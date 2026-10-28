from django.http import HttpResponse
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from .models import Report
from .serializers import ReportSerializer


class ReportViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Report history and authorized PDF download.

    Every authenticated operator may read the report history, matching the
    session access model. Unauthenticated requests are refused. The PDF bytes
    are served by this view, never from a public media path.
    """

    serializer_class = ReportSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = (
            Report.objects.select_related("patient", "session", "generated_by")
            .defer("pdf")
        )
        session_id = self.request.query_params.get("session")
        patient_id = self.request.query_params.get("patient")
        if session_id:
            queryset = queryset.filter(session_id=session_id)
        if patient_id:
            queryset = queryset.filter(patient_id=patient_id)
        return queryset.order_by("-generated_at")

    @action(detail=True, methods=["get"])
    def download(self, request, *args, **kwargs):
        """GET /api/reports/<id>/download/ - the stored PDF."""
        report = self.get_object()
        response = HttpResponse(bytes(report.pdf), content_type="application/pdf")
        filename = f"{report.report_id}-{report.patient.patient_id}.pdf"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response
