"""Turn an uploaded CSV into millivolt samples at the file's own rate.

"Upload the data from anywhere" means the parser has to cope with files that
were not written for this application: PhysioNet exports, a spreadsheet with a
header, one column or several, seconds or milliseconds on the time axis,
comma/semicolon/tab separated. The rules, in order:

* blank lines and `#` comments are ignored; a first row that is not numeric is
  a header;
* a leading sample-index column (0, 1, 2, ...) is dropped;
* if two numeric columns remain, the first is time and the second is the value;
  otherwise there is one value column and the rate is the caller's assumption;
* the time axis is read as seconds when that gives a plausible rate, else as
  milliseconds, else it is an index and the assumption applies;
* the samples are kept at the rate the file implies whenever that rate is one
  the ingestion API accepts (100-2000 Hz), so a 300 Hz recording is stored and
  reported as 300 Hz rather than being silently converted to 200 Hz. Only a
  rate outside that window is resampled (to 200 Hz), and the response says so;
* values are clamped to the API's millivolt range and rounded.

Every guess is reported back (`ParsedCSV.notes`) so the operator can see what
the server decided instead of wondering why the trace looks wrong.

Screening aid, not a medical diagnosis.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import median

from app.core.config import MAX_ECG_SAMPLE_RATE_HZ, MIN_ECG_SAMPLE_RATE_HZ
from app.simulation.generator import SAMPLE_RATE_HZ

#: The longest upload that is kept, in seconds. Bounds what one upload pins in
#: memory; the sample cap follows from the rate.
MAX_SECONDS = 600.0
#: A rate the time column can plausibly imply, in Hz. Low enough for a
#: 30 Hz export; an index column (0, 1, 2, ...) is caught separately.
MIN_PLAUSIBLE_RATE = 10.0
MAX_PLAUSIBLE_RATE = 2000.0
#: What an outside-the-API-window file is converted to.
FALLBACK_RATE_HZ = SAMPLE_RATE_HZ
#: Every sample must be inside the API's +/-20 mV; stay clear of the edge.
SAMPLE_LIMIT_MV = 19.0

_DELIMITERS = (",", ";", "\t")


@dataclass
class ParsedCSV:
    samples: list[float]
    #: the rate the samples are at now (and will be stored at)
    sample_rate_hz: int
    #: the rate inferred from the file before any conversion
    source_rate_hz: float
    duration_seconds: float
    rows_read: int
    rows_skipped: int
    notes: list[str] = field(default_factory=list)

    @property
    def sample_count(self) -> int:
        return len(self.samples)


def _split(line: str) -> list[str]:
    for delimiter in _DELIMITERS:
        if delimiter in line:
            return [part.strip() for part in line.split(delimiter)]
    return line.split()


def _is_number(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True


def _column_values(
    rows: list[list[float]], column: int
) -> list[float]:
    return [row[column] for row in rows]


def _looks_like_index(values: list[float]) -> bool:
    if len(values) < 2:
        return False
    if any(value != int(value) for value in values):
        return False
    return all(b - a == 1.0 for a, b in zip(values, values[1:3] or values[:1]))


def _source_rate(times: list[float], assumed: float, notes: list[str]) -> float:
    steps = [b - a for a, b in zip(times, times[1:]) if b > a]
    if not steps:
        return assumed

    step = median(steps)
    as_seconds = 1.0 / step if step > 0 else 0.0
    as_milliseconds = 1000.0 / step if step > 0 else 0.0

    if _looks_like_index(times):
        notes.append(
            f"The first column is a sample index; using {assumed:g} Hz as the rate."
        )
        return assumed
    if MIN_PLAUSIBLE_RATE <= as_seconds <= MAX_PLAUSIBLE_RATE:
        return as_seconds
    if MIN_PLAUSIBLE_RATE <= as_milliseconds <= MAX_PLAUSIBLE_RATE:
        notes.append("The time column looks like milliseconds; it was read as such.")
        return as_milliseconds

    notes.append(
        f"Could not infer a rate from the time column ({as_seconds:.3g} Hz); "
        f"using {assumed:g} Hz."
    )
    return assumed


def _resample(
    samples: list[float], source_rate_hz: float, target_rate_hz: int
) -> list[float]:
    """Linear interpolation onto the target grid, with an exact output length."""
    if not samples:
        return []
    if abs(source_rate_hz - target_rate_hz) < 1e-6:
        return [round(min(SAMPLE_LIMIT_MV, max(-SAMPLE_LIMIT_MV, value)), 6) for value in samples]

    ratio = source_rate_hz / target_rate_hz
    count = int(round(len(samples) * target_rate_hz / source_rate_hz))
    count = max(1, count)
    out: list[float] = []
    for index in range(count):
        position = index * ratio
        low = int(math.floor(position))
        high = min(len(samples) - 1, low + 1)
        fraction = position - low
        value = samples[low] * (1.0 - fraction) + samples[high] * fraction
        out.append(round(min(SAMPLE_LIMIT_MV, max(-SAMPLE_LIMIT_MV, value)), 6))
    return out


def parse_csv(text: str, *, assumed_rate_hz: float = 200.0) -> ParsedCSV:
    """Parse CSV text into resampled samples. Raises ValueError when unusable."""
    rows: list[list[float]] = []
    skipped = 0
    header_skipped = False

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        fields = _split(line)
        if not all(_is_number(field) for field in fields if field != ""):
            if not rows and not header_skipped:
                header_skipped = True  # a header row, not data
                continue
            skipped += 1
            continue

        values = [float(field) for field in fields if field != ""]
        if values:
            rows.append(values)

    if not rows:
        raise ValueError(
            "The file has no numeric rows. Expected one voltage column, or a "
            "time column followed by a voltage column."
        )

    # A file must describe the same columns on every row.
    width = min(len(row) for row in rows)
    rows = [row[:width] for row in rows]
    if width == 0:
        raise ValueError("The file has no columns to read.")

    notes: list[str] = []
    assumed = float(assumed_rate_hz)
    if MIN_PLAUSIBLE_RATE <= assumed <= MAX_PLAUSIBLE_RATE:
        pass
    else:
        notes.append(f"The requested {assumed:g} Hz is not plausible; using 200 Hz.")
        assumed = 200.0

    # Drop a leading 0,1,2,... index column so the time/value pair is right.
    if width >= 3:
        first = _column_values(rows, 0)
        if _looks_like_index(first):
            rows = [row[1:] for row in rows]
            width -= 1
            notes.append("Ignored the leading sample-index column.")

    if width >= 2:
        times = _column_values(rows, 0)
        values = _column_values(rows, 1)
        if any(b < a for a, b in zip(times, times[1:])):
            notes.append("The time column is not monotonic; rows kept as ordered.")
        source_rate = _source_rate(times, assumed, notes)
    else:
        values = _column_values(rows, 0)
        source_rate = assumed

    finite = [value for value in values if math.isfinite(value)]
    dropped = len(values) - len(finite)
    if dropped:
        notes.append(f"{dropped} non-finite sample(s) were dropped.")
    if not finite:
        raise ValueError("Every value in the file is non-finite (NaN or infinity).")

    # Keep the file's rate when the ingestion API accepts it. Converting a
    # 300 Hz recording to 200 Hz would still measure a heart rate, but the
    # stored signal, the report and any later classifier would then describe a
    # different signal than the one that was uploaded.
    if MIN_ECG_SAMPLE_RATE_HZ <= source_rate <= MAX_ECG_SAMPLE_RATE_HZ:
        stored_rate = int(round(source_rate))
        # A time column printed with a few decimals yields 300.3 Hz for a
        # 300 Hz file. Within half a percent that is rounding noise, not a
        # different rate, so the samples are used as they are.
        if abs(source_rate - stored_rate) / stored_rate < 0.005:
            samples = [
                round(min(SAMPLE_LIMIT_MV, max(-SAMPLE_LIMIT_MV, value)), 6)
                for value in finite
            ]
        else:
            samples = _resample(finite, source_rate, stored_rate)
    else:
        stored_rate = FALLBACK_RATE_HZ
        samples = _resample(finite, source_rate, stored_rate)
        notes.append(
            f"The file's rate ({source_rate:g} Hz) is outside "
            f"{MIN_ECG_SAMPLE_RATE_HZ}-{MAX_ECG_SAMPLE_RATE_HZ} Hz, so the "
            f"signal was resampled to {stored_rate} Hz."
        )

    max_samples = int(stored_rate * MAX_SECONDS)
    if len(samples) > max_samples:
        notes.append(
            f"File was longer than {MAX_SECONDS:.0f} s; kept the first part."
        )
        samples = samples[:max_samples]

    if samples and max(abs(value) for value in samples) < 0.02:
        notes.append(
            "Amplitudes are very small (<0.02 mV). If the file stores volts, "
            "the trace will look flat."
        )

    return ParsedCSV(
        samples=samples,
        sample_rate_hz=stored_rate,
        source_rate_hz=round(source_rate, 3),
        duration_seconds=round(len(samples) / stored_rate, 3),
        rows_read=len(rows),
        rows_skipped=skipped,
        notes=notes,
    )
