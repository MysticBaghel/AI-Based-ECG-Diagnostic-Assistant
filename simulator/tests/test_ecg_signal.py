"""Resampling, noise and chunking - the arithmetic, tested without a clock or a
network.

The assertion that matters most is the sample count: "N seconds at R Hz" must be
exactly `N x R` samples, because a chunk that is one sample short is the bug
that produces a visible seam in the waveform and is almost impossible to spot by
eye in a 400-sample list.
"""

from __future__ import annotations

import pytest

from simulator.ecg.signal import (
    ECGChunk,
    Chunker,
    NoiseConfig,
    ResampledECGSource,
    SampleSanitiser,
    expected_sample_count,
    resampled_length,
)
from simulator.ecg.source import SyntheticECGSource
from simulator.ranges import ECG_SAMPLE_MV_LIMIT


def synthetic(
    *, rate: float, seconds: float, frame_seconds: float = 0.25, noise=None
) -> SyntheticECGSource:
    """A synthetic source with a bounded, known length."""
    frames = max(1, int(round(seconds / frame_seconds)))
    return SyntheticECGSource(
        sample_rate_hz=rate,
        frames=frames,
        frame_seconds=frame_seconds,
        seed=11,
        noise=noise,
    )


# --- resampling -----------------------------------------------------------


@pytest.mark.parametrize(
    ("source_rate", "target_rate", "seconds"),
    [
        (360, 200, 2.0),  # MIT-BIH -> the simulator's 200 Hz
        (200, 200, 2.0),  # already the target: a pass-through
        (100, 200, 1.0),  # upsampling
        (1000, 250, 4.0),  # downsampling by 4
        (360, 200, 0.5),  # a partial second
        (360, 200, 7.5),  # odd duration, still exact
    ],
)
def test_resampling_produces_the_expected_sample_count(
    source_rate: int, target_rate: int, seconds: float
) -> None:
    """`N` seconds of signal at `R` Hz must come out as exactly `N x R` samples.

    Checked three ways: what the resampler advertises, what it actually yields,
    and the count computed from the contract's own arithmetic. They must agree,
    or a chunk will be a sample short and the waveform will seam.
    """
    source = synthetic(rate=source_rate, seconds=seconds)
    stream = ResampledECGSource(source, target_sample_rate_hz=target_rate)
    expected = expected_sample_count(duration_seconds=seconds, sample_rate_hz=target_rate)

    assert stream.output_length == expected
    assert len(list(stream)) == expected


def test_resampled_length_is_the_documented_formula() -> None:
    assert resampled_length(3600, 360, 200) == 2000  # 10 s: 5 source samples -> 1
    assert resampled_length(0, 360, 200) == 0
    assert resampled_length(400, 200, 200) == 400  # a pass-through
    assert resampled_length(100, 100, 200) == 200  # doubling
    with pytest.raises(ValueError):
        resampled_length(100, 0, 200)


def test_a_looping_source_must_be_given_a_length() -> None:
    """A source with no end cannot be resampled exactly; say so, do not guess."""

    class Endless(SyntheticECGSource):
        @property
        def total_samples(self):
            return None

    with pytest.raises(ValueError, match="max_source_samples"):
        ResampledECGSource(Endless(sample_rate_hz=200, frames=1), target_sample_rate_hz=200)

    stream = ResampledECGSource(
        Endless(sample_rate_hz=200, frames=1),
        target_sample_rate_hz=200,
        max_source_samples=400,
    )
    assert stream.output_length == 400


def test_resampling_is_exact_for_a_whole_number_of_output_samples() -> None:
    """2 s at 200 Hz is 400 samples, not 399 and not 401."""
    source = synthetic(rate=360, seconds=2.0)
    stream = ResampledECGSource(source, target_sample_rate_hz=200)

    assert len(stream.take(400)) == 400


def test_resampling_keeps_the_signal_inside_the_protocol_range() -> None:
    source = synthetic(rate=360, seconds=3.0, noise=NoiseConfig.all())
    stream = ResampledECGSource(source, target_sample_rate_hz=200)

    samples = stream.take(600)
    assert max(samples) <= ECG_SAMPLE_MV_LIMIT
    assert min(samples) >= -ECG_SAMPLE_MV_LIMIT
    assert stream.sanitiser.clamped == 0, "a clean synthetic signal must not need clamping"


def test_resampling_preserves_a_known_ramp() -> None:
    """Interpolation is checkable exactly on a signal we can compute by hand.

    A 100 Hz ramp of 0, 1, 2, ... resampled to 200 Hz doubles the sample count
    and lands halfway between the source samples: 0, 0.5, 1, 1.5, ... This is
    also the test that catches the buffer being trimmed wrongly: the interpolation
    reads two neighbouring samples, so dropping the lower one silently produces a
    plausible-looking but wrong waveform.
    """

    class Ramp(SyntheticECGSource):
        source_name = "ramp"

        def _next_frame(self):
            start = self._delivered * 10
            for index in range(10):
                yield float(start + index)

    source = Ramp(sample_rate_hz=100, frames=4, frame_seconds=0.1)
    stream = ResampledECGSource(source, target_sample_rate_hz=200)

    assert stream.take(6) == [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]


# --- noise ----------------------------------------------------------------


def test_noise_changes_the_signal_but_stays_legal() -> None:
    """`--noise` belongs to the source, applied before the resampler sees it.

    Putting it there is both where a real front-end picks it up and much cheaper:
    per source sample instead of per interpolated sample.
    """
    clean_source = synthetic(rate=360, seconds=2.0)
    clean = ResampledECGSource(clean_source, target_sample_rate_hz=200).take(400)

    noisy_source = synthetic(rate=360, seconds=2.0, noise=NoiseConfig.all())
    noisy = ResampledECGSource(noisy_source, target_sample_rate_hz=200).take(400)

    assert clean != noisy
    assert all(abs(value) <= ECG_SAMPLE_MV_LIMIT for value in noisy)


def test_the_sanitiser_counts_and_clamps() -> None:
    sanitiser = SampleSanitiser()
    assert sanitiser(1.5) == 1.5
    assert sanitiser(25.0) == ECG_SAMPLE_MV_LIMIT
    assert sanitiser(-999.0) == -ECG_SAMPLE_MV_LIMIT
    assert sanitiser(float("nan")) == 0.0
    assert sanitiser.clamped == 3
    assert sanitiser(0.1) == 0.1


# --- chunking -------------------------------------------------------------


def test_chunking_splits_evenly_and_numbers_from_zero() -> None:
    chunker = Chunker(
        [float(i) for i in range(1000)], sample_rate_hz=200, chunk_seconds=2.0
    )
    chunks = list(chunker.iter_chunks())

    assert [chunk.chunk_index for chunk in chunks] == [0, 1, 2]
    assert [chunk.sample_count for chunk in chunks] == [400, 400, 200]
    assert [chunk.start_time for chunk in chunks] == [0.0, 2.0, 4.0]
    assert all(chunk.sample_rate_hz == 200 for chunk in chunks)


def test_the_last_chunk_may_be_short_but_is_never_empty() -> None:
    chunker = Chunker([1.0] * 401, sample_rate_hz=200, chunk_seconds=2.0)
    chunks = list(chunker.iter_chunks())

    assert [chunk.sample_count for chunk in chunks] == [400, 1]


def test_chunk_index_is_independent_of_the_sample_values() -> None:
    """Same length in, same indexes out - indexes are positions, not counters."""
    first = list(Chunker([0.1] * 800, sample_rate_hz=200, chunk_seconds=2.0).iter_chunks())
    second = list(Chunker([0.9] * 800, sample_rate_hz=200, chunk_seconds=2.0).iter_chunks())

    assert [chunk.chunk_index for chunk in first] == [chunk.chunk_index for chunk in second]


def test_chunking_a_real_resampled_stream_gives_the_right_shape() -> None:
    """The end-to-end shape: 10 s at 200 Hz in 2 s chunks is 5 chunks of 400."""
    source = synthetic(rate=360, seconds=10.0)
    stream = ResampledECGSource(source, target_sample_rate_hz=200)
    chunks = list(Chunker(stream, sample_rate_hz=200, chunk_seconds=2.0).iter_chunks())

    assert len(chunks) == 5
    assert [chunk.sample_count for chunk in chunks] == [400] * 5
    assert [chunk.chunk_index for chunk in chunks] == [0, 1, 2, 3, 4]
    assert all(chunk.duration_seconds == 2.0 for chunk in chunks)


@pytest.mark.parametrize("chunk_seconds", [1.0, 2.0, 5.0])
def test_every_chunk_length_is_inside_the_api_limit(chunk_seconds: float) -> None:
    """1-5 s at 200 Hz is 200-1000 samples; the API accepts 1-5000."""
    chunker = Chunker([0.0] * 5000, sample_rate_hz=200, chunk_seconds=chunk_seconds)
    chunks = list(chunker.iter_chunks())

    assert all(1 <= chunk.sample_count <= 5000 for chunk in chunks)


def test_a_chunk_that_would_break_the_api_limit_is_refused_early() -> None:
    """10 s at 200 Hz is 2000 samples, which is legal; 30 s would not be at 200 Hz."""
    with pytest.raises(ValueError, match="chunk_seconds"):
        Chunker([0.0] * 10, sample_rate_hz=200, chunk_seconds=0)
    with pytest.raises(ValueError, match="outside the 1..5000"):
        Chunker([0.0] * 10, sample_rate_hz=2000, chunk_seconds=5.0)


def test_chunk_payload_has_everything_the_endpoint_needs() -> None:
    chunk = next(Chunker([0.5] * 400, sample_rate_hz=200, chunk_seconds=2.0).iter_chunks())

    assert isinstance(chunk, ECGChunk)
    assert chunk.samples[0] == 0.5
    assert chunk.sample_count == 400
    assert chunk.duration_seconds == pytest.approx(2.0)
    assert chunk.sample_rate_hz == 200


def test_first_chunk_index_can_be_offset() -> None:
    """A resumed session must continue numbering where it left off."""
    chunker = Chunker([0.0] * 400, sample_rate_hz=200, chunk_seconds=2.0, first_chunk_index=17)
    chunk = next(chunker.iter_chunks())

    assert chunk.chunk_index == 17
    assert chunk.start_time == 0.0
