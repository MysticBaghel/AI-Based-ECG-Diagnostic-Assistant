"""Close legacy patient logins after the earlier role collapse.

The first pass of the refactor mapped every doctor and patient account to
``operator``. Doctor accounts should keep working; a patient account must not
become a staff login with access to the whole registry. This migration disables
those legacy logins, using the ``legacy_user`` link the registry migration
preserved. New patient records have no user account at all.
"""

from django.db import migrations


def disable_legacy_patients(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    Patient = apps.get_model("patients", "Patient")

    legacy_ids = list(
        Patient.objects.filter(legacy_user_id__isnull=False).values_list(
            "legacy_user_id", flat=True
        )
    )
    User.objects.filter(id__in=legacy_ids, role="operator").exclude(
        is_staff=True
    ).update(is_active=False)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_remove_doctor_and_patient_profiles"),
        ("patients", "0002_migrate_legacy_patients"),
    ]

    operations = [
        migrations.RunPython(disable_legacy_patients, migrations.RunPython.noop),
    ]
