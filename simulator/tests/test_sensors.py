"""The generated scalars must be inside the Phase 2 ranges, always.

The interesting assertions here are not "36.8 is between 25 and 45" - they are
the ones that would catch a walk drifting out of range, a step that is too big
to be believable, or a seed that happens to walk into the boundary and stays
there.
"""

from __future__ import annotations

import pytest

from simulator.ranges import SCALARS, SENSOR_TYPES, ScalarSpec
from simulator.sensors import ScalarSensorSet

#: long enough that a walk with a buggy clamp has time to escape
STEPS = 2000


@pytest.mark.parametrize("sensor_type", SENSOR_TYPES)
def test_every_generated_value_is_inside_the_protocol_range(sensor_type: str) -> None:
    spec = SCALARS[sensor_type]
    sensors = ScalarSensorSet(seed=1234)
    sensor = sensors.sensor(sensor_type)

    for _ in range(STEPS):
        reading = sensor.next()
        assert spec.low <= reading.value <= spec.high, (
            f"{sensor_type} left the legal range: {reading.value}"
        )
        assert reading.unit == spec.unit


@pytest.mark.parametrize("sensor_type", SENSOR_TYPES)
def test_values_stay_inside_the_realistic_band(sensor_type: str) -> None:
    """The tighter band: a value at the protocol boundary would look absurd.

    A body temperature of 45.0 C or an SpO2 of 50 % is legal for the API and
    meaningless as data, so the walk must never go near them.
    """
    spec = SCALARS[sensor_type]
    sensors = ScalarSensorSet(seed=99)
    sensor = sensors.sensor(sensor_type)

    for _ in range(STEPS):
        assert spec.walk_low <= sensor.next().value <= spec.walk_high


@pytest.mark.parametrize("sensor_type", SENSOR_TYPES)
def test_a_value_never_jumps_by_more_than_one_step(sensor_type: str) -> None:
    """Drift, not noise: two consecutive samples must be close together."""
    spec = SCALARS[sensor_type]
    sensors = ScalarSensorSet(seed=7)
    sensor = sensors.sensor(sensor_type)

    previous = sensor.next().value
    for _ in range(STEPS):
        current = sensor.next().value
        # Rounding can add half a decimal of error on a step boundary.
        assert abs(current - previous) <= spec.step + 10 ** (-spec.decimals), (
            f"{sensor_type} jumped from {previous} to {current}"
        )
        previous = current


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5, 12345, 987654])
def test_the_band_holds_for_many_seeds(seed: int) -> None:
    """A clamp that only fires for one seed is a bug, not a lucky run."""
    sensors = ScalarSensorSet(seed=seed)
    for _ in range(STEPS):
        for reading in sensors.sample_all():
            spec = SCALARS[reading.sensor_type]
            assert spec.low <= reading.value <= spec.high


def test_each_sensor_has_a_distinct_unit_and_a_sane_start() -> None:
    units = {spec.unit for spec in SCALARS.values()}
    assert units == {"celsius", "percent", "bpm", "a.u."}
    for name, spec in SCALARS.items():
        assert spec.walk_low <= spec.start <= spec.walk_high, name
        # `walk_low` may equal `low` - motion's arbitrary unit genuinely bottoms
        # out at zero - but the band may never be wider than the legal range.
        assert spec.low <= spec.walk_low <= spec.walk_high <= spec.high, name
        assert spec.walk_high < spec.high, name
        assert spec.step > 0, name


def test_the_set_actually_moves() -> None:
    """A walk that never changes would pass every range test and be useless.

    Sampled long enough for the slowest sensor: temperature moves ~0.02 C per
    second and reports to 0.1 C, so it needs a few dozen samples before the
    reading ticks.
    """
    sensors = ScalarSensorSet(seed=5)
    for sensor_type in SENSOR_TYPES:
        sensor = sensors.sensor(sensor_type)
        values = {sensor.next().value for _ in range(200)}
        assert len(values) > 1, f"{sensor_type} never changed"


def test_the_walk_is_continuous_even_when_the_reading_is_not() -> None:
    """The reading may repeat; the state underneath it must keep drifting.

    This is the regression test for a walk that rounded its own state and froze
    at 36.8 forever.
    """
    sensors = ScalarSensorSet(seed=5)
    sensor = sensors.sensor("temperature")

    walks = []
    for _ in range(50):
        sensor.next()
        walks.append(sensor.walk_value)

    assert len(set(walks)) > 1
    assert all(walks[i] != walks[i + 1] for i in range(len(walks) - 1))
    # And the reading is that state, rounded.
    assert sensor.value == round(walks[-1], SCALARS["temperature"].decimals)


def test_clamp_and_round_are_boundaries_not_suggestions() -> None:
    spec = ScalarSpec(
        sensor_type="temperature",
        unit="celsius",
        low=25.0,
        high=45.0,
        walk_low=35.0,
        walk_high=38.0,
        start=36.5,
        step=1.0,
        decimals=1,
    )
    assert spec.clamp(99.0) == 45.0
    assert spec.clamp(-99.0) == 25.0
    assert spec.clamp_walk(99.0) == 38.0
    assert spec.clamp_walk(-99.0) == 35.0
    assert spec.round(36.549) == 36.5


def test_sample_all_returns_one_reading_per_sensor() -> None:
    readings = ScalarSensorSet(seed=1).sample_all()
    assert [reading.sensor_type for reading in readings] == list(SENSOR_TYPES)
