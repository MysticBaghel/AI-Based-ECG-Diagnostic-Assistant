import re

from django.utils import timezone
from rest_framework import serializers

from .models import Patient
from .normalisation import normalise_phone


class PatientSerializer(serializers.ModelSerializer):
    """Read model for the registry.

    ``patient_id`` is the permanent public ID; ``id`` is the internal key an ECG
    session references. Both are exposed because the operator may search by
    either, and the UI shows the readable one.
    """

    age = serializers.IntegerField(read_only=True)
    session_count = serializers.SerializerMethodField()

    class Meta:
        model = Patient
        fields = [
            "id",
            "patient_id",
            "full_name",
            "phone",
            "email",
            "date_of_birth",
            "age",
            "age_years",
            "sex",
            "notes",
            "session_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_session_count(self, obj) -> int:
        annotated = getattr(obj, "session_count", None)
        if annotated is not None:
            return annotated
        return obj.sessions.count()


class PatientWriteSerializer(serializers.ModelSerializer):
    """Create/update input.

    ``patient_id`` is never accepted: it is generated once and permanent.
    """

    class Meta:
        model = Patient
        fields = [
            "full_name",
            "phone",
            "email",
            "date_of_birth",
            "age_years",
            "sex",
            "notes",
        ]

    def validate_full_name(self, value: str) -> str:
        name = " ".join(value.split())
        if len(name) < 2:
            raise serializers.ValidationError("Enter the patient's full name.")
        return name

    def validate_phone(self, value: str) -> str:
        phone = (value or "").strip()
        if not phone:
            return ""
        digits = re.sub(r"\D", "", phone)
        if not 7 <= len(digits) <= 20:
            raise serializers.ValidationError(
                "Enter a phone number with 7 to 20 digits."
            )
        return phone

    def validate_date_of_birth(self, value):
        if value is not None and value > timezone.localdate():
            raise serializers.ValidationError("Date of birth cannot be in the future.")
        return value

    def validate(self, attrs):
        date_of_birth = attrs.get(
            "date_of_birth", getattr(self.instance, "date_of_birth", None)
        )
        age_years = attrs.get("age_years", getattr(self.instance, "age_years", None))
        if date_of_birth is not None and age_years is not None:
            raise serializers.ValidationError(
                {
                    "age_years": (
                        "Provide either a date of birth or an age, not both."
                    )
                }
            )
        return attrs


def duplicate_patients_for_phone(
    phone: str, *, exclude_pk: int | None = None
) -> list[Patient]:
    """Likely existing patients with the same phone number.

    An empty phone never produces a warning: most patients registered without a
    number would otherwise look like duplicates of each other.
    """
    normalized = normalise_phone(phone)
    if not normalized:
        return []
    queryset = Patient.objects.filter(phone_normalized=normalized)
    if exclude_pk is not None:
        queryset = queryset.exclude(pk=exclude_pk)
    return list(queryset.order_by("full_name")[:5])
