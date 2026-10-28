"""Point a device's optional dedicated patient at the new registry."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("devices", "0002_device_assigned_patient"),
        ("patients", "0002_migrate_legacy_patients"),
        ("accounts", "0004_remove_profiles_and_simplify_roles"),
    ]

    operations = [
        migrations.AlterField(
            model_name="device",
            name="assigned_patient",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="assigned_devices",
                to="patients.patient",
            ),
        ),
    ]
