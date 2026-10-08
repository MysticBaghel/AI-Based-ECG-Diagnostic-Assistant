"""Resampling and chunking - the arithmetic that has to be exactly right.

Separated from the network and the clock so it can be tested on its own:

* **Resampling** turns MIT-BIH's 360 Hz (or the synthetic 200 Hz) into the
  200 Hz the simulator sends: linear interpolation between the two neighbouring
  source samples, sized so that "N seconds of signal in" always gives exactly
  "N x 200 samples out". The off-by-one that makes a chunk one sample short is
  the classic bug here, so the count is *computed* (`resampled_length`) rather
  than accumulated.
* **Chunking** cuts the resampled stream into 1-5 second chunks, each with its
  own `chunk_index` and `start_time`. Chunk identity is `(session_id,
  chunk_index)`, the API's idempotency key, so a re-send of the same index must
  carry the same samples - it does, because the chunk is rebuilt from the same
  deterministic signal.
* **Noise** is *not* here. `--noise` is applied by the source, to raw samples at
  the source rate (`simulator/ecg/source.py`, `NoiseLayer`), which is both where
  a real front-end picks it up and dramatically cheaper: evaluating four `sin`
  calls per interpolated sample instead of per source sample costs more than the
  rest of the pipeline together.

Screening aid, not a medical diagnosis.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

from simulator.ecg.source import ECGSource, NoiseConfig, NoiseLayer
from simulator.ranges import ECG_SAMPLE_MV_LIMIT


class SampleSanitiser:
    """Keeps every sample inside the protocol's +/-20 mV, and counts the saves.

    Interpolation cannot push a value outside the range of its two neighbours,
    but `--noise` can: one movement artefact spike is exactly that. The protocol
    limit is +/-20 mV and a single out-of-range sample turns a whole chunk into a
    422, so clamping here is the difference between a noisy trace and no trace.

    The count is reported in the summary, because a silent clamp would hide a
    generator bug: in a clean run this number is 0.
    """

    def __init__(self, limit_mv: float = ECG_SAMPLE_MV_LIMIT) -> None:
        self.limit_mv = float(limit_mv)
        self.clamped = 0

    def __call__(self, value: float) -> float:
        if value != value:  # NaN - a generator bug, not a reading
            self.clamped += 1
            return 0.0
        if value > self.limit_mv:
            self.clamped += 1
            return self.limit_mv
        if value < -self.limit_mv:
            self.clamped += 1
            return -self.limit_mv
        return round(value, 6)


def resampled_length(source_samples: int, source_rate_hz: float, target_rate_hz: int) -> int:
    """How many samples `source_samples` become at the target rate.

    Linear resampling maps sample `i` to time `i / source_rate`, and the output
    covers the same span at `target_rate`, so the count is
    `round(n * target / source)`. Computing it once, up front, is what makes the
    output length exact; accumulating a float position and stopping "when the
    source ends" is what produces a chunk one sample short.
    """
    if source_rate_hz <= 0:
        raise ValueError("source_rate_hz must be positive")
    if source_samples <= 0:
        return 0
    return int(round(source_samples * target_rate_hz / source_rate_hz))


class ResampledECGSource:
    """A `wfdb`/synthetic source streamed out at a different sample rate.

    `__iter__` yields exactly `resampled_length(n, source_rate, target_rate)`
    samples, where `n` is the number of source samples the underlying source has
    (a `wfdb` record, or a synthetic source's `frames x frame_samples`). The
    count is known before the first sample is interpolated, so a 2-second chunk
    at 200 Hz is 400 samples and never 399.
    """

    def __init__(
        self,
        source: ECGSource,
        *,
        target_sample_rate_hz: int,
        max_source_samples: int | None = None,
    ) -> None:
        self.source = source
        self.target_sample_rate_hz = int(target_sample_rate_hz)
        self.source_rate_hz = float(source.sample_rate_hz)
        if self.target_sample_rate_hz <= 0:
            raise ValueError("target_sample_rate_hz must be positive")

        # How many source samples this stream will consume. Sources with a
        # known length (the synthetic generator) say so; a looping record keeps
        # going, so the caller can cap it - that is what stops an hour-long
        # session from growing a buffer without bound.
        self.max_source_samples = max_source_samples or source.total_samples
        if self.max_source_samples is None:
            raise ValueError(
                "this source has no end (it loops); pass max_source_samples so the "
                "resampler knows how long the stream is"
            )
        self.output_length = resampled_length(
            self.max_source_samples, self.source_rate_hz, self.target_sample_rate_hz
        )

        # Noise belongs to the source (see `NoiseLayer`), so the resampler stays
        # noise-free and fast; `sanitiser` is still the last line of defence
        # against a sample the API would refuse.
        self.sanitiser = SampleSanitiser()

        self._ratio = self.source_rate_hz / self.target_sample_rate_hz
        # `source_position` is a float count of source samples consumed so far.
        self._source_position = 0.0
        self._source_done = False
        self._source_iterator: Iterator[float] | None = None
        # `_collected[0]` is always source sample `_collected_count - len(...)`,
        # so the buffer can be trimmed from the front without renumbering.
        self._collected: list[float] = []
        self._collected_count = 0

    # -- source plumbing ---------------------------------------------------

    def _collect(self, count: int) -> None:
        """Make sure source sample `count - 1` has been read.

        `count` grows monotonically - the interpolation only ever moves forward -
        so the window is trimmed from the front on every call and holds a couple
        of samples instead of the whole signal. That matters when the "signal" is
        a 30-minute record being replayed on a loop.
        """
        while self._collected_count < count and self._collected_count < self.max_source_samples:
            try:
                self._collected.append(next(self._source()))
                self._collected_count += 1
            except StopIteration:
                self._source_done = True
                break
        # Keep `count - 2` onwards: sample `count - 2` is the interpolation's
        # lower neighbour on the next call.
        drop = self._collected_count - len(self._collected)
        keep_from = max(0, count - 2 - drop)
        if keep_from > 0:
            del self._collected[:keep_from]

    def _sample_at(self, index: int) -> float:
        """Source sample `index`, clamped to whatever is available."""
        if index < 0:
            index = 0
        self._collect(index + 1)
        if not self._collected:
            return 0.0
        # The buffer no longer starts at sample 0, so translate the absolute
        # index into a buffer position - this is the line the ramp test exists
        # to protect.
        offset = index - (self._collected_count - len(self._collected))
        if offset < 0:
            offset = 0
        elif offset >= len(self._collected):
            offset = len(self._collected) - 1
        return self._collected[offset]

    def _source(self) -> Iterator[float]:
        """The source stream, created once and pulled lazily."""
        if self._source_iterator is None:
            self._source_iterator = self.source.samples()
        return self._source_iterator

    # -- the public stream -------------------------------------------------

    @property
    def exhausted(self) -> bool:
        return self._source_done

    def __iter__(self) -> Iterator[float]:
        """Yield interpolated samples at the target rate, lazily and exactly.

        The loop is a counted one - `output_length` times - not a
        "stop when the source runs out" one. That is the whole trick: the count
        comes from `resampled_length`, so the last sample is never lost to a
        floating-point comparison at the boundary.
        """
        for _ in range(self.output_length):
            position = self._source_position
            low = int(math.floor(position))
            frac = position - low

            first = self._sample_at(low)
            second = self._sample_at(low + 1)
            self._source_position += self._ratio

            yield self.sanitiser(first if frac == 0.0 else first + (second - first) * frac)

    def take(self, count: int) -> list[float]:
        """Up to `count` samples - fewer only when the stream is shorter."""
        out: list[float] = []
        for value in self:
            out.append(value)
            if len(out) >= count:
                break
        return out


@dataclass
class ECGChunk:
    """One `POST /sensor/ecg` body, before it is serialised."""

    chunk_index: int
    start_time: float  # seconds since the session's ECG epoch
    sample_rate_hz: int
    samples: list[float] = field(default_factory=list)

    @property
    def sample_count(self) -> int:
        return len(self.samples)

    @property
    def duration_seconds(self) -> float:
        return self.sample_count / self.sample_rate_hz


class Chunker:
    """Cuts an ECG stream into fixed-duration chunks with stable indexes.

    `chunk_index` is the API's at-least-once delivery key, so it must mean
    "these samples, this start time" for the whole session. It is derived from
    the chunk's position in the stream, never from a counter that could be
    skipped by the drop logic - that is exactly the bug `--drop-chunks` would
    otherwise hide.
    """

    def __init__(
        self,
        stream: Iterable[float],
        *,
        sample_rate_hz: int,
        chunk_seconds: float = 2.0,
        first_chunk_index: int = 0,
    ) -> None:
        if chunk_seconds <= 0:
            raise ValueError("chunk_seconds must be positive")
        self.stream = stream
        self.sample_rate_hz = int(sample_rate_hz)
        self.chunk_seconds = float(chunk_seconds)
        self.chunk_samples = int(round(chunk_seconds * self.sample_rate_hz))
        if not 1 <= self.chunk_samples <= 5000:
            raise ValueError(
                "a chunk of "
                f"{self.chunk_samples} samples is outside the 1..5000 the API accepts; "
                "use a shorter --ecg-chunk-seconds"
            )
        self.first_chunk_index = first_chunk_index
        self._next_index = first_chunk_index

    def _build(self, index: int, blocks: list[list[float]]) -> ECGChunk:
        samples = [sample for block in blocks for sample in block]
        return ECGChunk(
            chunk_index=index,
            start_time=(index - self.first_chunk_index) * self.chunk_seconds,
            sample_rate_hz=self.sample_rate_hz,
            samples=samples,
        )

    def iter_chunks(self) -> Iterator[ECGChunk]:
        """Yield chunks in order. The final chunk may be shorter than the rest.

        A short final chunk is still a legal chunk (1..5000 samples), so it is
        sent rather than padded with invented samples.
        """
        iterator = iter(self.stream)
        while True:
            blocks: list[list[float]] = []
            received = 0
            while received < self.chunk_samples:
                block = _take(iterator, self.chunk_samples - received)
                if not block:
                    break
                blocks.append(block)
                received += len(block)

            if received == 0:
                return

            chunk = self._build(self._next_index, blocks)
            self._next_index += 1
            yield chunk
            if received < self.chunk_samples:
                return


def _take(iterator: Iterator[float], count: int) -> list[float]:
    """Up to `count` items from an iterator (a lazy version of a list slice)."""
    out: list[float] = []
    for value in iterator:
        out.append(value)
        if len(out) >= count:
            break
    return out


def expected_sample_count(*, duration_seconds: float, sample_rate_hz: int) -> int:
    """How many resampled samples `duration_seconds` of signal yields.

    Deliberately independent of `ResampledECGSource`: it is the number the
    *contract* implies (`chunk_seconds x sample_rate_hz`), which is what the
    implementation is checked against in `tests/test_ecg_signal.py`.
    """
    return int(round(duration_seconds * sample_rate_hz))


__all__ = [
    "ECGChunk",
    "Chunker",
    "NoiseConfig",
    "ResampledECGSource",
    "SampleSanitiser",
    "expected_sample_count",
    "resampled_length",
]
