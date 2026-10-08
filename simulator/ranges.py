"""The Phase 2 validation ranges, in one place.

Every value the simulator generates is checked against these before it goes on
the wire, so the simulator cannot produce a reading the API answers 422 to.

These mirror `backend/fastapi/app/schemas.py` (`SENSOR_RULES`, `UNIT_ALIASES`,
the ECG limits) and therefore `docs/api-contract.md` section 7. The test
`tests/test_ranges_match_api.py` imports that module when FastAPI is installed
and fails if the two ever drift apart.

Why the margins: a random walk with a hard clamp still *sends* the boundary
value, and a boundary value is one rounding error away from a 422. Keeping the
walk inside `[low, high]` with a margin means the value on the wire is always
comfortably legal.

Screening aid, not a medical diagnosis.
"""

from __future__ import annotations

from dataclasses import dataclass

#: protocol limits for an ECG chunk, from api-contract.md section 7
ECG_SAMPLE_MV_LIMIT = 20.0  # every sample must be within +/- this
ECG_MIN_SAMPLE_RATE_HZ = 100
ECG_MAX_SAMPLE_RATE_HZ = 2000
ECG_MAX_SAMPLES_PER_CHUNK = 5000
ECG_MAX_CHUNK_INDEX = 1_000_000

#: the default rate the simulator resamples everything to before chunking
ECG_TARGET_SAMPLE_RATE_HZ = 200


@dataclass(frozen=True)
class ScalarSpec:
    """One scalar sensor: the legal range, the unit, and a realistic walk.

    Four numbers describe the signal:

    * `low`/`high` are the protocol limits - what the API will accept;
    * `walk_low`/`walk_high` are the tighter band the generator keeps to;
    * `step` is the largest change in one sampling interval;
    * `decimals` is the resolution of the *reading*, not of the walk.

    A reading is the walk rounded to `decimals`; the walk itself stays
    continuous. That distinction is the whole reason this class exists.
    """

    sensor_type: str
    unit: str
    low: float
    high: float
    walk_low: float
    walk_high: float
    start: float
    step: float
    decimals: int

    def clamp(self, value: float) -> float:
        """Keep a generated value inside the legal range, whatever happened."""
        return min(self.high, max(self.low, value))

    def clamp_walk(self, value: float) -> float:
        """Keep the walk inside its realistic band (which is inside the legal one)."""
        return min(self.walk_high, max(self.walk_low, value))

    def round(self, value: float) -> float:
        """Round to the resolution a real sensor would report."""
        return round(value, self.decimals)

    def report(self, walk_value: float) -> float:
        """What the sensor puts on the wire: the walk, rounded, then clamped.

        The clamp after the rounding is belt and braces - rounding a value that
        is already inside the band cannot take it outside - but it means no
        arithmetic change can ever produce an illegal reading.
        """
        return self.clamp(self.round(walk_value))

    def generate(self, current: float, draw) -> float:
        """One step of the walk, clamped to the realistic band.

        **Not rounded.** The rounding to `decimals` happens only when a value is
        reported, because rounding the *state* destroys the walk: body
        temperature moves by ~0.02 C per second, so a state rounded to 0.1 C
        would round straight back to where it started, every second, forever -
        a flat line at 36.8. Keeping the state continuous and rounding on the
        way out gives a thermometer that reads 36.8 for a while and then ticks
        to 36.9, which is what a real one does.
        """
        return self.clamp_walk(current + (draw() * 2.0 - 1.0) * self.step)


#: The four scalar sensors `POST /sensor/data` accepts, in contract order.
SCALARS: dict[str, ScalarSpec] = {
    # Human body temperature: a slow wander of a few tenths of a degree.
    "temperature": ScalarSpec(
        sensor_type="temperature",
        unit="celsius",
        low=25.0,
        high=45.0,
        walk_low=35.8,
        walk_high=38.2,
        start=36.8,
        step=0.02,
        decimals=1,
    ),
    # Peripheral oxygen saturation: an integer-ish percentage that dips and
    # recovers; never below 90 in the generated band, which is a long way from
    # the protocol floor of 50.
    "spo2": ScalarSpec(
        sensor_type="spo2",
        unit="percent",
        low=50.0,
        high=100.0,
        walk_low=94.0,
        walk_high=99.0,
        start=97.0,
        step=0.15,
        decimals=1,
    ),
    # Pulse: beats per minute, walking slowly.
    "pulse": ScalarSpec(
        sensor_type="pulse",
        unit="bpm",
        low=20.0,
        high=250.0,
        walk_low=55.0,
        walk_high=105.0,
        start=72.0,
        step=0.4,
        decimals=0,
    ),
    # Motion: an arbitrary-unit activity level. The walk is bounded at 0, which
    # is the protocol floor as well, so this one is clamped rather than banded.
    "motion": ScalarSpec(
        sensor_type="motion",
        unit="a.u.",
        low=0.0,
        high=100.0,
        walk_low=0.0,
        walk_high=40.0,
        start=4.0,
        step=1.5,
        decimals=2,
    ),
}

SENSOR_TYPES: tuple[str, ...] = tuple(SCALARS)

__all__ = [
    "ECG_MAX_CHUNK_INDEX",
    "ECG_MAX_SAMPLE_RATE_HZ",
    "ECG_MAX_SAMPLES_PER_CHUNK",
    "ECG_MIN_SAMPLE_RATE_HZ",
    "ECG_SAMPLE_MV_LIMIT",
    "ECG_TARGET_SAMPLE_RATE_HZ",
    "SCALARS",
    "SENSOR_TYPES",
    "ScalarSpec",
]
