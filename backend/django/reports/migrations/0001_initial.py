import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import reports.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("monitoring", "0002_patient_registry_analysis"),
        ("patients", "0002_migrate_legacy_patients"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Report",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "report_id",
                    models.CharField(
                        default=reports.models.generate_report_code,
                        editable=False,
                        max_length=24,
                        unique=True,
                    ),
                ),
                ("version", models.PositiveIntegerField(default=1)),
                ("analysis_snapshot", models.JSONField(blank=True, default=dict)),
                ("pdf", models.BinaryField()),
                ("file_size", models.PositiveIntegerField(default=0)),
                ("checksum", models.CharField(blank=True, max_length=64)),
                ("generated_at", models.DateTimeField(auto_now_add=True)),
                (
                    "generated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="generated_reports",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "patient",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reports",
                        to="patients.patient",
                    ),
                ),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reports",
                        to="monitoring.session",
                    ),
                ),
            ],
            options={
                "ordering": ["-generated_at"],
                "indexes": [
                    models.Index(
                        fields=["patient", "generated_at"],
                        name="reports_rep_patient_f5341b_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("session", "version"),
                        name="unique_report_version_per_session",
                    )
                ],
            },
        ),
    ]
