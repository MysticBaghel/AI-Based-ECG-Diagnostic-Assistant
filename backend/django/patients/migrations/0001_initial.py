import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import patients.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("accounts", "0003_alter_user_managers"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Patient",
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
                    "patient_id",
                    models.CharField(
                        default=patients.models.generate_patient_id,
                        editable=False,
                        help_text="Permanent application-generated patient identifier.",
                        max_length=20,
                        unique=True,
                    ),
                ),
                ("full_name", models.CharField(max_length=200)),
                ("phone", models.CharField(blank=True, db_index=True, max_length=32)),
                (
                    "phone_normalized",
                    models.CharField(blank=True, db_index=True, max_length=32),
                ),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("date_of_birth", models.DateField(blank=True, null=True)),
                (
                    "age_years",
                    models.PositiveSmallIntegerField(
                        blank=True,
                        help_text="Only needed when the date of birth is unknown.",
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(0),
                            django.core.validators.MaxValueValidator(130),
                        ],
                    ),
                ),
                (
                    "sex",
                    models.CharField(
                        choices=[
                            ("unknown", "Unknown"),
                            ("female", "Female"),
                            ("male", "Male"),
                            ("other", "Other"),
                        ],
                        default="unknown",
                        max_length=20,
                    ),
                ),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "legacy_user",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="legacy_patient",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["full_name", "id"],
                "indexes": [
                    models.Index(fields=["full_name"], name="patients_pa_full_na_b75abe_idx")
                ],
            },
        ),
    ]
