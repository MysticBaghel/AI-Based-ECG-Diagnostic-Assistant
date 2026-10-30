"""SQLAlchemy models - the `telemetry` schema.

Rules this file exists to enforce:

* No foreign key points at a Django table. `session_id` and `device_id` are plain
  UUID columns, `owner_id`/`patient_id` plain integers, because the two services
  share identifiers, not a database.
* `sensor_readings` and `ecg_chunks` both carry `device_id` copied from the
  **verified token**, never from the request body: a device cannot write data
  attributed to another device.
* Idempotency is a database constraint, not a code path: a unique index on
  `(session_id, sensor_type, recorded_at)` for scalar readings and one on
  `(session_id, chunk_index)` for ECG chunks. A retry that races the original
  loses at the index and is then answered from the winner's row.
* Analysis results are stored here because this service owns the ECG samples and
  the DSP/inference run. Django keeps the business copy for the report.
* `ml_predictions` is the queryable projection of each analysis run's ML output
  and AI advisory. The full payload stays in `analysis_results.analysis`; the
  projection exists so model identity, class, confidence and risk can be
  filtered/audited without parsing JSON.
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
    not in it. There is no doctor assignment any more: the patient id is kept
    for association and audit, not for role-based viewer scoping.
    """

    __tablename__ = "known_sessions"

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=_uuid
    )
    patient_id: Mapped[int] = mapped_column(Integer, nullable=False)
    device_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
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
    analyses: Mapped[list["AnalysisResult"]] = relationship(back_populates="session")

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


class AnalysisResult(Base):
    """One DSP + inference run for one session, versioned.

    The payload is the same JSON Django stores, so a report generated from it
    reflects exactly what was computed - including an explicit "AI unavailable"
    outcome rather than a fabricated prediction.
    """

    __tablename__ = "analysis_results"
    __table_args__ = (
        UniqueConstraint("session_id", "version", name="uq_analysis_session_version"),
        Index("ix_analysis_session_analyzed", "session_id", "analyzed_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=_uuid
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("known_sessions.session_id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    analysis: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False
    )
    analyzed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped[KnownSession] = relationship(back_populates="analyses")
    ml_predictions: Mapped[list["MLPrediction"]] = relationship(
        back_populates="analysis_result"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AnalysisResult {self.session_id} v{self.version} {self.status}>"


class MLPrediction(Base):
    """The classification + advisory record for one analysis version.

    `analysis_results.analysis` already contains the full JSON payload. This
    table is the queryable projection: one row per signal-processing run, with
    the model identity, class, confidence, quality and advisory outcome as
    columns, and the complete ML/advisory snapshots for audit.

    A unique `analysis_result_id` is the idempotency rule: re-running an
    analysis creates a new version and therefore a new row, while a retry that
    targets the same version cannot duplicate it.
    """

    __tablename__ = "ml_predictions"
    __table_args__ = (
        UniqueConstraint(
            "analysis_result_id",
            name="uq_ml_prediction_analysis",
        ),
        Index("ix_ml_prediction_session_created", "session_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=_uuid
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("known_sessions.session_id", ondelete="CASCADE"),
        nullable=False,
    )
    analysis_result_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("analysis_results.id", ondelete="CASCADE"),
        nullable=False,
    )
    analysis_version: Mapped[int] = mapped_column(Integer, nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    predicted_class: Mapped[str | None] = mapped_column(String(8), nullable=True)
    predicted_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    heart_rate_bpm: Mapped[float | None] = mapped_column(Float, nullable=True)
    window_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    signal_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    advisor_provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    advice_risk_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ml: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False
    )
    advice: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped[KnownSession] = relationship()
    analysis_result: Mapped[AnalysisResult] = relationship(
        back_populates="ml_predictions"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<MLPrediction {self.session_id} v{self.analysis_version} "
            f"{self.predicted_class}>"
        )


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


class SimulationRun(Base):
    """One run of the built-in simulator against one session.

    The streaming state lives in memory (`app/simulation/manager.py`); this row
    is the durable trace. It is what lets the dashboard show "this recording was
    simulated as atrial fibrillation" after a restart, and what the analysis
    copies into its stored payload so a report can say the data is
    demonstration data rather than a patient recording.
    """

    __tablename__ = "simulation_runs"
    __table_args__ = (
        Index("ix_simulation_session_started", "session_id", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=_uuid
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("known_sessions.session_id", ondelete="CASCADE"),
        nullable=False,
    )
    #: scenario key and its display label, copied so a renamed scenario cannot
    #: rewrite history
    scenario: Mapped[str] = mapped_column(String(40), nullable=False)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    #: running | stopped | completed | failed
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    stopped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    chunks_sent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    readings_sent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<SimulationRun {self.session_id} {self.scenario} {self.status}>"


__all__ = [
    "AnalysisResult",
    "ECGChunk",
    "DeviceConnection",
    "KnownSession",
    "MLPrediction",
    "RevokedDevice",
    "SensorReading",
    "SimulationRun",
    "engine",
]
