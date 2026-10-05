"""Configuration rules that must survive refactoring.

The important one: the service refuses to start without `JWT_SIGNING_KEY`, and
refuses a configuration that cannot work (SQLite has no schemas). There is no
default signing key, because a default is how a development value ends up
verifying production traffic.
"""

import os
import subprocess
import sys
from pathlib import Path

from app.core.config import settings

FASTAPI_DIR = Path(__file__).resolve().parent.parent

PROBE = "import app.main; print('started')"

#: Overrides applied to every probe. `JWT_SIGNING_KEY` is removed first, then
#: added back only by the tests that want it.
BASE_ENV = {
    "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
    "TELEMETRY_SCHEMA": "",
    "FASTAPI_ENV": "test",
}


def _run_probe(env_overrides: dict[str, str | None]) -> tuple[int, str]:
    """Import the app in a fresh process and return (exit code, stderr).

    Output goes to files: `capture_output=True` opens anonymous pipes, which the
    confined Windows sandbox of this workspace denies.
    """
    workdir = FASTAPI_DIR / "tests_tmp"
    workdir.mkdir(exist_ok=True)
    stdout_path = workdir / "config_stdout.txt"
    stderr_path = workdir / "config_stderr.txt"

    env = dict(os.environ)
    env.pop("JWT_SIGNING_KEY", None)
    env.update(BASE_ENV)
    for key, value in env_overrides.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value

    with open(stdout_path, "w", encoding="utf-8") as stdout_file, open(
        stderr_path, "w", encoding="utf-8"
    ) as stderr_file:
        completed = subprocess.run(
            [sys.executable, "-c", PROBE],
            cwd=FASTAPI_DIR,
            env=env,
            stdout=stdout_file,
            stderr=stderr_file,
            timeout=180,
        )

    return completed.returncode, stderr_path.read_text(encoding="utf-8")


def test_settings_have_no_default_for_the_jwt_signing_key():
    assert settings.model_fields["jwt_signing_key"].is_required()


def test_startup_fails_when_the_jwt_signing_key_is_missing():
    returncode, stderr = _run_probe({"JWT_SIGNING_KEY": None})

    assert returncode != 0
    assert "jwt_signing_key" in stderr.lower()


def test_startup_succeeds_when_the_key_is_present():
    returncode, stderr = _run_probe({"JWT_SIGNING_KEY": "test-only-jwt-signing-key"})

    assert returncode == 0, stderr


def test_startup_fails_when_sqlite_is_combined_with_a_schema():
    returncode, stderr = _run_probe(
        {
            "JWT_SIGNING_KEY": "test-only-jwt-signing-key",
            "TELEMETRY_SCHEMA": "telemetry",
        }
    )

    assert returncode != 0
    assert "sqlite has no schemas" in stderr.lower()


def test_startup_succeeds_with_a_schema_on_postgres():
    """The schema switch is only rejected for SQLite, never for PostgreSQL."""
    returncode, stderr = _run_probe(
        {
            "JWT_SIGNING_KEY": "test-only-jwt-signing-key",
            "DATABASE_URL": "postgresql+psycopg://ecg:ecg@127.0.0.1:5432/ecg",
            "TELEMETRY_SCHEMA": "telemetry",
        }
    )

    # Creating no connection is the point: importing the app must not require a
    # reachable database.
    assert returncode == 0, stderr


def test_the_schema_name_is_none_when_the_setting_is_empty():
    assert settings.telemetry_schema_name is None


def test_cors_origins_are_split_and_trimmed():
    assert "http://localhost:5173" in settings.cors_origin_list
    assert all(origin == origin.strip() for origin in settings.cors_origin_list)


def test_the_heartbeat_threshold_is_configurable():
    assert settings.heartbeat_threshold_seconds == 120


def test_the_future_timestamp_guard_is_configured():
    assert settings.max_future_seconds == 300
