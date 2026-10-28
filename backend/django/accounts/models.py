from django.contrib.auth.models import AbstractUser, UserManager as BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    """User manager that keeps ``role`` in step with the staff/superuser flags.

    There are only two roles now: an operator (clinic staff running ECG
    recordings) and an administrator (technical administration, Django Admin).
    An explicit ``role=...`` always wins.
    """

    def _create_user(self, username, email=None, password=None, **extra_fields):
        if "role" not in extra_fields:
            if extra_fields.get("is_superuser") or extra_fields.get("is_staff"):
                extra_fields["role"] = User.Role.ADMIN
            else:
                extra_fields["role"] = User.Role.OPERATOR
        return super()._create_user(username, email, password, **extra_fields)


class User(AbstractUser):
    """Custom user model: Django authentication plus the operator/admin role.

    Patients are *not* users. They live in the ``patients`` app as permanent
    records, so a patient does not need a login account to have an ECG history.
    """

    class Role(models.TextChoices):
        OPERATOR = "operator", "Operator"
        ADMIN = "admin", "Admin"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.OPERATOR,
    )

    objects = UserManager()

    def __str__(self) -> str:
        return self.username
