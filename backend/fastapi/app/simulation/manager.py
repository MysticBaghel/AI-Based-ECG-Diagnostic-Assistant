"""The in-site simulator: one running stream per session.

Two sources:

* a **scenario** from `app/simulation/scenarios.py` - a synthetic teaching
  rhythm (normal sinus, AF, PVCs, ...), chosen in the monitor's panel;
* a **CSV** uploaded from the patient page - real or external data replayed at
  its own pace, which is what lets the live chart be checked with a signal the
  application did not invent.

Both go through the same path: the generator or the CSV yields one second of
samples, the manager builds the exact `SensorDataRequest` / `ECGChunkRequest`
payloads a device would send, and calls the real ingestion handlers
(`app.routes.sensor.ingest_reading`, `ingest_ecg_chunk`). Nothing writes to the
tables directly, so the replay has the same validation, the same active-session
check, the same idempotency constraints and the same WebSocket fan-out as the
firmware. That is why the live graph works for a replayed file with no special
case in the monitor.

The stream is paced in wall-clock time (one chunk per second) and lives in this
process: a restart leaves the rows it already wrote, and the status endpoint
reports the run as "interrupted" rather than pretending it is still going.

Screening aid, not a medical diagnosis.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app import db
from app.core.security import DevicePrincipal
from app.errors import APIError
from app.models import RevokedDevice, SimulationRun
from app.routes.sensor import connect_device, ingest_ecg_chunk, ingest_reading
from app.schemas import ECGChunkRequest, SensorConnectRequest, SensorDataRequest
from app.simulation.generator import SAMPLE_RATE_HZ, ScenarioGenerator
from app.simulation.scenarios import Scenario, get_scenario

logger = logging.getLogger(__name__)

#: One second of signal per tick: the chart's window is 12 s, so a viewer sees
#: roughly twelve chunks, and the live analysis has fresh samples every tick.
CHUNK_SECONDS = 1.0
#: A run with no requested duration keeps going until the operator stops it;
#: this is the ceiling that stops a forgotten tab from writing forever.
MAX_DURATION_SECONDS = 600.0
#: A demo does not need more than a handful of streams at once.
MAX_CONCURRENT = 4
#: Refresh the heartbeat (and re-check revocation) this often.
HEARTBEAT_EVERY_CHUNKS = 30
#: How long `stop` waits for a tick to finish before cancelling.
STOP_TIMEOUT_SECONDS = 6.0
#: firmware string stored on the device connection, so the device list says
#: where the stream came from
FIRMWARE = "in-site-simulator"

SENSOR_TYPES = ("temperature", "spo2", "pulse", "motion")


class SimulationConflict(RuntimeError):
    """The requested run cannot start (already running, or too many running)."""


@dataclass
class _Run:
    session_id: uuid.UUID
    device_id: uuid.UUID
    run_id: uuid.UUID
    started_at: datetime
    label: str
    #: "scenario" or "csv"
    kind: str
    scenario: Scenario | None = None
    samples: list[float] | None = None
    #: samples per second in every `ECGChunkRequest` this run sends
    sample_rate_hz: int = SAMPLE_RATE_HZ
    duration_seconds: float | None = None
    task: asyncio.Task | None = None
    stop_event: asyncio.Event = field(default_factory=asyncio.Event)
    chunks_sent: int = 0
    readings_sent: int = 0
    error: str | None = None


class SimulationManager:
    def __init__(self) -> None:
        self._runs: dict[str, _Run] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    # -- lifecycle ---------------------------------------------------------

    def _lock(self, key: str) -> asyncio.Lock:
        return self._locks.setdefault(key, asyncio.Lock())

    def is_running(self, session_id: uuid.UUID) -> bool:
        run = self._runs.get(str(session_id))
        return run is not None and run.task is not None and not run.task.done()

    async def _begin(self, run: _Run) -> _Run:
        key = str(run.session_id)
        async with self._lock(key):
            if self.is_running(run.session_id):
                raise SimulationConflict(
                    "A simulation is already running for this session."
                )
            active = [
                other
                for other in self._runs.values()
                if other.task is not None and not other.task.done()
            ]
            if len(active) >= MAX_CONCURRENT:
                raise SimulationConflict(
                    f"At most {MAX_CONCURRENT} simulations can run at once."
                )

            async with db.SessionFactory() as session:
                session.add(
                    SimulationRun(
                        id=run.run_id,
                        session_id=run.session_id,
                        scenario="csv" if run.kind == "csv" else run.scenario.key,
                        label=run.label,
                        status="running",
                        started_at=run.started_at,
                        chunks_sent=0,
                        readings_sent=0,
                    )
                )
                await session.commit()

            self._runs[key] = run
            run.task = asyncio.create_task(
                self._stream(run), name=f"simulation-{run.session_id}"
            )
            logger.info(
                "Simulation started for session %s: %s (%s)",
                run.session_id,
                run.label,
                run.kind,
            )
            return run

    async def start(
        self,
        session_id: uuid.UUID,
        scenario_key: str,
        duration_seconds: float | None,
        device_id: uuid.UUID,
    ) -> _Run:
        """Stream a built-in scenario."""
        scenario = get_scenario(scenario_key)
        if duration_seconds is not None:
            duration_seconds = min(float(duration_seconds), MAX_DURATION_SECONDS)
        return await self._begin(
            _Run(
                session_id=session_id,
                device_id=device_id,
                run_id=uuid.uuid4(),
                started_at=datetime.now(timezone.utc),
                label=scenario.label,
                kind="scenario",
                scenario=scenario,
                duration_seconds=duration_seconds,
            )
        )

    async def start_csv(
        self,
        session_id: uuid.UUID,
        samples: list[float],
        name: str,
        device_id: uuid.UUID,
        sample_rate_hz: int = SAMPLE_RATE_HZ,
    ) -> _Run:
        """Replay uploaded samples; the run ends when the file does.

        `sample_rate_hz` is the rate the parser kept for the file - 300 Hz
        stays 300 Hz - and every chunk is declared with it.
        """
        return await self._begin(
            _Run(
                session_id=session_id,
                device_id=device_id,
                run_id=uuid.uuid4(),
                started_at=datetime.now(timezone.utc),
                label=name,
                kind="csv",
                samples=samples,
                sample_rate_hz=int(sample_rate_hz),
                duration_seconds=None,
            )
        )

    async def stop(self, session_id: uuid.UUID) -> None:
        run = self._runs.get(str(session_id))
        if run is None:
            return

        run.stop_event.set()
        task = run.task
        if task is None:
            return
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=STOP_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def shutdown(self) -> None:
        """Stop every run - called from the application's lifespan."""
        runs = list(self._runs.values())
        for run in runs:
            run.stop_event.set()
        tasks = [run.task for run in runs if run.task is not None]
        if not tasks:
            return
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=STOP_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            for task in tasks:
                task.cancel()

    # -- the stream --------------------------------------------------------

    async def _stream(self, run: _Run) -> None:
        device = DevicePrincipal(device_id=run.device_id, owner_id=0)
        generator = (
            ScenarioGenerator(run.scenario) if run.scenario is not None else None
        )
        status = "completed"
        error: str | None = None
        next_tick = time.monotonic()

        try:
            while not run.stop_event.is_set():
                elapsed = run.chunks_sent * CHUNK_SECONDS
                if run.duration_seconds is not None and elapsed >= run.duration_seconds:
                    break

                start_time = run.started_at + timedelta(seconds=elapsed)
                samples = self._samples_for(run, generator, elapsed)
                if not samples:
                    break  # the CSV ran out

                async with db.SessionFactory() as session:
                    if run.chunks_sent % HEARTBEAT_EVERY_CHUNKS == 0:
                        if await self._is_revoked(session, run.device_id):
                            error = "This device has been revoked."
                            status = "failed"
                            break
                        await connect_device(
                            SensorConnectRequest(firmware_version=FIRMWARE),
                            device=device,
                            session=session,
                        )

                    await ingest_ecg_chunk(
                        ECGChunkRequest(
                            session_id=run.session_id,
                            chunk_index=run.chunks_sent,
                            start_time=start_time,
                            sample_rate_hz=run.sample_rate_hz,
                            samples=samples,
                        ),
                        device=device,
                        session=session,
                    )
                    for reading in _vitals(run, generator, start_time):
                        await ingest_reading(reading, device=device, session=session)

                run.chunks_sent += 1
                run.readings_sent += len(SENSOR_TYPES)

                # Pace the stream in wall-clock time; if a slow write pushed us
                # past the deadline, resynchronise instead of bursting.
                next_tick += CHUNK_SECONDS
                wait = next_tick - time.monotonic()
                if wait > 0:
                    try:
                        await asyncio.wait_for(run.stop_event.wait(), timeout=wait)
                    except asyncio.TimeoutError:
                        pass
                else:
                    next_tick = time.monotonic()

        except asyncio.CancelledError:
            status = "stopped"
            raise
        except APIError as exc:
            # A recording that has been stopped (or a session Django closed) is
            # the normal end of a demo run, not a failure.
            if exc.code in {"session_not_active", "unknown_session"}:
                status = "stopped"
            else:
                status = "failed"
                error = exc.detail
            logger.info("Simulation for session %s ended: %s", run.session_id, exc.detail)
        except Exception as exc:  # pragma: no cover - defensive
            status = "failed"
            error = str(exc)
            logger.exception("Simulation for session %s failed", run.session_id)
        finally:
            run.error = error
            try:
                await self._finish(run, status, error)
            except asyncio.CancelledError:
                raise
            except Exception:  # pragma: no cover - defensive
                logger.exception("Could not record simulation result")

    @staticmethod
    def _samples_for(
        run: _Run, generator: ScenarioGenerator | None, elapsed: float
    ) -> list[float]:
        if run.samples is not None:
            rate = run.sample_rate_hz
            first = int(elapsed * rate)
            if first >= len(run.samples):
                return []
            return run.samples[first : first + int(CHUNK_SECONDS * rate)]
        assert generator is not None
        return generator.chunk(elapsed, CHUNK_SECONDS)

    async def _finish(self, run: _Run, status: str, error: str | None) -> None:
        now = datetime.now(timezone.utc)
        try:
            async with db.SessionFactory() as session:
                row = await session.get(SimulationRun, run.run_id)
                if row is not None:
                    row.status = status
                    row.stopped_at = now
                    row.chunks_sent = run.chunks_sent
                    row.readings_sent = run.readings_sent
                    row.error = (error or "")[:500] or None
                    await session.commit()
        finally:
            self._runs.pop(str(run.session_id), None)
        logger.info(
            "Simulation finished for session %s: %s after %d chunk(s)",
            run.session_id,
            status,
            run.chunks_sent,
        )

    @staticmethod
    async def _is_revoked(session, device_id: uuid.UUID) -> bool:
        return (
            await session.scalar(
                select(RevokedDevice.device_id).where(
                    RevokedDevice.device_id == device_id
                )
            )
        ) is not None

    # -- status ------------------------------------------------------------

    async def status(self, session_id: uuid.UUID) -> dict:
        run = self._runs.get(str(session_id))
        if run is not None and run.task is not None and not run.task.done():
            now = datetime.now(timezone.utc)
            elapsed = max(0.0, (now - run.started_at).total_seconds())
            return {
                "session_id": session_id,
                "running": True,
                "status": "running",
                "scenario": "csv" if run.kind == "csv" else run.scenario.key,
                "label": run.label,
                "started_at": run.started_at,
                "stopped_at": None,
                "duration_seconds": run.duration_seconds,
                "elapsed_seconds": round(elapsed, 1),
                "chunks_sent": run.chunks_sent,
                "readings_sent": run.readings_sent,
                "error": run.error,
            }

        row = await self._latest_row(session_id)
        if row is None:
            return {
                "session_id": session_id,
                "running": False,
                "status": "never",
                "scenario": None,
                "label": None,
                "started_at": None,
                "stopped_at": None,
                "duration_seconds": None,
                "elapsed_seconds": 0.0,
                "chunks_sent": 0,
                "readings_sent": 0,
                "error": None,
            }

        started_at = _as_utc(row.started_at)
        stopped_at = _as_utc(row.stopped_at)
        if stopped_at is not None:
            elapsed = max(0.0, (stopped_at - started_at).total_seconds())
        else:
            elapsed = max(0.0, (datetime.now(timezone.utc) - started_at).total_seconds())

        # A "running" row with no task in this process was interrupted by a
        # restart; say so rather than reporting a stream that is not there.
        status = row.status
        if status == "running":
            status = "interrupted"

        return {
            "session_id": session_id,
            "running": False,
            "status": status,
            "scenario": row.scenario,
            "label": row.label,
            "started_at": started_at,
            "stopped_at": stopped_at,
            "duration_seconds": None,
            "elapsed_seconds": round(elapsed, 1),
            "chunks_sent": row.chunks_sent,
            "readings_sent": row.readings_sent,
            "error": row.error,
        }

    @staticmethod
    async def _latest_row(session_id: uuid.UUID) -> SimulationRun | None:
        async with db.SessionFactory() as session:
            return await session.scalar(
                select(SimulationRun)
                .where(SimulationRun.session_id == session_id)
                .order_by(SimulationRun.started_at.desc())
                .limit(1)
            )


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _vitals(
    run: _Run, generator: ScenarioGenerator | None, at: datetime
) -> list[SensorDataRequest]:
    """The four scalar readings for this tick, within the API's legal ranges."""
    scenario = run.scenario
    temperature_c = scenario.temperature_c if scenario else 36.8
    spo2_percent = scenario.spo2_percent if scenario else 97.0
    motion_au = scenario.motion_au if scenario else 0.4
    offset = max(0.0, (at - run.started_at).total_seconds())

    pulse = (
        round(generator.instantaneous_heart_rate())
        if generator is not None
        else 72
    )
    pulse = min(250, max(20, pulse))
    spo2 = round(spo2_percent + 0.5 * math.sin(offset / 17.0), 1)
    temperature = round(temperature_c + 0.05 * math.sin(offset / 40.0), 1)
    motion = round(motion_au + 0.15 * math.sin(offset / 6.0), 1)

    values = {
        "temperature": (min(45.0, max(25.0, temperature)), "celsius"),
        "spo2": (min(100.0, max(50.0, spo2)), "percent"),
        "pulse": (float(pulse), "bpm"),
        "motion": (min(100.0, max(0.0, motion)), "a.u."),
    }

    return [
        SensorDataRequest(
            session_id=run.session_id,
            sensor_type=sensor_type,
            value=value,
            unit=unit,
            recorded_at=at,
        )
        for sensor_type, (value, unit) in values.items()
    ]


#: one manager per process, imported by the route module and the lifespan
manager = SimulationManager()
