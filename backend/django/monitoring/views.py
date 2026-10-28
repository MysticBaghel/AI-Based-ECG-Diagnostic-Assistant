from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .analysis import run_and_store
from .models import Session, SessionAnalysis
from .serializers import SessionAnalysisSerializer, SessionSerializer
from .telemetry import sync_session


class SessionViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """ECG sessions, analysis and report generation.

    Every authenticated operator may read and write sessions: the refactor
    removed the doctor/patient assignment model, and the application is run by
    clinic staff. The Django Admin remains available for technical access
    control.
    """

    serializer_class = SessionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = (
            Session.objects.select_related(
                "patient",
                "device",
                "started_by",
                "analysis",
            )
            .annotate(report_count=Count("reports", distinct=True))
            .order_by("-start_time")
        )

        patient = self.request.query_params.get("patient")
        status_filter = self.request.query_params.get("status")
        query = self.request.query_params.get("q", "").strip()

        if patient:
            if str(patient).isdigit():
                queryset = queryset.filter(
                    Q(patient_id=int(patient)) | Q(patient__patient_id__iexact=patient)
                )
            else:
                queryset = queryset.filter(patient__patient_id__iexact=patient)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if query:
            queryset = queryset.filter(
                Q(patient__full_name__icontains=query)
                | Q(patient__patient_id__icontains=query)
                | Q(device__name__icontains=query)
                | Q(id__icontains=query)
            )
        return queryset

    def perform_create(self, serializer):
        session = serializer.save(started_by=self.request.user)
        # Tell FastAPI this session exists. Best effort: a telemetry outage must
        # not stop an operator from starting a recording.
        sync_session(session)

    @action(detail=True, methods=["post"])
    def stop(self, request, *args, **kwargs):
        """POST /api/sessions/<id>/stop/ - closes the session."""
        session = self.get_object()

        if session.status != Session.Status.ACTIVE:
            return Response(
                {"detail": "Session is not active."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        session.end_time = timezone.now()
        session.status = Session.Status.COMPLETED
        session.save(update_fields=["end_time", "status", "updated_at"])
        # Push the status change so FastAPI answers 409 rather than 404 for data
        # that arrives after the session closed.
        sync_session(session)
        return Response(self.get_serializer(session).data)

    @action(detail=True, methods=["post"])
    def analyze(self, request, *args, **kwargs):
        """POST /api/sessions/<id>/analyze/ - run DSP + AI and store the result."""
        session = self.get_object()
        if session.status == Session.Status.ACTIVE:
            return Response(
                {"detail": "Stop the recording before running the analysis."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        analysis = run_and_store(session)
        return Response(SessionAnalysisSerializer(analysis).data)

    @action(detail=True, methods=["get"])
    def analysis(self, request, *args, **kwargs):
        """GET /api/sessions/<id>/analysis/ - the stored analysis, if any."""
        session = self.get_object()
        try:
            analysis = session.analysis
        except SessionAnalysis.DoesNotExist:
            return Response(
                {"detail": "Analysis has not run for this session."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(SessionAnalysisSerializer(analysis).data)

    @action(detail=True, methods=["post", "get"])
    def report(self, request, *args, **kwargs):
        """GET/POST /api/sessions/<id>/report/ - latest or newly generated PDF."""
        from reports.serializers import ReportSerializer
        from reports.service import generate_report

        session = self.get_object()

        if request.method == "GET":
            report = session.reports.order_by("-version").first()
            if report is None:
                return Response(
                    {"detail": "No report has been generated for this session."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            return Response(ReportSerializer(report).data)

        if session.status == Session.Status.ACTIVE:
            return Response(
                {"detail": "Stop the recording before generating a report."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        regenerate = str(request.data.get("regenerate", "")).lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        before = (
            session.reports.order_by("-version")
            .values_list("version", flat=True)
            .first()
        )
        try:
            report = generate_report(
                session,
                user=request.user,
                regenerate=regenerate,
            )
        except Exception as exc:  # noqa: BLE001 - surface a readable 400
            return Response(
                {"detail": f"Could not generate the report: {exc}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        created = before != report.version
        return Response(
            ReportSerializer(report).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get"])
    def reports(self, request, *args, **kwargs):
        """GET /api/sessions/<id>/reports/ - every stored report version."""
        from reports.serializers import ReportSerializer

        session = self.get_object()
        rows = session.reports.order_by("-version")
        return Response(ReportSerializer(rows, many=True).data)
