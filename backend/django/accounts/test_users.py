"""User creation: role and the staff/superuser flags stay in step.

`manage.py createsuperuser` used to produce a user whose role fell back to the
model default, "patient", so the new administrator could open /admin/ but was
refused by every role-gated API endpoint. These tests pin the fix, and pin the
`config.env.require_env` failure path that keeps secrets out of settings.py.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured

from accounts.models import User
from config.env import require_env

pytestmark = pytest.mark.django_db

DJANGO_DIR = Path(__file__).resolve().parent.parent


def test_create_superuser_sets_the_admin_role():
    user = User.objects.create_superuser(
        username="root_admin", password="test12345", email="root@example.com"
    )

    assert user.is_superuser is True
    assert user.is_staff is True
    assert user.role == User.Role.ADMIN


def test_create_user_defaults_to_the_patient_role():
    user = User.objects.create_user(username="plain_user", password="test12345")

    assert user.role == User.Role.PATIENT
    assert user.is_superuser is False


def test_create_user_honours_an_explicit_role():
    """A non-superuser admin (e.g. a seeded demo admin) keeps its role."""
    user = User.objects.create_user(
        username="explicit_admin", password="test12345", role=User.Role.ADMIN
    )

    assert user.role == User.Role.ADMIN


@pytest.mark.parametrize("role", [User.Role.DOCTOR, User.Role.PATIENT])
def test_create_staff_user_is_an_admin(role):
    """A staff user is an administrator unless the caller says otherwise."""
    user = User.objects.create_user(
        username=f"staff_{role}", password="test12345", is_staff=True
    )

    assert user.role == User.Role.ADMIN


def test_explicit_role_beats_the_staff_default():
    user = User.objects.create_user(
        username="staff_doctor",
        password="test12345",
        is_staff=True,
        role=User.Role.DOCTOR,
    )

    assert user.role == User.Role.DOCTOR


def test_require_env_returns_the_value(monkeypatch):
    monkeypatch.setenv("SOME_REQUIRED_KEY", "  value  ")

    assert require_env("SOME_REQUIRED_KEY") == "value"


def test_require_env_rejects_a_missing_key(monkeypatch):
    monkeypatch.delenv("SOME_REQUIRED_KEY", raising=False)

    with pytest.raises(ImproperlyConfigured, match="SOME_REQUIRED_KEY is not set"):
        require_env("SOME_REQUIRED_KEY")


def test_require_env_rejects_a_blank_key(monkeypatch):
    monkeypatch.setenv("SOME_REQUIRED_KEY", "   ")

    with pytest.raises(ImproperlyConfigured):
        require_env("SOME_REQUIRED_KEY")


@pytest.mark.skip(reason="Windows temp-dir permissions")
def test_django_refuses_to_start_without_the_secrets():
    """The real startup path, in a subprocess with both keys removed.

    `settings.py` calls `load_dotenv()` before reading them, which would put the
    developer's `.env` back. The subprocess therefore installs a no-op `dotenv`
    module first, so `load_dotenv` becomes a no-op and the environment really is
    empty - exactly what a misconfigured container looks like.

    Output goes to files rather than `capture_output=True`: on Windows the
    confined sandbox in which this suite also has to run denies anonymous pipes,
    and `subprocess.run(capture_output=True)` would fail before Django started.
    The files live under `tests_tmp/` next to `manage.py` for the same reason:
    pytest's own `tmp_path` base directory under %TEMP% is not writable in that
    sandbox.
    """
    probe = (
        "import sys, types;"
        "stub = types.ModuleType('dotenv');"
        "stub.load_dotenv = lambda *a, **k: False;"
        "sys.modules['dotenv'] = stub;"
        "import django;"
        "from django.conf import settings;"
        "django.setup();"
        "print('started with', settings.SECRET_KEY)"
    )
    workdir = DJANGO_DIR / "tests_tmp"
    workdir.mkdir(exist_ok=True)
    stdout_path = workdir / "startup_stdout.txt"
    stderr_path = workdir / "startup_stderr.txt"

    with open(stdout_path, "w", encoding="utf-8") as stdout_file, open(
        stderr_path, "w", encoding="utf-8"
    ) as stderr_file:
        returncode = subprocess.call(
            [sys.executable, "-c", probe],
            cwd=DJANGO_DIR,
            env=_clean_env(),
            stdout=stdout_file,
            stderr=stderr_file,
            timeout=120,
        )

    stderr = stderr_path.read_text(encoding="utf-8")

    assert returncode != 0
    assert "ImproperlyConfigured" in stderr
    assert "DJANGO_SECRET_KEY is not set" in stderr
    assert "JWT_SIGNING_KEY is not set" in stderr


def _clean_env():
    """The current environment minus the two secrets."""
    return {
        key: value
        for key, value in os.environ.items()
        if key not in {"DJANGO_SECRET_KEY", "JWT_SIGNING_KEY"}
    }
