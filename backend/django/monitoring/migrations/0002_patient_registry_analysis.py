"""Move sessions to the patient registry and add stored analysis results."""

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("monitoring", "0001_initial"),
        ("patients", "0002_migrate_legacy_patients"),
        ("devices", "0003_assigned_patient_registry"),
        ("accounts", "0004_remove_profiles_and_simplify_roles"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="session",
            name="patient",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="sessions",
                to="patients.patient",
            ),
        ),
        migrations.AlterField(
            model_name="session",
            name="started_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="started_sessions",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="session",
            name="sample_rate_hz",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="session",
            name="notes",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="session",
            name="created_at",
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="session",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.CreateModel(
            name="SessionAnalysis",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("completed", "Completed"),
                            ("unusable", "Unusable signal"),
                            ("failed", "Failed"),
                            ("unavailable", "Analysis unavailable"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("result", models.JSONField(blank=True, default=dict)),
                ("model_version", models.CharField(blank=True, max_length=100)),
                ("analyzed_at", models.DateTimeField(blank=True, null=True)),
                ("error", models.TextField(blank=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "session",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="analysis",
                        to="monitoring.session",
                    ),
                ),
            ],
            options={
                "verbose_name": "session analysis",
                "verbose_name_plural": "session analyses",
            },
        ),
    ]
