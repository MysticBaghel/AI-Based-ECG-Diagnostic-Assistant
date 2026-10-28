"""DSP tests on synthetic signals with known beat times.

No NumPy, no external model: the point is that the deterministic measurements
are correct and that unusable input produces an explanation rather than a
number.
"""

import math

from app.dsp import analyse_chunks


def _gaussian(x: float, centre: float, width: float, amplitude: float) -> float:
    return amplitude * math.exp(-0.5 * ((x - centre) / width) ** 2)


def synthetic_ecg(
    *, bpm: float = 72.0, seconds: float = 12.0, sample_rate: int = 200
) -> list[float]:
    samples: list[float] = []
    period = 60.0 / bpm
    for index in range(int(seconds * sample_rate)):
        t = index / sample_rate
        phase = t % period
        value = (
            _gaussian(phase, 0.16, 0.025, 0.10)  # P
            + _gaussian(phase, 0.31, 0.008, -0.16)  # Q
            + _gaussian(phase, 0.345, 0.010, 1.10)  # R
            + _gaussian(phase, 0.385, 0.010, -0.28)  # S
            + _gaussian(phase, 0.56, 0.055, 0.26)  # T
        )
        value += 0.04 * math.sin(2 * math.pi * 0.3 * t)  # baseline wander
        samples.append(value)
    return samples


def _chunks(samples, rate=200):
    return [{"chunk_index": 0, "sample_rate_hz": rate, "samples": samples}]


def test_heart_rate_and_rr_intervals_are_measured():
    result = analyse_chunks(_chunks(synthetic_ecg(bpm=72)), min_quality=35)

    assert result["status"] == "completed"
    assert result["signal"]["quality"]["usable"] is True
    assert result["signal"]["sample_rate_hz"] == 200
    assert result["measurements"]["heart_rate_bpm"] == 72.0 or abs(
        result["measurements"]["heart_rate_bpm"] - 72.0
    ) < 4.0
    assert 3 <= result["measurements"]["beats_detected"] <= 17
    assert result["measurements"]["rr_mean_ms"] is not None
    assert result["measurements"]["rr_intervals_ms"]


def test_flatline_is_unusable_and_has_no_heart_rate():
    result = analyse_chunks(_chunks([0.0] * 2000))

    assert result["status"] == "unusable"
    assert result["signal"]["quality"]["usable"] is False
    assert result["signal"]["quality"]["flatline"] is True
    assert result["measurements"]["heart_rate_bpm"] is None
    assert "flat" in " ".join(result["signal"]["quality"]["reasons"]).lower()


def test_short_recording_is_unusable():
    result = analyse_chunks(_chunks(synthetic_ecg(seconds=1.0)))

    assert result["status"] == "unusable"
    assert result["measurements"]["heart_rate_bpm"] is None


def test_non_finite_samples_are_counted_and_do_not_crash():
    samples = synthetic_ecg(seconds=8)
    samples[100] = float("nan")
    samples[200] = float("inf")

    result = analyse_chunks(_chunks(samples))

    assert result["signal"]["quality"]["missing_samples"] == 2
    assert result["signal"]["quality"]["usable"] is True


def test_mixed_sample_rates_are_refused():
    result = analyse_chunks(
        [
            {"chunk_index": 0, "sample_rate_hz": 200, "samples": [0.1] * 400},
            {"chunk_index": 1, "sample_rate_hz": 250, "samples": [0.1] * 400},
        ]
    )

    assert result["status"] == "unusable"
    assert "sampling frequency" in result["signal"]["quality"]["reasons"][0]


def test_no_chunks_is_unusable():
    result = analyse_chunks([])

    assert result["status"] == "unusable"
    assert result["signal"]["sample_count"] == 0
    assert result["measurements"]["heart_rate_bpm"] is None


def test_high_heart_rate_is_detected():
    result = analyse_chunks(_chunks(synthetic_ecg(bpm=130, seconds=8)), min_quality=35)

    assert result["status"] == "completed"
    assert abs(result["measurements"]["heart_rate_bpm"] - 130) < 8
