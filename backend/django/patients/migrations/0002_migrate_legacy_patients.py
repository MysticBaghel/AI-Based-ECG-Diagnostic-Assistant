"""Copy every pre-refactor patient account into the permanent registry.

The old model tied a patient to a Django login. The new registry is independent,
so each ``PatientProfile`` becomes one ``Patient`` row with the same primary key
(which keeps every existing session and device assignment pointing at the right
person) and a newly generated permanent patient ID. The login account is kept
and linked through ``legacy_user`` for traceability; it is no longer required.
"""

from django.db import migrations


def copy_patients(apps, schema_editor):
    PatientProfile = apps.get_model("accounts", "PatientProfile")
    Patient = apps.get_model("patients", "Patient")

    for profile in PatientProfile.objects.select_related("user").iterator():
        user = profile.user
        full_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username
        patient, _ = Patient.objects.update_or_create(
            id=profile.id,
            defaults={
                "full_name": full_name,
                "phone": "",
                "phone_normalized": "",
                "email": user.email or "",
                "date_of_birth": profile.date_of_birth,
                "age_years": None,
                "sex": "unknown",
                "notes": profile.notes or "",
                "legacy_user_id": user.id,
            },
        )
        # auto_now_add/auto_now ignore the supplied values on save; copy the
        # account creation time explicitly so the registry order is sensible.
        Patient.objects.filter(pk=patient.pk).update(
            created_at=user.date_joined,
            updated_at=user.date_joined,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_alter_user_managers"),
        ("patients", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(copy_patients, migrations.RunPython.noop),
    ]
