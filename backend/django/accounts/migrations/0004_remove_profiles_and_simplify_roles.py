"""Collapse the role model to operator/admin.

Doctor profiles, care-team assignments and patient login profiles are removed in
the next migration, after the device and session foreign keys have been pointed
at the new patient registry. Doing the data change first keeps the schema valid
while those tables are still referenced.

Doctor accounts become operators. Legacy patient logins are disabled rather than
promoted: they were never clinic staff, and promoting them would expose every
patient record. The user rows stay for traceability.
"""

from django.db import migrations, models


def collapse_roles(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    # Clinicians keep working as operators. A legacy *patient* login was never
    # an operator account: converting it into one would give a patient access to
    # every other patient's record. Keep the row for traceability, but disable
    # the login. Staff/superuser accounts are left alone.
    User.objects.filter(role="doctor").update(role="operator")
    User.objects.filter(role="patient").exclude(is_staff=True).update(
        role="operator", is_active=False
    )
    User.objects.filter(role="patient", is_staff=True).update(role="operator")


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_alter_user_managers"),
        ("patients", "0002_migrate_legacy_patients"),
    ]

    operations = [
        migrations.RunPython(collapse_roles, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[("operator", "Operator"), ("admin", "Admin")],
                default="operator",
                max_length=20,
            ),
        ),
    ]
