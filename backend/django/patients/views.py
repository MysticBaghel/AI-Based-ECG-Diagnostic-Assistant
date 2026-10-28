from django.db.models import Count, Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Patient
from .normalisation import normalise_phone
from .serializers import (
    PatientSerializer,
    PatientWriteSerializer,
    duplicate_patients_for_phone,
)


class PatientViewSet(viewsets.ModelViewSet):
    """The patient registry: list/search, register, read, update.

    Every authenticated operator may use it. There is no doctor/patient role
    distinction any more: the application is operated by clinic staff, and the
    patient is a record rather than an account. Unauthenticated requests are
    refused by the default DRF permission class.

    Search (``?q=``) covers name, phone and the permanent patient ID. A separate
    ``?phone=`` performs an exact normalised-phone lookup for the duplicate
    warning before registration.
    """

    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "patch", "put", "head", "options"]

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return PatientWriteSerializer
        return PatientSerializer

    def get_queryset(self):
        queryset = Patient.objects.annotate(session_count=Count("sessions", distinct=True))
        query = self.request.query_params.get("q", "").strip()
        phone = self.request.query_params.get("phone", "").strip()

        if query:
            queryset = queryset.filter(
                Q(full_name__icontains=query)
                | Q(phone__icontains=query)
                | Q(patient_id__icontains=query)
            )
        if phone:
            queryset = queryset.filter(phone_normalized=normalise_phone(phone))
        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        duplicates = duplicate_patients_for_phone(
            serializer.validated_data.get("phone", "")
        )
        confirm = str(request.data.get("confirm_duplicate", "")).lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if duplicates and not confirm:
            return Response(
                {
                    "code": "duplicate_patient",
                    "detail": (
                        "A patient with this phone number already exists. "
                        "Review the match, or confirm that this is a different person."
                    ),
                    "duplicates": PatientSerializer(duplicates, many=True).data,
                },
                status=status.HTTP_409_CONFLICT,
            )

        patient = serializer.save()
        return Response(
            PatientSerializer(patient).data,
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        patient = self.get_object()
        serializer = self.get_serializer(patient, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(PatientSerializer(patient).data)

    @action(detail=False, methods=["get"], url_path="duplicates")
    def duplicates(self, request):
        """GET /api/patients/duplicates/?phone=... - pre-registration warning."""
        phone = request.query_params.get("phone", "")
        return Response(
            {
                "phone": phone,
                "duplicates": PatientSerializer(
                    duplicate_patients_for_phone(phone), many=True
                ).data,
            }
        )

    @action(detail=True, methods=["get"], url_path="sessions")
    def sessions(self, request, pk=None):
        """The session history shown on a patient profile."""
        patient = self.get_object()
        from monitoring.serializers import SessionSerializer

        rows = patient.sessions.select_related("device").select_related(
            "analysis"
        ).order_by("-start_time")
        return Response(SessionSerializer(rows, many=True).data)
