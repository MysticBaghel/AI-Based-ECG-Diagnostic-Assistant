"""The integration test: the simulator against the real FastAPI app.

Nothing here is stubbed. `fastapi.testclient.TestClient` runs the same `app`
object the service runs, through the same routers, the same Pydantic schemas,
the same SQLAlchemy models and the same **database unique indexes** - so the
duplicate-is-one-row assertion is a statement about `uq_ecg_session_chunk` and
`uq_reading_session_type_time`, not about a mock.

That is the point: "the simulator fills the database" is a claim about rows in
`telemetry.sensor_readings` and `telemetry.ecg_chunks`, so the test counts rows.

The database is a temporary file rather than `:memory:` because the app opens
its own session per request; a file is shared by every connection, and it can be
read back afterwards to see what is really stored.

Screening aid, not a medical diagnosis.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest

# `Transport` calls `client.post(path, json=payload)`, and that keyword shadows
# the stdlib module inside the recorder below, so keep a second name for it.
import json as json_module

from app.core.config import JWT_ALGORITHM, JWT_SIGNING_KEY
from app.models import Base, ECGChunk, KnownSession, SensorReading

from simulator.config import Config
from simulator.simulator import ECGSimulator
from simulator.transport import Transport

from .conftest import DEVICE_ID, DOCTOR_ID, PATIENT_ID, SESSION_ID

# TestClient's default base URL; the transport posts to paths, so this only has
# to be a host its ASGI transport recognises.
TEST_BASE_URL = "http://testserver"

#: short enough for a test, long enough for several beats and chunks
RUN_SECONDS = 3.0
RUN_INTERVAL = 0.25
ECG_CHUNK_SECONDS = 1.0
ECG_RATE_HZ = 200
#: 0.25 s frames make the pipeline produce blocks quickly
ECG_FRAME_SECONDS = 0.25
ECG_FRAMES = 8


def device_token(device_id=DEVICE_ID, owner_id: int = DOCTOR_ID) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "type": "device",
            "device_id": str(device_id),
            "owner_id": owner_id,
            "iat": now,
            "exp": now + timedelta(hours=1),
        },
        JWT_SIGNING_KEY,
        algorithm=JWT_ALGORITHM,
    )


class Recorder:
    """A tiny capture layer that turns `Transport.post` into an ASGI request.

    `Transport` is kept exactly as it is in production - retries, logging,
    `Response` objects - and only the HTTP call underneath it is swapped, which
    is what makes this a test of the simulator rather than of a rewrite of it.

    The one subtlety is the body. `Transport` calls `client.post(path,
    json=payload)`; this recorder must put exactly the same bytes on the wire,
    so it JSON-encodes the dict *once* and sends it with an explicit
    `Content-Type: application/json`. Passing a pre-dumped string to `json=` (or
    a string to `data=` without the header, which gets form-encoded) makes the
    API see a JSON *string* instead of an object and answer
    `422 Input should be a valid dictionary` - the exact failure this harness
    exists to catch.
    """

    def __init__(self, client) -> None:
        self.client = client
        self.headers = {
            "Authorization": "Bearer " + device_token(),
            "Content-Type": "application/json",
        }
        self.calls: list[tuple[str, dict]] = []

    def install(self, transport) -> None:
        """Swap the httpx call for the TestClient, borrowing its auth header."""
        self.headers["Authorization"] = transport._client.headers["Authorization"]
        transport._client.post = self.post  # noqa: SLF001 - the one seam

    def post(self, path, json=None, **kwargs):
        """Stand in for `httpx.Client.post`: same signature, ASGI underneath."""
        self.calls.append((path, json))
        body = json_module.dumps(json) if json is not None else None
        response = self.client.post(path, content=body, headers=self.headers)

        class _Response:
            """Enough of an `httpx.Response` for `transport._json_or_text`."""

            status_code = response.status_code
            text = response.text

            @staticmethod
            def json():
                return response.json()

        return _Response()


def _sql(url: str) -> str:
    """'sqlite+aiosqlite:///C:/x/y.db' -> 'C:/x/y.db' for the stdlib driver."""
    return url.split(":///", 1)[1]


async def _create_schema(engine) -> None:
    """A fresh schema every time, even if this path was used by an earlier test."""
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)


async def _register_session(session_factory) -> None:
    async with session_factory() as session:
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


@pytest.fixture
def app_database(workdir: Path, monkeypatch):
    """Point the app at a temporary SQLite file and register one session.

    The engine is created inside the fixture and installed with
    `monkeypatch.setattr`, so the app's request handler and the test both use it
    and nothing leaks into the next test.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app import db

    url = f"sqlite+aiosqlite:///{(workdir / 'integration.db').as_posix()}"
    engine = create_async_engine(url, connect_args={"check_same_thread": False})
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "SessionFactory", session_factory)

    asyncio.run(_create_schema(engine))
    asyncio.run(_register_session(session_factory))

    yield {"engine": engine, "session_factory": session_factory, "path": _sql(url)}

    asyncio.run(engine.dispose())


@pytest.fixture
def client(app_database):
    """TestClient with the app's own session dependency, pointed at the file."""
    from fastapi.testclient import TestClient

    from app.db import get_session
    from app.main import app

    async def _override():
        async with app_database["session_factory"]() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _simulator_config(**overrides) -> Config:
    base = dict(
        base_url=TEST_BASE_URL,
        device_token=device_token(),
        session_id=str(SESSION_ID),
        duration_seconds=RUN_SECONDS,
        interval_seconds=RUN_INTERVAL,
        heartbeat_seconds=1.0,
        seed=4242,
        ecg_source="synthetic",
        ecg_download=False,
        ecg_chunk_seconds=ECG_CHUNK_SECONDS,
        ecg_sample_rate_hz=ECG_RATE_HZ,
        timeout_seconds=5.0,
        max_attempts=1,
    )
    base.update(overrides)
    return Config(**base)


def _transport(client, config: Config) -> tuple[Transport, "Recorder"]:
    """A production `Transport` whose underlying call is the TestClient."""
    recorder = Recorder(client)
    transport = Transport(
        base_url=config.base_url,
        token=config.device_token or "",
        timeout_seconds=config.timeout_seconds,
        max_attempts=config.max_attempts,
        seed=config.seed,
    )
    recorder.install(transport)
    return transport, recorder


def _run(client, config: Config):
    """Run the simulator for real, with the HTTP layer pointed at the app."""
    transport, recorder = _transport(client, config)
    simulator = ECGSimulator(config, transport=transport)
    with transport:
        simulator.run()
    return simulator, recorder


def _rows(path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


# --- the tests ------------------------------------------------------------


def test_heartbeat_is_registered(client, app_database) -> None:
    simulator, _ = _run(client, _simulator_config(duration_seconds=0.4, interval_seconds=0.2))

    assert simulator.stats.heartbeats_sent >= 1
    with _rows(app_database["path"]) as connection:
        rows = connection.execute(
            "SELECT device_id, owner_id, firmware_version FROM device_connections"
        ).fetchall()
    assert len(rows) == 1
    # SQLite stores a UUID as 32 hex characters without dashes, so compare
    # UUIDs rather than their string spellings.
    assert uuid.UUID(rows[0]["device_id"]) == DEVICE_ID
    assert rows[0]["firmware_version"].startswith("sim-")


def test_all_four_scalar_sensors_are_stored(client, app_database) -> None:
    """Temperature, SpO2, pulse and motion - one row each per batch, all legal."""
    simulator, _ = _run(client, _simulator_config())

    with _rows(app_database["path"]) as connection:
        rows = connection.execute(
            "SELECT sensor_type, COUNT(*) AS n, MIN(value) AS low, MAX(value) AS high, "
            "MIN(unit) AS unit FROM sensor_readings GROUP BY sensor_type"
        ).fetchall()

    stored = {row["sensor_type"]: row["n"] for row in rows}
    assert set(stored) == {"temperature", "spo2", "pulse", "motion"}, stored
    assert all(count >= 5 for count in stored.values()), stored

    # Every row the database holds came from a reading the API accepted.
    for row in rows:
        stats = simulator.stats.readings[row["sensor_type"]]
        assert stats.stored == row["n"]
        assert stats.failed == 0
        assert row["unit"] == {"temperature": "celsius", "spo2": "percent",
                              "pulse": "bpm", "motion": "a.u."}[row["sensor_type"]]

    # And the values are inside the Phase 2 ranges, read back from the database.
    from simulator.ranges import SCALARS

    for row in rows:
        spec = SCALARS[row["sensor_type"]]
        assert spec.low <= row["low"] and row["high"] <= spec.high


def test_ecg_chunks_are_stored_one_row_per_chunk(client, app_database) -> None:
    """One row per chunk - never one row per sample."""
    simulator, _ = _run(client, _simulator_config(ecg=True))

    with _rows(app_database["path"]) as connection:
        rows = connection.execute(
            "SELECT chunk_index, sample_count, sample_rate_hz, samples "
            "FROM ecg_chunks ORDER BY chunk_index"
        ).fetchall()

    assert len(rows) == simulator.stats.chunks_stored
    assert len(rows) >= 2, "a 3 s run in 1 s chunks should store at least 2 chunks"
    assert [row["chunk_index"] for row in rows] == list(range(len(rows)))

    for row in rows:
        samples = json.loads(row["samples"])
        assert len(samples) == row["sample_count"] == ECG_CHUNK_SECONDS * ECG_RATE_HZ
        assert row["sample_rate_hz"] == ECG_RATE_HZ
        assert all(abs(sample) <= 20.0 for sample in samples)

    # The samples column holds arrays, not one JSON number per row.
    assert simulator.stats.samples_sent == len(rows) * ECG_CHUNK_SECONDS * ECG_RATE_HZ


def test_a_resent_chunk_stores_exactly_one_row(client, app_database) -> None:
    """`--resend-chunks 1.0`: every chunk is sent twice, half the rows appear.

    This is the idempotency proof at the database level: the second POST of the
    same `chunk_index` answers `duplicate: true` and inserts nothing, because
    `uq_ecg_session_chunk` says so.
    """
    simulator, recorder = _run(
        client, _simulator_config(ecg=True, resend_chunks=1.0)
    )

    ecg_calls = [path for path, _ in recorder.calls if path == "/sensor/ecg"]
    with _rows(app_database["path"]) as connection:
        row_count = connection.execute("SELECT COUNT(*) FROM ecg_chunks").fetchone()[0]

    assert simulator.stats.chunks_stored >= 2
    assert simulator.stats.chunks_resent == simulator.stats.chunks_stored
    assert simulator.stats.chunks_duplicate == simulator.stats.chunks_stored
    # Twice as many requests as chunks, one row per chunk.
    assert len(ecg_calls) == 2 * simulator.stats.chunks_stored
    assert row_count == simulator.stats.chunks_stored


def test_a_dropped_chunk_leaves_a_hole_in_the_indexes(client, app_database) -> None:
    """`--drop-chunks 1.0`: nothing is sent, so there are no chunks at all."""
    simulator, recorder = _run(client, _simulator_config(ecg=True, drop_chunks=1.0))

    ecg_calls = [path for path, _ in recorder.calls if path == "/sensor/ecg"]
    with _rows(app_database["path"]) as connection:
        row_count = connection.execute("SELECT COUNT(*) FROM ecg_chunks").fetchone()[0]

    assert ecg_calls == []
    assert row_count == 0
    assert simulator.stats.chunks_dropped == simulator.stats.chunks_produced


def test_a_duplicate_scalar_reading_is_one_row(client, app_database) -> None:
    """Two batches at the same timestamp: the second must not add rows.

    `recorded_at` is part of `uq_reading_session_type_time`, so this is the same
    idempotency guarantee as the ECG chunk, applied to the scalar path.
    """
    config = _simulator_config(duration_seconds=0.4, interval_seconds=0.2)
    transport, _ = _transport(client, config)
    simulator = ECGSimulator(config, transport=transport)
    with transport:
        simulator.send_scalars("2026-01-01T00:00:00+00:00")
        simulator.send_scalars("2026-01-01T00:00:00+00:00")

    with _rows(app_database["path"]) as connection:
        row_count = connection.execute("SELECT COUNT(*) FROM sensor_readings").fetchone()[0]

    assert row_count == 4, "one row per sensor type, not two"
    assert all(stats.duplicates == 1 for stats in simulator.stats.readings.values())
    assert all(stats.stored == 1 for stats in simulator.stats.readings.values())


def test_the_summary_json_is_written_and_parsable(client, workdir: Path) -> None:
    """The smoke script reads this file, so its shape is part of the contract."""
    out = workdir / "summary.json"
    simulator, _ = _run(client, _simulator_config(ecg=True, output_json=str(out)))
    simulator.write_summary()

    data = json.loads(out.read_text(encoding="utf-8"))
    assert set(data["readings"]) == {"temperature", "spo2", "pulse", "motion"}
    assert data["readings_total"]["stored"] > 0
    assert data["ecg"]["chunks_stored"] >= 2
    assert data["ecg"]["chunks_unique_stored"] == data["ecg"]["chunks_stored"]
    assert data["transport"]["by_status"]["200"] > 0
    assert "not a medical diagnosis" in simulator.summary_text().lower()
