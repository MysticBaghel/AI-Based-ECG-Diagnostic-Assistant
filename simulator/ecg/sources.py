"""Picks the ECG source: MIT-BIH when it can, synthetic when it cannot.

The decision is made in one place so the rest of the simulator never has to ask
"do we have wfdb?". The rules:

* `--ecg-source synthetic`  -> synthetic, no network, no wfdb, always works
* `--ecg-source mitbih`     -> MIT-BIH, and a hard failure if it cannot be read
* `--ecg-source auto`       -> MIT-BIH, falling back to synthetic with a warning

`auto` is the default because it is the useful one: on a machine with a network
and `wfdb` installed you replay real annotated ECG, and on a plane you still get
a signal. `mitbih` is there for the person who *wants* the failure - a broken
download should not be silently masked in a demo that claims to be replaying
MIT-BIH.

Screening aid, not a medical diagnosis.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from simulator.ecg.mitbih import (
    DEFAULT_ECG_DATA_DIR,
    DEFAULT_RECORD,
    WFDBECGSource,
    WFDBUnavailable,
)
from simulator.ecg.source import (
    DEFAULT_SOURCE_FRAMES,
    ECGSource,
    NoiseConfig,
    NoiseLayer,
    SyntheticECGSource,
)

logger = logging.getLogger("simulator.ecg.source")

SOURCE_CHOICES = ("auto", "mitbih", "synthetic")


@dataclass
class SourceRequest:
    """Everything the choice depends on, so tests can build one cheaply."""

    kind: str = "auto"
    record: str = DEFAULT_RECORD
    data_dir: str = DEFAULT_ECG_DATA_DIR
    download: bool = True
    frames: int = DEFAULT_SOURCE_FRAMES
    synthetic_rate_hz: float = 200.0
    seed: int | None = None
    #: `--noise`; the source applies it to raw samples before resampling
    noise: NoiseConfig = field(default_factory=NoiseConfig.none)
    notes: list[str] = field(default_factory=list)


def build_ecg_source(request: SourceRequest) -> ECGSource:
    """Return an ECG source, honouring `request.kind`.

    Raises `ValueError` for an unknown kind and `WFDBUnavailable` when MIT-BIH
    was demanded and could not be delivered.
    """
    if request.kind not in SOURCE_CHOICES:
        raise ValueError(
            f"unknown ECG source {request.kind!r}; expected one of {SOURCE_CHOICES}"
        )

    if request.kind == "synthetic":
        return _synthetic(request, reason="requested")

    try:
        source = WFDBECGSource(
            record_name=request.record,
            data_dir=request.data_dir,
            frames=request.frames,
            download=request.download,
            noise=request.noise,
            seed=request.seed,
        )
        logger.info(
            "ECG source: MIT-BIH record %s (%s Hz, channel 0)%s",
            request.record,
            int(source.sample_rate_hz),
            _provenance(source),
        )
        request.notes.append(
            f"MIT-BIH {request.record} at {int(source.sample_rate_hz)} Hz{_provenance(source)}"
        )
        return source
    except WFDBUnavailable as exc:
        if request.kind == "mitbih":
            raise WFDBUnavailable(
                f"MIT-BIH record {request.record!r} could not be loaded: {exc}"
            ) from exc
        logger.warning("MIT-BIH unavailable (%s); using the synthetic ECG", exc)
        request.notes.append(f"MIT-BIH unavailable, synthetic fallback ({exc})")
        return _synthetic(request, reason=str(exc))
    except Exception as exc:  # noqa: BLE001
        # Broad on purpose: a network error, an HTTP error, a missing file, a
        # corrupt header or an import error all mean the same thing to us -
        # fall back, do not crash a smoke run.
        if request.kind == "mitbih":
            raise WFDBUnavailable(
                f"MIT-BIH record {request.record!r} could not be loaded: {exc}"
            ) from exc
        logger.warning("MIT-BIH failed (%s); using the synthetic ECG", exc)
        request.notes.append(f"MIT-BIH failed, synthetic fallback ({exc})")
        return _synthetic(request, reason=str(exc))


def _synthetic(request: SourceRequest, *, reason: str) -> SyntheticECGSource:
    source = SyntheticECGSource(
        sample_rate_hz=request.synthetic_rate_hz,
        frames=request.frames,
        seed=request.seed,
        noise=request.noise,
    )
    logger.info(
        "ECG source: synthetic sinus rhythm at %s Hz (%s)",
        int(source.sample_rate_hz),
        reason,
    )
    if request.kind == "synthetic":
        request.notes.append(f"synthetic ECG at {int(source.sample_rate_hz)} Hz")
    return source


def _provenance(source) -> str:
    """Where a MIT-BIH record came from, for the log and the summary."""
    if getattr(source, "downloaded", False):
        return " (downloaded to the local cache)"
    if getattr(source, "streamed", False):
        return " (streamed from PhysioNet)"
    return " (local cache)"


__all__ = ["SOURCE_CHOICES", "SourceRequest", "build_ecg_source"]
