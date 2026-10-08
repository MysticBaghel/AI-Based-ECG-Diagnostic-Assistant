"""Scalar sensor generation: temperature, SpO2, pulse and motion.

Each sensor is an independent bounded random walk. A random walk is the right
shape for this because real vitals drift: they do not jump from 36.8 to 39.0
between two consecutive seconds, and the dashboard's live chart should look like
a vitals monitor rather than noise.

Three properties are guaranteed by construction, and each one is a test:

1. every value is inside the Phase 2 protocol range (`ranges.ScalarSpec.low/high`);
2. every value is inside the tighter realistic band, so a clamp never fires;
3. successive values differ by at most one step, which is what makes the curve
   look like a body rather than a random number generator.

Screening aid, not a medical diagnosis.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from simulator.ranges import SCALARS, ScalarSpec


@dataclass
class ScalarReading:
    """One reading, ready to be serialised as a `POST /sensor/data` body."""

    sensor_type: str
    value: float
    unit: str


class ScalarSensor:
    """A bounded random walk for one sensor type."""

    def __init__(self, spec: ScalarSpec, *, rng: random.Random) -> None:
        self.spec = spec
        self._rng = rng
        # The walk itself is continuous; `value` is that walk rounded to the
        # resolution of the reading. Rounding the *state* would freeze the walk
        # (see `ScalarSpec.generate`), so the two are kept apart on purpose.
        self._walk = spec.start
        self._value = spec.report(spec.start)

    @property
    def value(self) -> float:
        """The last value reported, at the sensor's own resolution."""
        return self._value

    @property
    def walk_value(self) -> float:
        """The underlying continuous signal (no rounding). Tests use this."""
        return self._walk

    def next(self) -> ScalarReading:
        """Advance the walk by one sample and return it."""
        self._walk = self.spec.generate(self._walk, self._rng.random)
        self._value = self.spec.report(self._walk)
        return ScalarReading(self.spec.sensor_type, self._value, self.spec.unit)

    def force(self, value: float) -> ScalarReading:
        """Set the walk to an exact value (used by tests, not by the loop)."""
        self._walk = self.spec.clamp_walk(value)
        self._value = self.spec.report(self._walk)
        return ScalarReading(self.spec.sensor_type, self._value, self.spec.unit)


class ScalarSensorSet:
    """All four sensors of one simulated device."""

    def __init__(self, *, seed: int | None = None) -> None:
        # One RNG for the whole set. A single seed then reproduces an entire
        # run, including the ECG generator's decisions.
        self.rng = random.Random(seed)
        self.sensors: dict[str, ScalarSensor] = {
            sensor_type: ScalarSensor(spec, rng=self.rng)
            for sensor_type, spec in SCALARS.items()
        }

    def sample_all(self) -> list[ScalarReading]:
        """One reading from each sensor, in a stable (contract) order."""
        return [sensor.next() for sensor in self.sensors.values()]

    def sensor(self, sensor_type: str) -> ScalarSensor:
        return self.sensors[sensor_type]

    def is_within_band(self) -> bool:
        """True when every sensor's *walk* is inside its realistic band.

        Checks the continuous state, not the rounded reading: a reading can sit
        on the band edge for a while by construction, the state cannot.
        """
        return all(
            sensor.spec.walk_low <= sensor.walk_value <= sensor.spec.walk_high
            for sensor in self.sensors.values()
        )


__all__ = ["ScalarReading", "ScalarSensor", "ScalarSensorSet"]
