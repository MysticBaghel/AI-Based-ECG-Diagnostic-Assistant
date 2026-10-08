"""ECG sample sources: a real MIT-BIH record, or a synthetic one.

`ECGSource` is a *stream*, not a list: it hands out a few seconds of samples at
a time and can be pulled forever. That matters, because a 30-second smoke run at
200 Hz is 6 000 samples but a one-hour session is 720 000 - nothing here should
try to hold a whole session in memory.

Two implementations:

* `SyntheticECGSource` - a PQRST generator written in plain Python. It has no
  dependency beyond the standard library, so the simulator runs offline, on a
  laptop with no network, and in CI.
* `WFDBECGSource` (in `mitbih.py`) - real MIT-BIH records through the `wfdb`
  library, which is the point of the exercise. When the download or the library
  is unavailable the simulator falls back to the synthetic source instead of
  failing.

Screening aid, not a medical diagnosis. The synthetic waveform is a teaching
signal, not a patient.
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterator
from dataclasses import dataclass

#: MIT-BIH records are 30 minutes long; a few minutes is plenty for a demo run.
DEFAULT_SOURCE_FRAMES = 20_000

#: plausible power-line frequencies; 50 Hz in India/EU, 60 Hz in the US
MAINS_HZ = 50.0
MAINS_AMPLITUDE_MV = 0.05
#: breathing artefact and slow electrode drift
WANDER_HZ = 0.25
WANDER_AMPLITUDE_MV = 0.10
DRIFT_HZ = 0.05
DRIFT_AMPLITUDE_MV = 0.04
#: a movement artefact: rare, brief, and large
SPIKE_PROBABILITY = 0.0015
SPIKE_AMPLITUDE_MV = 2.0


@dataclass(frozen=True)
class NoiseConfig:
    """What `--noise` turns on. Each part can be switched off on its own."""

    mains_hum: bool = True
    baseline_wander: bool = True
    random_spikes: bool = True

    @property
    def enabled(self) -> bool:
        return self.mains_hum or self.baseline_wander or self.random_spikes

    @classmethod
    def all(cls) -> "NoiseConfig":
        return cls(True, True, True)

    @classmethod
    def none(cls) -> "NoiseConfig":
        return cls(False, False, False)


class NoiseLayer:
    """The `--noise` of a real front-end, applied at the *source* rate.

    Three artefacts, which is what an actual single-lead acquisition picks up:

    * **baseline wander** - breathing (0.25 Hz) and slow electrode drift
      (0.05 Hz), a slow sinusoid;
    * **mains hum** - the power line at 50 Hz;
    * **random spikes** - a movement artefact: rare, brief and relatively big.

    It lives here, applied while the raw signal is produced, and not in the
    resampler. That is both more honest - a real front-end picks up hum before
    the rate is changed, so the resampler band-limits it - and much faster: the
    resampler would otherwise evaluate four `sin` calls per interpolated sample
    instead of per source sample, which is measurable at 200 Hz.
    """

    def __init__(self, config: NoiseConfig, *, rate_hz: float, seed: int | None = None) -> None:
        self.config = config
        self.rate_hz = float(rate_hz)
        self._rng = random.Random(seed)

    def at(self, index: int) -> float:
        """The noise added to source sample `index`."""
        t = index / self.rate_hz
        noise = 0.0
        if self.config.baseline_wander:
            noise += WANDER_AMPLITUDE_MV * math.sin(2.0 * math.pi * WANDER_HZ * t)
            noise += DRIFT_AMPLITUDE_MV * math.sin(2.0 * math.pi * DRIFT_HZ * t)
        if self.config.mains_hum:
            noise += MAINS_AMPLITUDE_MV * math.sin(2.0 * math.pi * MAINS_HZ * t)
        if self.config.random_spikes and self._rng.random() < SPIKE_PROBABILITY:
            noise += self._rng.choice((-1.0, 1.0)) * self._rng.uniform(0.5, SPIKE_AMPLITUDE_MV)
        return noise


class ECGSource:
    """Base class: a named stream of mV samples at a fixed rate."""

    #: where the samples came from, for the log line and the summary file
    source_name = "unknown"
    #: the record/lead this stream is derived from
    record_name = "n/a"

    def __init__(
        self,
        *,
        sample_rate_hz: float,
        frames: int,
        noise: NoiseLayer | None = None,
    ) -> None:
        self.sample_rate_hz = float(sample_rate_hz)
        self.frames = int(frames)
        self.noise = noise
        self._delivered = 0

    def enable_noise(self, config: NoiseConfig, *, seed: int | None = None) -> None:
        """Turn on `--noise`, now that the sample rate is known.

        A source learns its own rate while loading (a MIT-BIH record declares
        360 Hz in its header), so the noise layer is built here rather than by
        the caller, which would have to guess the rate first.
        """
        if config.enabled:
            self.noise = NoiseLayer(config, rate_hz=self.sample_rate_hz, seed=seed)

    # -- the part subclasses implement ------------------------------------

    def _next_frame(self) -> Iterator[float]:
        """The next frame of samples, at `sample_rate_hz`. Never empty.

        A *generator* on purpose. The resampler pulls source samples one at a
        time, so a frame that builds all of its samples eagerly computes values
        nobody reads - and a 200-sample frame of PQRST arithmetic is the most
        expensive thing in the simulator. Yielding lazily makes the cost
        proportional to what is actually used.
        """
        raise NotImplementedError

    # -- the streaming interface ------------------------------------------

    @property
    def total_samples(self) -> int | None:
        """How many samples this source will produce, or None if it loops.

        The resampler needs this number to know its output length exactly, so a
        source that can end should say so.
        """
        return None

    @property
    def exhausted(self) -> bool:
        """True once the requested number of frames has been produced."""
        return self._delivered >= self.frames

    def samples(self) -> Iterator[float]:
        """Yield samples one at a time until the source is exhausted.

        `--noise` is applied here, to every raw sample, before the resampler
        sees it.
        """
        index = 0
        while not self.exhausted:
            # `_next_frame` is a generator, so the frame counter advances only
            # once the frame has actually been consumed. A generator that derives
            # its values from `self._delivered` (the tests do, to build a ramp)
            # then sees the right frame number.
            frame = self._next_frame()
            if self.noise is None:
                for value in frame:
                    yield value
                    index += 1
            else:
                for value in frame:
                    yield value + self.noise.at(index)
                    index += 1
            self._delivered += 1

    def take(self, count: int) -> list[float]:
        """Up to `count` samples - fewer only when the source runs out."""
        out: list[float] = []
        for value in self.samples():
            out.append(value)
            if len(out) >= count:
                break
        return out


class SyntheticECGSource(ECGSource):
    """A PQRST generator: normal sinus rhythm, realistic amplitudes.

    Each beat is the sum of five Gaussian bumps - P, Q, R, S, T - laid out on a
    timeline whose beat-to-beat interval jitters slightly, which is what makes
    the trace look like a heart and not a metronome. Amplitudes are in
    millivolts, in the same range as a real lead II surface ECG (R wave ~1 mV),
    so the +/-20 mV protocol limit is never in sight.

    `frames` frames of `frame_seconds` each are produced lazily, so the class is
    as happy generating an hour as it is two seconds.
    """

    source_name = "synthetic"
    record_name = "synthetic-sinus"

    #: (centre in seconds relative to the R wave, width, amplitude in mV)
    #: a QRS complex is narrow (~80 ms), a T wave is broad (~160 ms)
    WAVES: tuple[tuple[float, float, float], ...] = (
        (-0.20, 0.025, 0.10),  # P
        (-0.025, 0.010, -0.12),  # Q
        (0.0, 0.011, 1.05),  # R
        (0.028, 0.012, -0.22),  # S
        (0.22, 0.045, 0.28),  # T
    )

    def __init__(
        self,
        *,
        sample_rate_hz: float = 200.0,
        frames: int = DEFAULT_SOURCE_FRAMES,
        frame_seconds: float = 1.0,
        heart_rate_bpm: float = 72.0,
        seed: int | None = None,
        noise: NoiseLayer | NoiseConfig | None = None,
        noise_seed: int | None = None,
    ) -> None:
        super().__init__(sample_rate_hz=sample_rate_hz, frames=frames)
        if isinstance(noise, NoiseLayer):
            self.noise = noise
        elif isinstance(noise, NoiseConfig):
            self.enable_noise(noise, seed=seed if noise_seed is None else noise_seed)
        self._rng = random.Random(seed)
        self._frame_seconds = float(frame_seconds)
        self._frame_samples = max(1, int(round(self._frame_seconds * self.sample_rate_hz)))
        self._heart_rate = float(heart_rate_bpm)

        # Absolute time of the next R wave, in seconds, and the current beat's
        # interval. Both advance as beats are emitted.
        self._next_beat = 0.35
        self._beat_interval = 60.0 / self._heart_rate
        self._elapsed = 0.0

    # -- bounds ------------------------------------------------------------

    @property
    def total_samples(self) -> int:
        """`frames` frames of `frame_seconds` at `sample_rate_hz`."""
        return self.frames * self._frame_samples

    # -- beat bookkeeping --------------------------------------------------

    def _schedule_next_beat(self) -> None:
        """R-R interval with slight respiratory sinus arrhythmia."""
        jitter = 1.0 + self._rng.uniform(-0.04, 0.04)
        self._beat_interval = (60.0 / self._heart_rate) * jitter
        self._next_beat += self._beat_interval

    def _amplitude_at(self, t: float) -> float:
        """The clean ECG value in mV at absolute time `t`.

        Noise (wander, hum, spikes) is deliberately *not* here: it belongs to
        `signal.py`, so the same generator is used with and without `--noise`
        and the difference is one line at the end of the pipeline.
        """
        value = 0.0
        for offset, width, amplitude in self.WAVES:
            delta = t - (self._next_beat + offset)
            if abs(delta) < 6.0 * width:  # outside 6 sigma a Gaussian is ~0
                value += amplitude * math.exp(-0.5 * (delta / width) ** 2)
        return value

    # -- ECGSource ---------------------------------------------------------

    def _next_frame(self) -> Iterator[float]:
        """One second of PQRST samples, computed one sample at a time."""
        for _ in range(self._frame_samples):
            t = self._elapsed
            if t >= self._next_beat + 0.30:
                # 0.30 s after the R wave the beat is over; start the next one.
                self._schedule_next_beat()
            yield self._amplitude_at(t)
            self._elapsed += 1.0 / self.sample_rate_hz


__all__ = [
    "DEFAULT_SOURCE_FRAMES",
    "ECGSource",
    "NoiseConfig",
    "NoiseLayer",
    "SyntheticECGSource",
]
