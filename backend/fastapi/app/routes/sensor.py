"""Sensor ingestion and status.

Every device endpoint goes through `require_device`, which verifies the token
locally and refuses a revoked device. Every write then goes through
`require_active_session_for_device`, which answers 404 / 403 / 409 for a session
this service does not know, a session belonging to another device, and a session
that is no longer active. Nothing reaches the tables without those two checks.
"""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import HEARTBEAT_THRESHOLD_SECONDS
from app.core.security import (
    DevicePrincipal,
    UserPrincipal,
    require_device,
    require_user,
)
from app.db import get_session
from app.errors import APIError
from app.models import (
    DeviceConnection,
    ECGChunk,
    KnownSession,
    RevokedDevice,
    SensorReading,
)
from app.registry import require_active_session_for_device, require_viewer
from app.schemas import (
    ECGChunkRequest,
    ECGChunkResponse,
    ECGChunkView,
    ReadingsResponse,
    SENSOR_RULES,
    SensorConnectRequest,
    SensorConnectResponse,
    SensorDataRequest,
    SensorDataResponse,
    SensorStatusResponse,
)
from app.hub import hub

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sensor"])


def _as_utc(value: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes, PostgreSQL returns aware ones.

    Normalising on the way out keeps `seconds_since_seen` and every timestamp in
    a response consistently UTC-aware.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def _revoked_ids(session: AsyncSession) -> set[uuid.UUID]:
    """One query for the whole deny list; it is expected to stay tiny."""
    return set(await session.scalars(select(RevokedDevice.device_id)))


def _heartbeat(last_seen: datetime | None, *, revoked: bool = False) -> dict:
    now = datetime.now(timezone.utc)
    seen = _as_utc(last_seen)
    seconds_since = None if seen is None else (now - seen).total_seconds()
    online = seconds_since is not None and seconds_since <= HEARTBEAT_THRESHOLD_SECONDS
    return {
        "last_seen": seen,
        "seconds_since_seen": seconds_since,
        "online": online,
        "revoked": revoked,
    }


async def _upsert_connection(
    session: AsyncSession,
    device: DevicePrincipal,
    payload: SensorConnectRequest,
) -> DeviceConnection:
    """Register or refresh the device row.

    SELECT then INSERT/UPDATE rather than PostgreSQL's `ON CONFLICT DO UPDATE`:
    the test suite runs on SQLite, which has no such clause, and a device
    connects a handful of times a day - one extra round trip is not worth a
    dialect-specific code path (or an untested one).
    """
    now = datetime.now(timezone.utc)
    connection = await session.get(DeviceConnection, device.device_id)

    if connection is None:
        connection = DeviceConnection(
            device_id=device.device_id,
            owner_id=device.owner_id,
            last_seen=now,
            firmware_version=payload.firmware_version,
            ip_address=payload.ip_address,
        )
        session.add(connection)
    else:
        connection.owner_id = device.owner_id
        connection.last_seen = now
        connection.firmware_version = payload.firmware_version
        connection.ip_address = payload.ip_address

    await session.commit()
    await session.refresh(connection)
    return connection


@router.post("/sensor/connect", response_model=SensorConnectResponse)
async def connect_device(
    payload: SensorConnectRequest,
    device: DevicePrincipal = Depends(require_device),
    session: AsyncSession = Depends(get_session),
) -> SensorConnectResponse:
    """Register/refresh the device connection and stamp `last_seen`."""
    connection = await _upsert_connection(session, device, payload)
    heartbeat = _heartbeat(connection.last_seen)

    return SensorConnectResponse(
        device_id=device.device_id,
        owner_id=device.owner_id,
        last_seen=heartbeat["last_seen"],
        online=heartbeat["online"],
        firmware_version=connection.firmware_version,
    )


@router.get("/sensor/status", response_model=SensorStatusResponse)
async def sensor_status(
    device_id: uuid.UUID | None = Query(default=None),
    user: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> SensorStatusResponse:
    """Heartbeat for every device the caller is allowed to see.

    * patient: the devices on their own sessions
    * doctor: the devices on sessions of patients they are assigned to
    * admin: every device that has ever been registered
    """
    rows = (
        await session.execute(
            select(
                KnownSession.device_id,
                KnownSession.patient_id,
                KnownSession.doctor_ids,
            ).distinct()
        )
    ).all()

    if user.role == "patient":
        rows = [row for row in rows if row.patient_id == user.user_id]
    elif user.role == "doctor":
        # doctor_ids is a JSON array; the containment test happens here rather
        # than in SQL because SQLite and PostgreSQL spell it differently and the
        # table is small by design.
        rows = [row for row in rows if user.user_id in (row.doctor_ids or [])]

    visible: dict[uuid.UUID, dict] = {
        row.device_id: {"device_id": row.device_id, "owner_id": None} for row in rows
    }

    if user.role == "admin":
        # Admins also see devices that connected but are not on any session yet,
        # otherwise a new device is invisible until its first session starts.
        for device in await session.scalars(select(DeviceConnection.device_id)):
            visible.setdefault(device, {"device_id": device, "owner_id": None})

    if device_id is not None:
        visible = (
            {device_id: visible[device_id]}
            if device_id in visible
            else {}
        )

    revoked = await _revoked_ids(session)

    connections: dict[uuid.UUID, DeviceConnection] = {}
    if visible:
        found = await session.scalars(
            select(DeviceConnection).where(DeviceConnection.device_id.in_(list(visible)))
        )
        connections = {connection.device_id: connection for connection in found}

    devices = []
    for current, entry in visible.items():
        connection = connections.get(current)
        if connection is not None:
            entry["owner_id"] = connection.owner_id
        devices.append(
            {
                **entry,
                **_heartbeat(
                    connection.last_seen if connection else None,
                    revoked=current in revoked,
                ),
            }
        )

    # Admin asking about one revoked device that never connected: still report
    # it, so the dashboard can show "revoked, never seen".
    if device_id is not None and not devices and device_id in revoked:
        devices.append(
            {
                "device_id": device_id,
                "owner_id": None,
                **_heartbeat(None, revoked=True),
            }
        )

    return SensorStatusResponse(
        threshold_seconds=HEARTBEAT_THRESHOLD_SECONDS,
        devices=devices,
    )


@router.post("/sensor/data", response_model=SensorDataResponse)
async def ingest_reading(
    payload: SensorDataRequest,
    device: DevicePrincipal = Depends(require_device),
    session: AsyncSession = Depends(get_session),
) -> SensorDataResponse:
    """Store one scalar reading. Idempotent on (session, type, timestamp)."""
    await require_active_session_for_device(session, payload.session_id, device)

    recorded_at = payload.recorded_at or datetime.now(timezone.utc)

    existing = await session.scalar(
        select(SensorReading).where(
            SensorReading.session_id == payload.session_id,
            SensorReading.sensor_type == payload.sensor_type,
            SensorReading.recorded_at == recorded_at,
        )
    )
    if existing is not None:
        return _reading_response(existing, stored=False)

    reading = SensorReading(
        session_id=payload.session_id,
        device_id=device.device_id,
        sensor_type=payload.sensor_type,
        value=payload.value,
        unit=payload.unit,
        recorded_at=recorded_at,
    )
    session.add(reading)
    try:
        await session.commit()
    except IntegrityError:
        # Two concurrent retries: the unique index picked a winner. Answer from
        # the winner's row instead of failing the request.
        await session.rollback()
        winner = await session.scalar(
            select(SensorReading).where(
                SensorReading.session_id == payload.session_id,
                SensorReading.sensor_type == payload.sensor_type,
                SensorReading.recorded_at == recorded_at,
            )
        )
        if winner is None:  # pragma: no cover - only if the row vanished
            raise APIError(
                status_code=409,
                detail="Conflicting reading could not be resolved.",
                code="session_not_active",
            )
        return _reading_response(winner, stored=False)

    await session.refresh(reading)
    response = _reading_response(reading, stored=True)

    await hub.publish(
        str(payload.session_id),
        {
            "event": "reading",
            "session_id": str(payload.session_id),
            "sensor_type": reading.sensor_type,
            "value": reading.value,
            "unit": reading.unit,
            "recorded_at": _as_utc(reading.recorded_at).isoformat(),
        },
    )
    return response


def _reading_response(reading: SensorReading, *, stored: bool) -> SensorDataResponse:
    return SensorDataResponse(
        stored=stored,
        duplicate=not stored,
        reading_id=reading.id,
        session_id=reading.session_id,
        sensor_type=reading.sensor_type,
        value=reading.value,
        unit=reading.unit,
        recorded_at=_as_utc(reading.recorded_at),
    )


@router.post("/sensor/ecg", response_model=ECGChunkResponse)
async def ingest_ecg_chunk(
    payload: ECGChunkRequest,
    device: DevicePrincipal = Depends(require_device),
    session: AsyncSession = Depends(get_session),
) -> ECGChunkResponse:
    """Store one ECG chunk. Idempotent on (session_id, chunk_index)."""
    await require_active_session_for_device(session, payload.session_id, device)

    existing = await session.scalar(
        select(ECGChunk).where(
            ECGChunk.session_id == payload.session_id,
            ECGChunk.chunk_index == payload.chunk_index,
        )
    )
    if existing is not None:
        return _chunk_response(existing, stored=False)

    chunk = ECGChunk(
        session_id=payload.session_id,
        device_id=device.device_id,
        start_time=payload.start_time,
        sample_rate_hz=payload.sample_rate_hz,
        samples=payload.samples,
        sample_count=len(payload.samples),
        chunk_index=payload.chunk_index,
    )
    session.add(chunk)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        winner = await session.scalar(
            select(ECGChunk).where(
                ECGChunk.session_id == payload.session_id,
                ECGChunk.chunk_index == payload.chunk_index,
            )
        )
        if winner is None:  # pragma: no cover - only if the row vanished
            raise APIError(
                status_code=409,
                detail="Conflicting chunk could not be resolved.",
                code="session_not_active",
            )
        return _chunk_response(winner, stored=False)

    await session.refresh(chunk)
    response = _chunk_response(chunk, stored=True)

    # Metadata only: pushing 5 000 samples down every viewer socket is what the
    # REST endpoint is for.
    await hub.publish(
        str(payload.session_id),
        {
            "event": "ecg_chunk",
            "session_id": str(payload.session_id),
            "chunk_index": chunk.chunk_index,
            "sample_count": chunk.sample_count,
            "sample_rate_hz": chunk.sample_rate_hz,
            "start_time": _as_utc(chunk.start_time).isoformat(),
        },
    )
    return response


def _chunk_response(chunk: ECGChunk, *, stored: bool) -> ECGChunkResponse:
    return ECGChunkResponse(
        stored=stored,
        duplicate=not stored,
        chunk_id=chunk.id,
        session_id=chunk.session_id,
        chunk_index=chunk.chunk_index,
        sample_count=chunk.sample_count,
        sample_rate_hz=chunk.sample_rate_hz,
        start_time=_as_utc(chunk.start_time),
        duration_seconds=chunk.sample_count / chunk.sample_rate_hz,
    )


@router.get("/sessions/{session_id}/readings", response_model=ReadingsResponse)
async def list_readings(
    session_id: uuid.UUID,
    limit: int = Query(default=100, ge=1, le=500),
    sensor_type: str | None = Query(default=None),
    user: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> ReadingsResponse:
    """Latest scalar readings for a session the caller may see."""
    await require_viewer(session, session_id, user)

    if sensor_type is not None and sensor_type not in SENSOR_RULES:
        raise APIError(
            status_code=422,
            detail=f"Unknown sensor_type {sensor_type!r}.",
            code="validation_error",
            errors=[
                {
                    "field": "sensor_type",
                    "message": f"expected one of {sorted(SENSOR_RULES)}",
                }
            ],
        )

    query = select(SensorReading).where(SensorReading.session_id == session_id)
    if sensor_type is not None:
        query = query.where(SensorReading.sensor_type == sensor_type)
    query = query.order_by(SensorReading.recorded_at.desc()).limit(limit)

    readings = list(await session.scalars(query))

    return ReadingsResponse(
        session_id=session_id,
        count=len(readings),
        readings=[
            {
                "reading_id": str(reading.id),
                "sensor_type": reading.sensor_type,
                "value": reading.value,
                "unit": reading.unit,
                "recorded_at": _as_utc(reading.recorded_at).isoformat(),
            }
            for reading in readings
        ],
    )


@router.get("/sessions/{session_id}/ecg/{chunk_index}", response_model=ECGChunkView)
async def get_ecg_chunk(
    session_id: uuid.UUID,
    chunk_index: int,
    user: UserPrincipal = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> ECGChunkView:
    """One stored chunk, samples included. 404 when it does not exist."""
    await require_viewer(session, session_id, user)

    chunk = await session.scalar(
        select(ECGChunk).where(
            ECGChunk.session_id == session_id,
            ECGChunk.chunk_index == chunk_index,
        )
    )
    if chunk is None:
        raise APIError(
            status_code=404,
            detail=f"No ECG chunk {chunk_index} for this session.",
            code="not_found",
        )

    return ECGChunkView(
        chunk_id=chunk.id,
        session_id=chunk.session_id,
        device_id=chunk.device_id,
        chunk_index=chunk.chunk_index,
        sample_rate_hz=chunk.sample_rate_hz,
        sample_count=chunk.sample_count,
        start_time=_as_utc(chunk.start_time),
        duration_seconds=chunk.sample_count / chunk.sample_rate_hz,
        samples=chunk.samples,
    )
