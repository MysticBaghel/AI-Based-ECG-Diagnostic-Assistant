"""ECG: where the signal comes from, and how it is shaped for the wire.

    source.py   the `ECGSource` interface + the offline synthetic PQRST generator
    mitbih.py   real MIT-BIH records through the `wfdb` library, with a cache
    sources.py  the auto/mitbih/synthetic decision and the fallback
    signal.py   resampling, `--noise`, and chunking into `chunk_index` units

The pipeline is one direction only:

    source (360 Hz, mV) -> noise -> resample (200 Hz) -> chunk (2 s) -> POST

Screening aid, not a medical diagnosis.
"""

from simulator.ecg.signal import (
    ECGChunk,
    Chunker,
    NoiseConfig,
    ResampledECGSource,
    expected_sample_count,
)
from simulator.ecg.source import ECGSource, SyntheticECGSource
from simulator.ecg.sources import SOURCE_CHOICES, SourceRequest, build_ecg_source

__all__ = [
    "SOURCE_CHOICES",
    "Chunker",
    "ECGChunk",
    "ECGSource",
    "NoiseConfig",
    "ResampledECGSource",
    "SourceRequest",
    "SyntheticECGSource",
    "build_ecg_source",
    "expected_sample_count",
]
