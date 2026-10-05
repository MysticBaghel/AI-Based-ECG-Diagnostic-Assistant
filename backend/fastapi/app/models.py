"""SQLAlchemy models - the `telemetry` schema.

Rules this file exists to enforce:

* No foreign key points at a Django table. `session_id` and `device_id` are plain
  UUID columns, `owner_id`/`patient_id`/`doctor_ids` plain integers, because the
  two services share identifiers, not a database.
* `sensor_readings` and `ecg_chunks` both carry `device_id` copied from the
  **verified token**, never from the request body: a device cannot write data
  attributed to another device.
* Idempotency is a database constraint, not a code path: a unique index on
  `(session_id, sensor_type, recorded_at)` for scalar readings and one on
  `(session_id, chunk_index)` for ECG chunks. A retry that races the original
  loses at the index and is then answered from the winner's row.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from app.db import Base, engine


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


# JSONB on PostgreSQL, JSON on SQLite: one ECG chunk is a list of samples, and
# the alternative - one row per sample at 250 Hz - is 21.6 million rows a day.
SamplesType = JSONB().with_variant(JSON(), "sqlite")


class KnownSession(Base):
    """Cache of the sessions Django knows about, pushed by Django.

    FastAPI cannot ask Django on the ingest path (a Django outage must not stop
    devices), so it keeps its own copy and refuses data for sessions that are
    not in it. See `docs/api-contract.md` section 10 for the tradeoff.
    """

    __tablename__ = "known_sessions"

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=_uuid
    )
    patient_id: Mapped[int] = mapped_column(Integer, nullable=False)
    device_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    # An int[] on PostgreSQL, a JSON list on SQLite.
    doctor_ids: Mapped[list] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False, default=list
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    readings: Mapped[list["SensorReading"]] = relationship(back_populates="session")
    chunks: Mapped[list["ECGChunk"]] = relationship(back_populates="session")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<KnownSession {self.session_id} {self.status}>"


class DeviceConnection(Base):
    """One row per device: when FastAPI last heard from it."""

    __tablename__ = "device_connections"

    device_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=_uuid
    )
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    firmware_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<DeviceConnection {self.device_id} last_seen={self.last_seen}>"


class SensorReading(Base):
    """One scalar reading: temperature, spo2, pulse or motion."""

    __tablename__ = "sensor_readings"
    __table_args__ = (
        # Idempotency: a retry of the same reading is already here.
        UniqueConstraint(
            "session_id",
            "sensor_type",
            "recorded_at",
            name="uq_reading_session_type_time",
        ),
        Index("ix_reading_session_time", "session_id", "recorded_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=_uuid
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("known_sessions.session_id", ondelete="CASCADE"),
        nullable=False,
    )
    device_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    sensor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped[KnownSession] = relationship(back_populates="readings")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<SensorReading {self.sensor_type}={self.value}{self.unit}>"


class ECGChunk(Base):
    """One chunk of ECG samples - one row per chunk, never one row per sample."""

    __tablename__ = "ecg_chunks"
    __table_args__ = (
        # Idempotency and the device's at-least-once delivery key.
        UniqueConstraint("session_id", "chunk_index", name="uq_ecg_session_chunk"),
        Index("ix_ecg_session_start", "session_id", "start_time"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=_uuid
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("known_sessions.session_id", ondelete="CASCADE"),
        nullable=False,
    )
    device_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sample_rate_hz: Mapped[int] = mapped_column(Integer, nullable=False)
    samples: Mapped[list] = mapped_column(SamplesType, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped[KnownSession] = relationship(back_populates="chunks")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ECGChunk {self.session_id}#{self.chunk_index} n={self.sample_count}>"


class RevokedDevice(Base):
    """FastAPI-owned deny list.

    Device tokens are stateless and stay valid until they expire, so the only
    way to cut a device off before that is a list this service owns and checks
    on every device request. One primary-key lookup per request.
    """

    __tablename__ = "revoked_devices"

    device_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=_uuid
    )
    reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    revoked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<RevokedDevice {self.device_id}>"


__all__ = [
    "ECGChunk",
    "DeviceConnection",
    "KnownSession",
    "RevokedDevice",
    "SensorReading",
    "engine",
]
