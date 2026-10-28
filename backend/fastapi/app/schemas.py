"""Pydantic request/response models and per-sensor validation.

The ranges are the ones in `docs/api-contract.md` section 7. They are here, not
in the endpoints, so a malformed frame is rejected by the schema layer with a
422 that names the offending field - it never reaches the database and it never
becomes a 500.
"""

import uuid
from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.config import (
    MAX_ECG_SAMPLES_PER_CHUNK,
    MAX_FUTURE_SECONDS,
    MAX_PAYLOAD_BYTES,
    MIN_ECG_SAMPLE_RATE_HZ,
    MAX_ECG_SAMPLE_RATE_HZ,
)

SensorType = Literal["temperature", "spo2", "pulse", "motion"]

#: value range and the single canonical unit per sensor type
SENSOR_RULES: dict[str, tuple[float, float, str]] = {
    "temperature": (25.0, 45.0, "celsius"),
    "spo2": (50.0, 100.0, "percent"),
    "pulse": (20.0, 250.0, "bpm"),
    "motion": (0.0, 100.0, "a.u."),
}

#: spellings the firmware and the simulator actually send, normalised to the
#: canonical unit above. Everything else is a 422.
UNIT_ALIASES: dict[str, dict[str, str]] = {
    "temperature": {"celsius": "celsius", "c": "celsius", "°c": "celsius", "degc": "celsius"},
    "spo2": {"percent": "percent", "%": "percent", "pct": "percent"},
    "pulse": {"bpm": "bpm", "beats/min": "bpm", "beats_per_minute": "bpm"},
    "motion": {"a.u.": "a.u.", "au": "a.u.", "g": "a.u.", "arbitrary": "a.u."},
}

#: readings before 2000 are a clock that was never set, not data
EARLIEST_TIMESTAMP = datetime(2000, 1, 1, tzinfo=timezone.utc)

MAX_ECG_SAMPLE_MV = 20.0


class StrictModel(BaseModel):
    """Base for request bodies: unknown fields are ignored, never rejected.

    Firmware in the field cannot be redeployed in lockstep with this API, so a
    superset of the documented fields is accepted (documented in
    `docs/api-contract.md` section 2). Anything whose *value* is wrong is still
    a 422.
    """

    model_config = ConfigDict(extra="ignore")


def _as_utc(value: datetime) -> datetime:
    """A timestamp without an offset means UTC, not server-local time."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _check_timestamp(value: datetime | None, now: datetime | None = None) -> datetime:
    """Shared rule: not absurdly in the future, not before the year 2000."""
    now = now or datetime.now(timezone.utc)
    timestamp = _as_utc(value) if value is not None else now

    if timestamp < EARLIEST_TIMESTAMP:
        raise ValueError("timestamp is before 2000-01-01, refusing a clock that is not set")
    if (timestamp - now).total_seconds() > MAX_FUTURE_SECONDS:
        raise ValueError(
            f"timestamp is more than {MAX_FUTURE_SECONDS}s in the future"
        )
    return timestamp


# --- device endpoints -----------------------------------------------------


class SensorConnectRequest(StrictModel):
    firmware_version: str | None = Field(default=None, max_length=50)
    ip_address: str | None = Field(default=None, max_length=64)


class SensorConnectResponse(BaseModel):
    device_id: uuid.UUID
    owner_id: int
    last_seen: datetime
    online: bool
    firmware_version: str | None = None


class SensorDataRequest(StrictModel):
    session_id: uuid.UUID
    sensor_type: SensorType
    value: float
    unit: str = Field(min_length=1, max_length=20)
    recorded_at: datetime | None = None

    @field_validator("recorded_at")
    @classmethod
    def _timestamp_not_absurd(cls, value: datetime | None) -> datetime | None:
        return _check_timestamp(value) if value is not None else None

    @model_validator(mode="after")
    def _value_and_unit_in_range(self) -> "SensorDataRequest":
        low, high, canonical = SENSOR_RULES[self.sensor_type]

        if not low <= self.value <= high:
            raise ValueError(
                f"{self.sensor_type} must be between {low} and {high}, got {self.value}"
            )

        normalised = UNIT_ALIASES[self.sensor_type].get(self.unit.strip().lower())
        if normalised is None:
            raise ValueError(
                f"unit {self.unit!r} is not valid for {self.sensor_type}; "
                f"expected {canonical}"
            )
        self.unit = normalised
        return self


class SensorDataResponse(BaseModel):
    stored: bool
    duplicate: bool
    reading_id: uuid.UUID
    session_id: uuid.UUID
    sensor_type: str
    value: float
    unit: str
    recorded_at: datetime


class ECGChunkRequest(StrictModel):
    session_id: uuid.UUID
    chunk_index: Annotated[int, Field(ge=0, le=1_000_000)]
    start_time: datetime
    sample_rate_hz: Annotated[
        int, Field(ge=MIN_ECG_SAMPLE_RATE_HZ, le=MAX_ECG_SAMPLE_RATE_HZ)
    ]
    samples: Annotated[
        list[float], Field(min_length=1, max_length=MAX_ECG_SAMPLES_PER_CHUNK)
    ]

    @field_validator("start_time")
    @classmethod
    def _timestamp_not_absurd(cls, value: datetime) -> datetime:
        return _check_timestamp(value)

    @field_validator("samples")
    @classmethod
    def _samples_are_plausible_millivolts(cls, value: list[float]) -> list[float]:
        for index, sample in enumerate(value):
            if sample != sample or sample in (float("inf"), float("-inf")):
                raise ValueError(f"samples.{index} is not a finite number")
            if abs(sample) > MAX_ECG_SAMPLE_MV:
                raise ValueError(
                    f"samples.{index}={sample} is outside ±{MAX_ECG_SAMPLE_MV} mV"
                )
        return value

    @property
    def duration_seconds(self) -> float:
        return len(self.samples) / self.sample_rate_hz


class ECGChunkResponse(BaseModel):
    stored: bool
    duplicate: bool
    chunk_id: uuid.UUID
    session_id: uuid.UUID
    chunk_index: int
    sample_count: int
    sample_rate_hz: int
    start_time: datetime
    duration_seconds: float


# --- user endpoints -------------------------------------------------------


class DeviceStatus(BaseModel):
    device_id: uuid.UUID
    owner_id: int | None
    last_seen: datetime | None
    seconds_since_seen: float | None
    online: bool
    revoked: bool = False


class SensorStatusResponse(BaseModel):
    threshold_seconds: int
    devices: list[DeviceStatus]


class ReadingsResponse(BaseModel):
    session_id: uuid.UUID
    count: int
    readings: list[dict]


class ECGChunkView(BaseModel):
    chunk_id: uuid.UUID
    session_id: uuid.UUID
    device_id: uuid.UUID
    chunk_index: int
    sample_rate_hz: int
    sample_count: int
    start_time: datetime
    duration_seconds: float
    samples: list[float]


class ECGChunkSummary(BaseModel):
    """One chunk in a session's recording index - metadata only.

    The dashboard needs to know which chunks exist before it can ask for the
    samples of the ones it wants to draw. Sending every sample in an index
    response would turn a small listing into a multi-megabyte payload, so the
    index is metadata and the waveform is fetched chunk by chunk.
    """

    chunk_id: uuid.UUID
    chunk_index: int
    sample_rate_hz: int
    sample_count: int
    start_time: datetime
    duration_seconds: float


class ECGChunkListResponse(BaseModel):
    session_id: uuid.UUID
    count: int
    chunks: list[ECGChunkSummary]


# --- internal registry endpoints -----------------------------------------


class SessionRegistration(BaseModel):
    """What Django pushes. `extra="ignore"` so Django may send more later.

    ``doctor_ids`` was removed with the hospital workflow. A legacy Django that
    still sends it is accepted and ignored, so a rolling deploy does not break
    session registration.
    """

    model_config = ConfigDict(extra="ignore")

    session_id: uuid.UUID
    patient_id: int
    device_id: uuid.UUID
    status: Literal["active", "completed", "aborted"] = "active"


class SessionRegistrationResponse(BaseModel):
    session_id: uuid.UUID
    status: str
    known: bool


class RevokeDeviceRequest(StrictModel):
    reason: str | None = Field(default=None, max_length=200)


class RevokeDeviceResponse(BaseModel):
    device_id: uuid.UUID
    revoked: bool


# --- analysis -------------------------------------------------------------


class SignalQuality(BaseModel):
    score: float | None = None
    level: str = "unknown"
    usable: bool = False
    reasons: list[str] = Field(default_factory=list)
    flatline: bool = False
    clipping: bool = False
    missing_samples: int = 0


class AnalysisSignal(BaseModel):
    sample_rate_hz: int | None = None
    sample_count: int = 0
    duration_seconds: float = 0.0
    chunks: int = 0
    quality: SignalQuality = Field(default_factory=SignalQuality)
    filtering_note: str = ""


class AnalysisMeasurements(BaseModel):
    heart_rate_bpm: float | None = None
    rr_intervals_ms: list[float] = Field(default_factory=list)
    rr_mean_ms: float | None = None
    rr_std_ms: float | None = None
    rmssd_ms: float | None = None
    pnn50_percent: float | None = None
    beats_detected: int = 0
    r_peak_seconds: list[float] = Field(default_factory=list)


class AIResult(BaseModel):
    available: bool = False
    reason: str = ""
    model_name: str | None = None
    model_version: str | None = None
    classes: list[str] = Field(default_factory=list)
    predicted_class: str | None = None
    probabilities: dict[str, float] | None = None
    analyzed_at: datetime | None = None


class AnalysisResponse(BaseModel):
    session_id: uuid.UUID
    analysis_version: int
    status: Literal["completed", "unusable", "failed"]
    analyzed_at: datetime
    signal: AnalysisSignal
    measurements: AnalysisMeasurements
    ai: AIResult
    findings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class InternalECGChunk(BaseModel):
    chunk_index: int
    start_time: datetime
    sample_rate_hz: int
    samples: list[float]


class InternalECGResponse(BaseModel):
    session_id: uuid.UUID
    sample_rate_hz: int | None
    sample_count: int
    chunks: list[InternalECGChunk]


class AnalysisStatusResponse(BaseModel):
    available: bool
    dsp: str = "deterministic"
    model_name: str | None = None
    model_version: str | None = None
    reason: str = ""


__all__ = [
    "AIResult",
    "AnalysisMeasurements",
    "AnalysisResponse",
    "AnalysisSignal",
    "AnalysisStatusResponse",
    "ECGChunkRequest",
    "ECGChunkListResponse",
    "ECGChunkResponse",
    "ECGChunkSummary",
    "ECGChunkView",
    "InternalECGChunk",
    "InternalECGResponse",
    "MAX_PAYLOAD_BYTES",
    "ReadingsResponse",
    "RevokeDeviceRequest",
    "RevokeDeviceResponse",
    "SENSOR_RULES",
    "SensorConnectRequest",
    "SensorConnectResponse",
    "SensorDataRequest",
    "SensorDataResponse",
    "SensorStatusResponse",
    "SensorType",
    "SessionRegistration",
    "SessionRegistrationResponse",
    "SignalQuality",
]
