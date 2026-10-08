"""Test fixtures for the simulator suite.

Two things happen here that are worth reading before the tests:

1. **The FastAPI app's configuration is set before anything under `app` is
   imported.** `app/core/config.py` reads the environment at import time and has
   no default for `JWT_SIGNING_KEY`, and it refuses to start with SQLite *and* a
   schema. These values are the same ones `backend/fastapi/tests/conftest.py`
   uses, so the two suites run against an identically configured app.

2. **The integration tests use a file-backed SQLite database.** The FastAPI app
   opens a new session per request from its own engine, so an in-memory database
   with `StaticPool` would have to be shared through a dependency override;
   a temporary file is simpler, and it means the test asserts what is *really*
   in the database - which is the whole point of "the row count is right".

Screening aid, not a medical diagnosis.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest

# --- the app's environment, before `app` is imported -----------------------

os.environ["JWT_SIGNING_KEY"] = "simulator-test-jwt-signing-key"
os.environ["FASTAPI_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["TELEMETRY_SCHEMA"] = ""
os.environ["HEARTBEAT_THRESHOLD_SECONDS"] = "120"

# The path fix-up: `cd simulator ; pytest` should work without an install step,
# even though some environments do not process pytest.ini's `pythonpath`.
REPO_ROOT = Path(__file__).resolve().parents[2]
for extra in (REPO_ROOT, REPO_ROOT / "backend" / "fastapi"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

# --- identity shared with the integration test -----------------------------

PATIENT_ID = 41
DOCTOR_ID = 7
DEVICE_ID = uuid.UUID("11111111-2222-4333-8444-555555555555")
SESSION_ID = uuid.UUID("66666666-7777-4888-8999-aaaaaaaaaaaa")


@pytest.fixture
def session_id() -> uuid.UUID:
    return SESSION_ID


@pytest.fixture
def device_id() -> uuid.UUID:
    return DEVICE_ID


@pytest.fixture
def workdir():
    """A throwaway directory for tests that need real files.

    Two deliberate choices:

    * **not** pytest's `tmp_path` - under a restricted Windows sandbox the
      system temp directory can be unlistable, and pytest's cleanup then turns
      a green suite red;
    * **not** `tempfile.mkdtemp` - it creates the directory mode 0700, which
      some sandboxes refuse to write into. A plain `mkdir` under the checkout
      inherits normal permissions.
    """
    import itertools
    import shutil

    counter = itertools.count()
    # Outside `tests/`, so pytest never tries to collect these directories.
    base = Path(__file__).resolve().parents[1] / ".pytest-work"
    base.mkdir(exist_ok=True)

    created: list[Path] = []

    def _make() -> Path:
        path = base / f"case-{os.getpid()}-{next(counter)}"
        path.mkdir(parents=True, exist_ok=True)
        created.append(path)
        return path

    try:
        yield _make()
    finally:
        for path in created:
            shutil.rmtree(path, ignore_errors=True)


# --- pytest's own tmp_path cleanup ----------------------------------------
#
# `tmp_path` is used by several tests, and pytest 9 always runs
# `cleanup_dead_symlinks(basetemp)` at the end of the session. Under a
# restricted Windows sandbox that directory may not be listable, and the
# resulting PermissionError fails the whole run *after* every test has passed -
# a harness artefact masquerading as a test failure. Removing a few dead
# symlinks is not something these tests depend on, so it is turned off here
# rather than left to turn a green suite red on someone else's machine.
def pytest_sessionstart(session):  # noqa: ARG001
    """Patch before any test runs, so it is in place when the session ends."""
    try:
        from _pytest import tmpdir as _pytest_tmpdir

        _pytest_tmpdir.cleanup_dead_symlinks = lambda *args, **kwargs: None
    except Exception:  # pragma: no cover - if pytest's internals move, ignore
        pass
