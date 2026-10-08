"""The simulator's limits must equal the API's limits.

This is the test that keeps two copies of a number honest. `simulator/ranges.py`
restates the per-sensor ranges and the ECG limits from
`backend/fastapi/app/schemas.py`; if someone widens a range in the service, this
test fails rather than letting the simulator quietly generate 42.0 C readings
that answer 200 instead of 422 - or, worse, 46.0 C readings that answer 422.

It skips itself, with a reason, when the API is not importable (a simulator-only
install). `simulator/requirements-dev.txt` installs it, and the end-to-end run
in `docs/phase-3-smoke-test.md` uses it.
"""

from __future__ import annotations

import pytest

from simulator import ranges

api_schemas = pytest.importorskip(
    "app.schemas",
    reason="the Phase 2 FastAPI app is not installed; "
    "install simulator/requirements-dev.txt to check the ranges against it",
)
api_config = pytest.importorskip("app.core.config")


def test_the_scalar_ranges_match_the_api() -> None:
    api_rules = api_schemas.SENSOR_RULES
    assert set(api_rules) == set(ranges.SCALARS), "the sensor types themselves differ"

    for sensor_type, (low, high, unit) in api_rules.items():
        spec = ranges.SCALARS[sensor_type]
        assert (spec.low, spec.high) == (low, high), (
            f"{sensor_type}: simulator {spec.low}-{spec.high} vs API {low}-{high}"
        )
        assert spec.unit == unit, f"{sensor_type}: {spec.unit!r} vs {unit!r}"


def test_the_unit_aliases_the_simulator_sends_are_accepted() -> None:
    """Whatever the simulator puts in `unit` must be a key the API normalises."""
    for sensor_type, spec in ranges.SCALARS.items():
        aliases = api_schemas.UNIT_ALIASES[sensor_type]
        assert spec.unit in aliases, f"the API would reject unit {spec.unit!r}"
        assert aliases[spec.unit] == spec.unit


def test_the_generated_band_is_inside_the_api_range() -> None:
    for sensor_type, spec in ranges.SCALARS.items():
        low, high, _ = api_schemas.SENSOR_RULES[sensor_type]
        assert low <= spec.walk_low <= spec.walk_high <= high, sensor_type


def test_the_ecg_limits_match_the_api() -> None:
    assert ranges.ECG_SAMPLE_MV_LIMIT == api_schemas.MAX_ECG_SAMPLE_MV
    assert ranges.ECG_MIN_SAMPLE_RATE_HZ == api_config.MIN_ECG_SAMPLE_RATE_HZ
    assert ranges.ECG_MAX_SAMPLE_RATE_HZ == api_config.MAX_ECG_SAMPLE_RATE_HZ
    assert ranges.ECG_MAX_SAMPLES_PER_CHUNK == api_config.MAX_ECG_SAMPLES_PER_CHUNK


def test_the_default_ecg_rate_is_inside_the_api_range() -> None:
    assert (
        ranges.ECG_MIN_SAMPLE_RATE_HZ
        <= ranges.ECG_TARGET_SAMPLE_RATE_HZ
        <= ranges.ECG_MAX_SAMPLE_RATE_HZ
    )


def test_the_chunk_index_bound_matches_the_api_schema() -> None:
    """`chunk_index` is `ge=0, le=1_000_000` in the API; keep the copy honest."""
    field = api_schemas.ECGChunkRequest.model_fields["chunk_index"]
    upper = next(
        meta.le for meta in field.metadata if getattr(meta, "le", None) is not None
    )
    assert upper == ranges.ECG_MAX_CHUNK_INDEX


def test_an_api_legal_value_passes_the_api_model_for_every_sensor() -> None:
    """Belt and braces: build the real request model from generated values.

    This is stronger than comparing numbers - it runs the simulator's output
    through the API's own Pydantic validator, which is the thing that answers
    422 in production.
    """
    from simulator.sensors import ScalarSensorSet

    sensors = ScalarSensorSet(seed=2026)
    for reading in sensors.sample_all():
        model = api_schemas.SensorDataRequest(
            session_id="11111111-1111-4111-8111-111111111111",
            sensor_type=reading.sensor_type,
            value=reading.value,
            unit=reading.unit,
        )
        assert model.unit == reading.unit
