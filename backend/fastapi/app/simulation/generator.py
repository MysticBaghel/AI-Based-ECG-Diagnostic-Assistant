"""Synthesises the ECG and scalar samples for one simulated scenario.

This is deliberately a *stream*: `chunk(start, seconds)` returns exactly that
slice of the timeline, so a long run never holds more than one chunk of samples
in memory and the chunks join without a seam. Beats are scheduled at absolute
times on the scenario clock, so a T wave that crosses a chunk boundary is
produced in both chunks with the right shape.

The waveform is a sum of Gaussian bumps - one per P/QRS/T component - laid out
on a beat timeline whose intervals the scenario controls (steady, jittered,
irregular, or with ectopic beats). Amplitudes are in millivolts, in the range a
real single lead produces (R wave ~1 mV), so nothing approaches the protocol's
±20 mV limit.

Screening aid, not a medical diagnosis.
"""

from __future__ import annotations

import math
import random

from app.simulation.scenarios import Scenario, Wave

#: The rate the built-in simulator streams at. 200 Hz matches the CLI simulator
#: and the limits in `app/schemas.py`; the dashboard re-renders at whatever rate
#: the chunks declare.
SAMPLE_RATE_HZ = 200

#: A beat may still contribute this long after its R wave (the T wave is broad).
_BEAT_TAIL_SECONDS = 0.75
#: Baseline wander: breathing (~0.25 Hz) and slow electrode drift (~0.05 Hz).
_WANDER_AMPLITUDE_MV = 0.03
_DRIFT_AMPLITUDE_MV = 0.015
#: A Gaussian is numerically zero beyond four widths.
_GAUSS_CUTOFF = 4.0
#: Hard stop well inside the API's ±20 mV, whatever a template sums to.
_SAMPLE_LIMIT_MV = 19.0


class ScenarioGenerator:
    """Pulls consecutive slices of one scenario's ECG timeline."""

    def __init__(
        self,
        scenario: Scenario,
        *,
        sample_rate_hz: int = SAMPLE_RATE_HZ,
        seed: int | None = None,
    ) -> None:
        self.scenario = scenario
        self.rate = int(sample_rate_hz)
        self._rng = random.Random(seed)
        self._beats: list[tuple[float, tuple[Wave, ...]]] = []
        self._next_beat_s = 0.20
        self._beat_number = 0
        self._previous_was_pvc = False
        self._last_rr_seconds = 60.0 / scenario.heart_rate_bpm
        # Fixed per run, so the fibrillatory waves continue across a chunk
        # boundary instead of restarting with a phase step.
        self._fibrillation_phases = tuple(
            self._rng.uniform(0.0, 2.0 * math.pi) for _ in range(3)
        )

    # -- beat scheduling ---------------------------------------------------

    def _next_rr(self, *, after_pvc: bool) -> float:
        """One RR interval, in seconds, before any prematurity adjustment."""
        scenario = self.scenario
        if scenario.irregular_rr is not None:
            low, high = scenario.irregular_rr
            rr = self._rng.uniform(low, high)
        else:
            mean = 60.0 / scenario.heart_rate_bpm
            rr = self._rng.gauss(mean, mean * max(0.0, scenario.rr_variability))
            rr = min(max(rr, 0.30), 2.40)
        if after_pvc:
            # The compensatory pause that follows a ventricular ectopic beat.
            rr *= 1.40
        return rr

    def _schedule_until(self, t_end: float) -> None:
        while self._next_beat_s < t_end:
            self._beat_number += 1
            is_pvc = (
                self.scenario.pvc_every is not None
                and self._beat_number % self.scenario.pvc_every == 0
            )
            rr = self._next_rr(after_pvc=self._previous_was_pvc)
            if is_pvc:
                # Premature: the coupling interval before the ectopic is short.
                rr *= 0.62
            self._beats.append(
                (self._next_beat_s, self.scenario.waves(pvc=is_pvc))
            )
            self._previous_was_pvc = is_pvc
            self._last_rr_seconds = rr
            self._next_beat_s += rr

    # -- the stream --------------------------------------------------------

    def chunk(self, start_seconds: float, chunk_seconds: float) -> list[float]:
        """The samples for `[start_seconds, start_seconds + chunk_seconds)`."""
        if chunk_seconds <= 0:
            raise ValueError("chunk_seconds must be positive")

        count = int(round(chunk_seconds * self.rate))
        end_seconds = start_seconds + chunk_seconds
        self._schedule_until(end_seconds + _BEAT_TAIL_SECONDS)

        samples = [0.0] * count
        for centre, waves in self._beats:
            if centre + _BEAT_TAIL_SECONDS < start_seconds:
                continue
            if centre - _BEAT_TAIL_SECONDS > end_seconds:
                break
            for offset, width, amplitude in waves:
                wave_centre = centre + offset
                span = _GAUSS_CUTOFF * width
                if wave_centre + span < start_seconds or wave_centre - span > end_seconds:
                    continue
                # ceil/floor on the exact cutoff - not int() with slack - so a
                # chunk boundary cannot include or drop a tail that the same
                # signal generated in one slice would treat differently.
                first = max(
                    0, math.ceil((wave_centre - span - start_seconds) * self.rate)
                )
                last = min(
                    count - 1,
                    math.floor((wave_centre + span - start_seconds) * self.rate),
                )
                for index in range(first, last + 1):
                    delta = start_seconds + index / self.rate - wave_centre
                    samples[index] += amplitude * math.exp(-0.5 * (delta / width) ** 2)

        fibrillation_mv = self.scenario.fibrillation_mv
        phase_a, phase_b, phase_c = self._fibrillation_phases
        tau = 2.0 * math.pi
        for index in range(count):
            t = start_seconds + index / self.rate
            value = samples[index]
            value += _WANDER_AMPLITUDE_MV * math.sin(tau * 0.25 * t)
            value += _DRIFT_AMPLITUDE_MV * math.sin(tau * 0.05 * t)
            if fibrillation_mv:
                # Three incommensurate components between 5 and 8 Hz: the fine,
                # irregular baseline of atrial fibrillation.
                value += fibrillation_mv * (
                    0.45 * math.sin(tau * 5.3 * t + phase_a)
                    + 0.35 * math.sin(tau * 6.7 * t + phase_b)
                    + 0.20 * math.sin(tau * 8.1 * t + phase_c)
                )
            samples[index] = round(
                min(_SAMPLE_LIMIT_MV, max(-_SAMPLE_LIMIT_MV, value)), 6
            )

        # Beats older than this chunk can no longer contribute to a later one.
        while self._beats and self._beats[0][0] + _BEAT_TAIL_SECONDS < start_seconds:
            self._beats.pop(0)

        return samples

    # -- what the vitals show ---------------------------------------------

    def instantaneous_heart_rate(self) -> float:
        """60 / the most recent RR interval - what a pulse sensor would show.

        On an irregular rhythm this moves beat to beat instead of reporting the
        mean, which is the point of simulating one.
        """
        if self._last_rr_seconds <= 0:
            return self.scenario.heart_rate_bpm
        return 60.0 / self._last_rr_seconds
