"""Pytest fixtures for the FastAPI telemetry suite.

The suite runs on SQLite (`sqlite+aiosqlite:///:memory:`, one shared connection)
with `TELEMETRY_SCHEMA=""`, because SQLite has no schemas. PostgreSQL is what
the schema, the JSONB columns and Alembic target in a real deployment, and the
test file `test_migrations.py` checks that the migrations and the models agree.

`os.environ` is set here, before `app.*` is imported: `app.core.config` reads the
environment at import time and has no default for `JWT_SIGNING_KEY`, which is the
point of that rule.
"""

import os
import uuid

# Test-only values. Must be set before anything under app/ is imported.
os.environ["JWT_SIGNING_KEY"] = "test-only-jwt-signing-key"
os.environ["FASTAPI_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["TELEMETRY_SCHEMA"] = ""
os.environ["HEARTBEAT_THRESHOLD_SECONDS"] = "120"

from datetime import datetime, timedelta, timezone  # noqa: E402

import jwt  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import db  # noqa: E402
from app.core.config import JWT_ALGORITHM, JWT_SIGNING_KEY  # noqa: E402
from app.db import Base, get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import KnownSession  # noqa: E402

# --- Identity used across the suite ---------------------------------------

PATIENT_ID = 4
DOCTOR_ID = 2
OTHER_DOCTOR_ID = 3
ADMIN_ID = 1

DEVICE_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
OTHER_DEVICE_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
SESSION_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")


def issue_user_token(
    user_id: int = DOCTOR_ID,
    role: str = "doctor",
    *,
    token_type: str = "access",
    expires_in: int = 3600,
) -> str:
    """A token shaped exactly like `RoleTokenObtainPairSerializer` produces."""
    now = datetime.now(timezone.utc)
    payload = {
        "token_type": token_type,
        "user_id": user_id,
        "role": role,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, JWT_SIGNING_KEY, algorithm=JWT_ALGORITHM)


def issue_device_token(
    device_id: uuid.UUID = DEVICE_ID,
    owner_id: int = DOCTOR_ID,
    *,
    token_type_claim: str = "device",
    expires_in: int = 3600,
) -> str:
    """A token shaped exactly like `devices.tokens.issue_device_token`."""
    now = datetime.now(timezone.utc)
    payload = {
        "type": token_type_claim,
        "device_id": str(device_id),
        "owner_id": owner_id,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    return jwt.encode(payload, JWT_SIGNING_KEY, algorithm=JWT_ALGORITHM)


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- Database --------------------------------------------------------------


@pytest.fixture(autouse=True)
def database(monkeypatch):
    """One in-memory SQLite database per test, shared by every connection.

    `StaticPool` is what keeps `:memory:` alive between the fixture's setup and
    the request that follows it - otherwise every connection would see a fresh,
    empty database.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "SessionFactory", session_factory)

    import asyncio

    async def _setup() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def _teardown() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await engine.dispose()

    asyncio.run(_setup())
    yield
    asyncio.run(_teardown())


@pytest.fixture
def client():
    """A TestClient with its lifespan run, so the app starts like it really does."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def session_factory():
    return db.SessionFactory


@pytest.fixture
def known_session(database):
    """A registered session for DEVICE_ID, patient PATIENT_ID, doctor DOCTOR_ID."""
    import asyncio

    async def _create() -> None:
        async with db.SessionFactory() as session:
            session.add(
                KnownSession(
                    session_id=SESSION_ID,
                    patient_id=PATIENT_ID,
                    device_id=DEVICE_ID,
                    doctor_ids=[DOCTOR_ID],
                    status="active",
                )
            )
            await session.commit()

    asyncio.run(_create())
    return SESSION_ID


@pytest.fixture
def unregistered_session_id():
    return uuid.UUID("99999999-9999-4999-8999-999999999999")


@pytest.fixture
def scoped_client(client):
    """TestClient with the app's DB dependency pointed at the test engine.

    The lifespan runs `create_all` against whatever `db.engine` is, which the
    `database` fixture has already replaced, so the two agree.
    """
    async def _override():
        async with db.SessionFactory() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    yield client
    app.dependency_overrides.clear()
