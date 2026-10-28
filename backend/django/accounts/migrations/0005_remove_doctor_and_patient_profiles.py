"""Remove the doctor and patient-account profile tables.

Every device assignment and session already points at ``patients.Patient`` by
this point, and the patient records were copied by patients.0002, so these
tables can be dropped without losing clinical data. The Django user accounts
themselves are kept.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_remove_profiles_and_simplify_roles"),
        ("patients", "0002_migrate_legacy_patients"),
        ("devices", "0003_assigned_patient_registry"),
        ("monitoring", "0002_patient_registry_analysis"),
    ]

    operations = [
        migrations.DeleteModel(name="DoctorAssignment"),
        migrations.DeleteModel(name="DoctorProfile"),
        migrations.DeleteModel(name="PatientProfile"),
    ]
