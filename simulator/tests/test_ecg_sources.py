"""Where the ECG comes from: the synthetic generator, the MIT-BIH loader, and
the fallback between them.

The fallback is the part worth testing: a demo runs on a laptop with no network
and no `wfdb` installed, and it must still produce a signal instead of a
traceback. Nothing in these tests touches the network - the MIT-BIH path is
asked for a record that is deliberately not in the cache, with downloading off,
which is exactly the failure the fallback exists for.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from simulator.ecg import SOURCE_CHOICES, SourceRequest, build_ecg_source
from simulator.ecg.mitbih import WFDBECGSource, WFDBUnavailable
from simulator.ecg.source import SyntheticECGSource
from simulator.ranges import ECG_SAMPLE_MV_LIMIT


# --- the synthetic generator ---------------------------------------------


def test_synthetic_samples_are_physiological_millivolts() -> None:
    source = SyntheticECGSource(sample_rate_hz=200, frames=3, frame_seconds=1.0, seed=1)
    samples = list(source.samples())

    assert len(samples) == 600
    assert max(samples) > 0.5, "an R wave should be clearly positive"
    assert min(samples) > -0.5, "the S wave is small; nothing should dive"
    assert all(abs(value) <= ECG_SAMPLE_MV_LIMIT for value in samples)


def test_synthetic_has_a_recognisable_beat() -> None:
    """Roughly one R wave per beat, at roughly the requested rate.

    A 72 bpm source over 10 s should show ~12 peaks above 0.5 mV. This is the
    check that the generator makes a *heartbeat* and not a smooth wiggle.
    """
    source = SyntheticECGSource(
        sample_rate_hz=200, frames=10, frame_seconds=1.0, heart_rate_bpm=72.0, seed=2
    )
    samples = list(source.samples())

    peaks = 0
    above = False
    for value in samples:
        if value > 0.5 and not above:
            peaks += 1
            above = True
        elif value < 0.3:
            above = False

    assert 11 <= peaks <= 13, f"expected ~12 beats in 10 s, counted {peaks}"


def test_synthetic_source_is_lazy_but_bounded() -> None:
    source = SyntheticECGSource(sample_rate_hz=200, frames=2, frame_seconds=0.5)
    assert len(source.take(500)) == 200  # only what exists, never more


def test_synthetic_is_reproducible_from_a_seed() -> None:
    first = list(SyntheticECGSource(sample_rate_hz=200, frames=2, seed=42).samples())
    second = list(SyntheticECGSource(sample_rate_hz=200, frames=2, seed=42).samples())
    third = list(SyntheticECGSource(sample_rate_hz=200, frames=2, seed=43).samples())

    assert first == second
    assert first != third


# --- the source picker ----------------------------------------------------


def test_synthetic_kind_never_touches_wfdb(workdir: Path) -> None:
    request = SourceRequest(kind="synthetic", data_dir=str(workdir), seed=1)
    source = build_ecg_source(request)

    assert isinstance(source, SyntheticECGSource)
    assert request.notes and "synthetic" in request.notes[0]


def test_auto_falls_back_when_the_record_is_not_there(workdir: Path) -> None:
    """No download, no cache: `auto` must fall back, and say why."""
    request = SourceRequest(
        kind="auto", data_dir=str(workdir), download=False, frames=2, seed=1
    )
    source = build_ecg_source(request)

    assert isinstance(source, SyntheticECGSource)
    assert any("fallback" in note for note in request.notes)


def test_demanding_mitbih_reports_the_failure_instead_of_hiding_it(workdir: Path) -> None:
    """`--ecg-source mitbih` is for someone who wants the error, not a substitute."""
    request = SourceRequest(
        kind="mitbih", data_dir=str(workdir), download=False, frames=2
    )
    with pytest.raises(WFDBUnavailable):
        build_ecg_source(request)


def test_an_unknown_source_kind_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown ECG source"):
        build_ecg_source(SourceRequest(kind="telepathy"))


def test_source_choices_are_the_documented_ones() -> None:
    assert SOURCE_CHOICES == ("auto", "mitbih", "synthetic")


# --- the MIT-BIH loader (offline behaviour only) --------------------------


def test_wfdb_loader_explains_a_missing_local_record(workdir: Path) -> None:
    """With downloading off, the loader must say what is missing, not crash oddly."""
    try:
        WFDBECGSource(record_name="100", data_dir=str(workdir), download=False)
    except WFDBUnavailable as exc:
        assert "not in" in str(exc) or "wfdb is not installed" in str(exc)
    except Exception as exc:  # pragma: no cover - wfdb present but angry
        pytest.fail(f"expected a WFDBUnavailable, got {type(exc).__name__}: {exc}")
    else:  # pragma: no cover - only if a record really is in workdir
        pytest.skip("a record was found in the temporary directory")


def test_record_cache_is_detected_by_header_and_data(workdir: Path) -> None:
    from simulator.ecg.mitbih import _record_is_local

    assert _record_is_local(str(workdir / "100")) is False
    (workdir / "100.hea").write_text("x", encoding="utf-8")
    assert _record_is_local(str(workdir / "100")) is False  # header only
    (workdir / "100.dat").write_bytes(b"\x00")
    assert _record_is_local(str(workdir / "100")) is True
