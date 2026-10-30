"""Deterministic ECG signal processing - pure Python, no NumPy.

What this module does, in order:

1. validates the chunk stream (sample rate, duration, missing/non-finite values);
2. removes baseline wander (0.5 Hz high-pass), power-line hum (50/60 Hz notch)
   and high-frequency noise (40 Hz low-pass);
3. detects R-peaks on a 5-15 Hz band-passed copy using a derivative-square
   integrator and a refractory window;
4. reports heart rate, RR intervals, RMSSD, pNN50 and a transparent signal
   quality score.

It does **not** diagnose anything. When the signal is unusable the measurements
are withheld rather than guessed, and the reasons are returned so the UI can
explain why.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import mean, median

#: Samples outside this range are treated as clipped/saturated (API limit is 20 mV).
CLIP_MV = 19.5
#: Below this standard deviation the trace is effectively a flat line.
FLATLINE_STD_MV = 0.015
#: Physiological RR bounds: 240 bpm down to 24 bpm.
MIN_RR_SECONDS = 0.25
MAX_RR_SECONDS = 2.5
#: A detection candidate must be at least this far from the previous one.
REFRACTORY_SECONDS = 0.25


@dataclass
class Biquad:
    """A second-order IIR section in direct form I."""

    b0: float
    b1: float
    b2: float
    a1: float
    a2: float

    def process(self, samples: list[float]) -> list[float]:
        out: list[float] = []
        x1 = x2 = y1 = y2 = 0.0
        for value in samples:
            y = (
                self.b0 * value
                + self.b1 * x1
                + self.b2 * x2
                - self.a1 * y1
                - self.a2 * y2
            )
            out.append(y)
            x2, x1 = x1, value
            y2, y1 = y1, y
        return out


def _normalise(b0, b1, b2, a0, a1, a2) -> Biquad:
    return Biquad(b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0)


def highpass(sample_rate_hz: float, cutoff_hz: float, q: float = 0.707) -> Biquad:
    w0 = 2.0 * math.pi * cutoff_hz / sample_rate_hz
    cos_w0 = math.cos(w0)
    alpha = math.sin(w0) / (2.0 * q)
    b0 = (1.0 + cos_w0) / 2.0
    b1 = -(1.0 + cos_w0)
    b2 = (1.0 + cos_w0) / 2.0
    a0 = 1.0 + alpha
    a1 = -2.0 * cos_w0
    a2 = 1.0 - alpha
    return _normalise(b0, b1, b2, a0, a1, a2)


def lowpass(sample_rate_hz: float, cutoff_hz: float, q: float = 0.707) -> Biquad:
    w0 = 2.0 * math.pi * cutoff_hz / sample_rate_hz
    cos_w0 = math.cos(w0)
    alpha = math.sin(w0) / (2.0 * q)
    b0 = (1.0 - cos_w0) / 2.0
    b1 = 1.0 - cos_w0
    b2 = (1.0 - cos_w0) / 2.0
    a0 = 1.0 + alpha
    a1 = -2.0 * cos_w0
    a2 = 1.0 - alpha
    return _normalise(b0, b1, b2, a0, a1, a2)


def notch(sample_rate_hz: float, frequency_hz: float, q: float = 30.0) -> Biquad:
    w0 = 2.0 * math.pi * frequency_hz / sample_rate_hz
    cos_w0 = math.cos(w0)
    alpha = math.sin(w0) / (2.0 * q)
    b0 = 1.0
    b1 = -2.0 * cos_w0
    b2 = 1.0
    a0 = 1.0 + alpha
    a1 = -2.0 * cos_w0
    a2 = 1.0 - alpha
    return _normalise(b0, b1, b2, a0, a1, a2)


def filtfilt(section: Biquad, samples: list[float]) -> list[float]:
    """Forward-backward filtering: zero phase, no visible peak shift."""
    forward = section.process(samples)
    backward = section.process(forward[::-1])
    return backward[::-1]


def moving_average(samples: list[float], window: int) -> list[float]:
    window = max(1, window)
    if window == 1:
        return list(samples)
    out: list[float] = []
    total = 0.0
    queue: list[float] = []
    for value in samples:
        queue.append(value)
        total += value
        if len(queue) > window:
            total -= queue.pop(0)
        out.append(total / len(queue))
    return out


def derivative(samples: list[float]) -> list[float]:
    if not samples:
        return []
    out = [0.0]
    for index in range(1, len(samples)):
        out.append(samples[index] - samples[index - 1])
    return out


@dataclass
class Quality:
    score: float
    level: str
    usable: bool
    reasons: list[str] = field(default_factory=list)
    flatline: bool = False
    clipping: bool = False
    missing_samples: int = 0


@dataclass
class Measurement:
    heart_rate_bpm: float | None = None
    rr_intervals_ms: list[float] = field(default_factory=list)
    rr_mean_ms: float | None = None
    rr_std_ms: float | None = None
    rmssd_ms: float | None = None
    pnn50_percent: float | None = None
    beats_detected: int = 0
    r_peak_seconds: list[float] = field(default_factory=list)


def _median(values: list[float]) -> float:
    return median(values) if values else 0.0


def _rr_metrics(peaks: list[int], sample_rate_hz: float) -> tuple[list[float], Measurement]:
    rr = [
        (peaks[index + 1] - peaks[index]) / sample_rate_hz * 1000.0
        for index in range(len(peaks) - 1)
    ]
    # Keep only physiological intervals; an ectopic-like gap is a quality
    # signal, not a heart rate.
    rr = [value for value in rr if MIN_RR_SECONDS * 1000 <= value <= MAX_RR_SECONDS * 1000]
    measurement = Measurement(beats_detected=len(peaks), rr_intervals_ms=rr)
    if not rr:
        return rr, measurement

    measurement.rr_mean_ms = mean(rr)
    measurement.rr_std_ms = math.sqrt(
        sum((value - measurement.rr_mean_ms) ** 2 for value in rr) / len(rr)
    )
    diffs = [rr[index + 1] - rr[index] for index in range(len(rr) - 1)]
    if diffs:
        measurement.rmssd_ms = math.sqrt(sum(d * d for d in diffs) / len(diffs))
        measurement.pnn50_percent = (
            sum(1 for d in diffs if abs(d) > 50.0) / len(diffs) * 100.0
        )
    if measurement.rr_mean_ms > 0:
        measurement.heart_rate_bpm = 60000.0 / measurement.rr_mean_ms
    measurement.r_peak_seconds = [peak / sample_rate_hz for peak in peaks]
    return rr, measurement


def _detect_peaks(
    samples: list[float], sample_rate_hz: float
) -> list[int]:
    """R-peak indices from a 5-15 Hz band-passed derivative-square envelope."""
    if len(samples) < int(sample_rate_hz * 1.0):
        return []

    band = filtfilt(highpass(sample_rate_hz, 5.0), samples)
    band = filtfilt(lowpass(sample_rate_hz, 15.0), band)
    diff = derivative(band)
    squared = [value * value for value in diff]
    envelope = moving_average(squared, max(1, int(sample_rate_hz * 0.12)))

    ordered = sorted(envelope)
    high = ordered[min(len(ordered) - 1, int(len(ordered) * 0.995))]
    if high <= 0:
        return []

    refractory = max(1, int(REFRACTORY_SECONDS * sample_rate_hz))
    for factor in (0.22, 0.14, 0.09):
        threshold = high * factor
        peaks: list[int] = []
        for index in range(1, len(envelope) - 1):
            if envelope[index] < threshold:
                continue
            if envelope[index] < envelope[index - 1] or envelope[index] < envelope[index + 1]:
                continue
            if peaks and index - peaks[-1] < refractory:
                # Keep the stronger of two candidates inside the refractory
                # window rather than counting a T-wave as a beat.
                if envelope[index] > envelope[peaks[-1]]:
                    peaks[-1] = index
                continue
            peaks.append(index)

        if len(peaks) >= 3:
            # Refine to the largest absolute deflection of the band-passed
            # signal within +/- 80 ms, which is closer to the R apex than the
            # envelope maximum.
            radius = max(1, int(0.08 * sample_rate_hz))
            refined: list[int] = []
            for peak in peaks:
                low = max(0, peak - radius)
                high_index = min(len(band) - 1, peak + radius)
                best = max(
                    range(low, high_index + 1),
                    key=lambda index: abs(band[index]),
                )
                if not refined or best - refined[-1] >= refractory:
                    refined.append(best)
            return refined

    return []


def assess_quality(
    *,
    raw: list[float],
    missing: int,
    sample_rate_hz: int,
    chunks: int,
    chunk_gaps: int,
    peak_count: int,
    rr: list[float],
    min_quality: float,
    min_seconds: float,
) -> Quality:
    reasons: list[str] = []
    fatal = False
    score = 100.0
    seconds = len(raw) / sample_rate_hz if sample_rate_hz else 0.0

    if not raw or not sample_rate_hz:
        return Quality(0.0, "unusable", False, ["No ECG samples are stored."], missing_samples=missing)

    if seconds < min_seconds:
        reasons.append(
            f"Recording is only {seconds:.1f} s; at least {min_seconds:.1f} s is needed."
        )
        fatal = True

    missing_ratio = missing / max(1, len(raw))
    if missing_ratio > 0.02:
        reasons.append(f"{missing} samples were missing or non-finite.")
        score -= min(40.0, missing_ratio * 300.0)
        if missing_ratio > 0.10:
            fatal = True

    finite = [value for value in raw if math.isfinite(value)]
    spread = 0.0
    if len(finite) > 1:
        avg = sum(finite) / len(finite)
        spread = math.sqrt(sum((value - avg) ** 2 for value in finite) / len(finite))

    flatline = spread < FLATLINE_STD_MV
    if flatline:
        reasons.append("Signal is flat (no measurable electrical activity).")
        fatal = True

    clipped = sum(1 for value in finite if abs(value) >= CLIP_MV)
    clipping_ratio = clipped / max(1, len(finite))
    clipping = clipping_ratio > 0.02
    if clipping:
        reasons.append(f"{clipped} samples are clipped at the ±{CLIP_MV:g} mV limit.")
        score -= min(30.0, clipping_ratio * 150.0)
        if clipping_ratio > 0.30:
            fatal = True

    if chunk_gaps:
        reasons.append(f"{chunk_gaps} chunk(s) are missing from the recording sequence.")
        score -= min(20.0, chunk_gaps * 4.0)

    if peak_count < 3:
        reasons.append("Fewer than three R-peaks were detected.")
        score -= 35.0
        if seconds >= min_seconds:
            fatal = True

    if rr:
        rr_median = _median(rr)
        if rr_median > 0:
            outliers = sum(1 for value in rr if abs(value - rr_median) > rr_median * 0.30)
            outlier_ratio = outliers / len(rr)
            if outlier_ratio > 0.25:
                reasons.append(
                    f"{outliers} of {len(rr)} RR intervals are irregular; "
                    "the rhythm measurement may be unreliable."
                )
                score -= min(25.0, outlier_ratio * 60.0)

    score = max(0.0, min(100.0, score))
    if fatal:
        score = min(score, min_quality - 1.0)

    if score >= 75:
        level = "good"
    elif score >= 50:
        level = "fair"
    elif score >= min_quality:
        level = "poor"
    else:
        level = "unusable"

    usable = (not fatal) and score >= min_quality
    if not reasons:
        reasons.append("No obvious quality problem detected.")
    return Quality(
        score=round(score, 1),
        level=level,
        usable=usable,
        reasons=reasons,
        flatline=flatline,
        clipping=clipping,
        missing_samples=missing,
    )


def extract_signal(chunks: list[dict]) -> tuple[list[float], int | None]:
    """Return the raw, ordered sample stream and its single sample rate.

    The classifier needs the unfiltered trace; ``analyse_chunks`` filters a
    copy for peak detection. Mixed sample rates have no single legal sampling
    frequency, so the rate is ``None`` and the caller must not classify.

    This function performs no filtering and no quality assessment. It mirrors
    the sanitisation in ``analyse_chunks`` (non-finite samples become zeros) so
    both paths see the same trace.
    """

    ordered = sorted(chunks, key=lambda item: item.get("chunk_index", 0))
    rates = {int(item.get("sample_rate_hz") or 0) for item in ordered}
    rates.discard(0)
    if len(rates) != 1:
        return [], None

    samples: list[float] = []
    for item in ordered:
        for value in item.get("samples") or []:
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                numeric = float("nan")
            samples.append(numeric if math.isfinite(numeric) else 0.0)
    return samples, rates.pop()


def analyse_chunks(
    chunks: list[dict],
    *,
    min_quality: float = 35.0,
    min_seconds: float = 2.5,
) -> dict:
    """Analyse stored chunks and return the JSON payload stored by the API.

    ``chunks`` items need ``chunk_index``, ``sample_rate_hz`` and ``samples``.
    The caller (FastAPI) reads them from the database; this function has no I/O
    so it can be unit-tested directly.
    """
    ordered = sorted(chunks, key=lambda item: item.get("chunk_index", 0))
    rates = {int(item.get("sample_rate_hz") or 0) for item in ordered}
    rates.discard(0)

    raw: list[float] = []
    missing = 0
    chunk_gaps = 0
    for item in ordered:
        for value in item.get("samples") or []:
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                numeric = float("nan")
            if not math.isfinite(numeric):
                missing += 1
                numeric = 0.0
            raw.append(numeric)

    indexes = [int(item.get("chunk_index", 0)) for item in ordered]
    if indexes:
        expected = set(range(indexes[0], indexes[-1] + 1))
        chunk_gaps = len(expected - set(indexes))

    if not ordered:
        return _unusable_payload("No ECG chunks are stored for this session.", 0, 0, 0)
    if len(rates) != 1:
        return _unusable_payload(
            "The stored chunks do not share one sampling frequency.", len(raw), 0, len(ordered)
        )

    sample_rate_hz = rates.pop()
    seconds = len(raw) / sample_rate_hz if sample_rate_hz else 0.0

    cleaned = [value for value in raw]
    if sample_rate_hz >= 100:
        # Baseline wander, mains hum, and high-frequency noise.
        cleaned = filtfilt(highpass(sample_rate_hz, 0.5), cleaned)
        if sample_rate_hz > 2 * 50 + 10:
            cleaned = filtfilt(notch(sample_rate_hz, 50.0), cleaned)
        if sample_rate_hz > 2 * 60 + 10:
            cleaned = filtfilt(notch(sample_rate_hz, 60.0), cleaned)
        cutoff = min(40.0, sample_rate_hz * 0.45)
        cleaned = filtfilt(lowpass(sample_rate_hz, cutoff), cleaned)

    peaks = _detect_peaks(cleaned, sample_rate_hz)
    rr, measurement = _rr_metrics(peaks, sample_rate_hz)

    quality = assess_quality(
        raw=raw,
        missing=missing,
        sample_rate_hz=sample_rate_hz,
        chunks=len(ordered),
        chunk_gaps=chunk_gaps,
        peak_count=len(peaks),
        rr=rr,
        min_quality=min_quality,
        min_seconds=min_seconds,
    )

    if not quality.usable:
        # Withhold measurements rather than return a number the signal cannot
        # support. The detected peak count is still reported for transparency.
        measurement = Measurement(beats_detected=len(peaks))

    return {
        "status": "completed" if quality.usable else "unusable",
        "signal": {
            "sample_rate_hz": sample_rate_hz,
            "sample_count": len(raw),
            "duration_seconds": round(seconds, 3),
            "chunks": len(ordered),
            "quality": {
                "score": quality.score,
                "level": quality.level,
                "usable": quality.usable,
                "reasons": quality.reasons,
                "flatline": quality.flatline,
                "clipping": quality.clipping,
                "missing_samples": quality.missing_samples,
            },
            "filtering_note": (
                "0.5 Hz high-pass, 40 Hz low-pass and 50/60 Hz notch applied "
                "forward-backward for zero phase."
            ),
        },
        "measurements": {
            "heart_rate_bpm": round(measurement.heart_rate_bpm, 1)
            if measurement.heart_rate_bpm is not None and quality.usable
            else None,
            "rr_intervals_ms": [round(value, 1) for value in measurement.rr_intervals_ms]
            if quality.usable
            else [],
            "rr_mean_ms": round(measurement.rr_mean_ms, 1)
            if measurement.rr_mean_ms is not None and quality.usable
            else None,
            "rr_std_ms": round(measurement.rr_std_ms, 1)
            if measurement.rr_std_ms is not None and quality.usable
            else None,
            "rmssd_ms": round(measurement.rmssd_ms, 1)
            if measurement.rmssd_ms is not None and quality.usable
            else None,
            "pnn50_percent": round(measurement.pnn50_percent, 1)
            if measurement.pnn50_percent is not None and quality.usable
            else None,
            "beats_detected": measurement.beats_detected,
            "r_peak_seconds": [round(value, 3) for value in measurement.r_peak_seconds]
            if quality.usable
            else [],
        },
    }


def _unusable_payload(reason: str, sample_count: int, rate: int, chunks: int) -> dict:
    return {
        "status": "unusable",
        "signal": {
            "sample_rate_hz": rate or None,
            "sample_count": sample_count,
            "duration_seconds": (sample_count / rate) if rate else 0.0,
            "chunks": chunks,
            "quality": {
                "score": 0.0,
                "level": "unusable",
                "usable": False,
                "reasons": [reason],
                "flatline": False,
                "clipping": False,
                "missing_samples": 0,
            },
            "filtering_note": "",
        },
        "measurements": {
            "heart_rate_bpm": None,
            "rr_intervals_ms": [],
            "rr_mean_ms": None,
            "rr_std_ms": None,
            "rmssd_ms": None,
            "pnn50_percent": None,
            "beats_detected": 0,
            "r_peak_seconds": [],
        },
    }
