"""Real MIT-BIH records through the `wfdb` library, with a local cache.

MIT-BIH Arrhythmia Database records are 30-minute, 360 Hz, two-channel
annotated ECG traces published on PhysioNet. They are the standard teaching and
benchmark material for exactly this kind of project, which is why the simulator
replays them rather than inventing a signal.

How the three failure modes are handled - because a demo that dies on a train
with no wifi is not a demo:

* `wfdb` is not installed      -> `load()` raises, the caller falls back
* the download fails/no network -> `load()` raises, the caller falls back
* the record is there already   -> read from `--ecg-data-dir`, no network at all

`wfdb.rdrecord` already prefers a local file under its `pn_dir`, and
`wfdb.dl_database` fetches one record on demand into that directory. Nothing
here ever recurses into `wfdb.dl_database`'s full-database mode, which would
pull ~100 MB for a 30-second smoke test.

Screening aid, not a medical diagnosis. MIT-BIH is a research corpus of
recorded arrhythmias, used here as a realistic *signal*, not as a patient.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

from simulator.ecg.source import (
    DEFAULT_SOURCE_FRAMES,
    ECGSource,
    NoiseConfig,
    NoiseLayer,
)

#: The classic first record of the MIT-BIH Arrhythmia Database.
DEFAULT_RECORD = "100"
DEFAULT_PN_DIR = "mitbih-arrhythmia-database-1.0.0"
DEFAULT_ECG_DATA_DIR = "simulator/.ecg-data"


class WFDBUnavailable(RuntimeError):
    """`wfdb` (or its science dependencies) could not be imported."""


def _import_wfdb():
    """Import `wfdb`, or explain precisely why we cannot.

    Imported lazily on purpose: the synthetic path must work on a machine where
    `wfdb` was never installed, so nothing at module import time may touch it.
    """
    try:
        import wfdb  # noqa: PLC0415 - lazy by design
    except Exception as exc:  # pragma: no cover - depends on the environment
        raise WFDBUnavailable(f"wfdb is not installed: {exc}") from exc
    return wfdb


class WFDBECGSource(ECGSource):
    """A stream of samples read from one MIT-BIH record.

    The record is fetched once, in full, and then replayed frame by frame. Two
    channels exist in MIT-BIH; channel 0 (MLII, a modified lead II) is the one
    with the clearest QRS morphology, so that is the default.
    """

    source_name = "mitbih"

    def __init__(
        self,
        *,
        record_name: str = DEFAULT_RECORD,
        channel: int = 0,
        data_dir: str = DEFAULT_ECG_DATA_DIR,
        frames: int = DEFAULT_SOURCE_FRAMES,
        download: bool = True,
        frame_seconds: float = 1.0,
        repeat: bool = True,
        noise: NoiseLayer | NoiseConfig | None = None,
        seed: int | None = None,
    ) -> None:
        wfdb = _import_wfdb()

        self.record_name = record_name
        self.channel = channel
        self.data_dir = os.path.abspath(data_dir)
        self.downloaded = False
        self.streamed = False
        self.repeat = repeat
        os.makedirs(self.data_dir, exist_ok=True)

        record = self._read(wfdb, download=download)

        # `p_signal` is already in physical units (mV for MIT-BIH), which is
        # exactly the unit `POST /sensor/ecg` wants - no gain conversion here.
        # The array is kept as it is and converted a frame at a time: converting
        # and noising 650 000 samples up front costs seconds, and a 30-second run
        # consumes 6 000 of them.
        self._signal = record.p_signal
        self._row_count = int(self._signal.shape[0])
        source_rate = float(record.fs)

        super().__init__(sample_rate_hz=source_rate, frames=frames)
        # The record's own rate is only known now, so `--noise` is switched on
        # here rather than by the caller.
        if isinstance(noise, NoiseLayer):
            self.noise = noise
        elif isinstance(noise, NoiseConfig):
            self.enable_noise(noise, seed=seed)

        self._cursor = 0
        self._frame_samples = max(1, int(round(frame_seconds * source_rate)))

    # -- bounds ------------------------------------------------------------

    @property
    def total_samples(self) -> int | None:
        """The record's own length, or `None` when it is being repeated.

        A MIT-BIH record is 30 minutes; a session may be longer. Repeating is a
        better failure mode for a simulator than an exception mid-demo, but the
        resampler then cannot know the length, so a caller that needs an exact
        count (the simulator) supplies its own budget from the run duration.
        """
        if self.repeat:
            return None
        return self._row_count

    # -- loading -----------------------------------------------------------

    def _read(self, wfdb, *, download: bool):
        """Read the record: local cache first, then PhysioNet, then a download.

        Three strategies, in the order that costs least:

        1. **local cache** - `<data_dir>/<record>.hea` + `.dat`, no network;
        2. **stream from PhysioNet** - `rdrecord(name, pn_dir="mitdb")` reads the
           record straight over HTTP and never writes anything. This is the path
           that works in a restricted environment, because `dl_database` uses a
           thread pool and a thread pool needs a named pipe, which some sandboxes
           refuse to create;
        3. **download into the cache** - `dl_database`, so the next run is
           offline and instant.
        """
        record_path = os.path.join(self.data_dir, self.record_name)
        if _record_is_local(record_path):
            return wfdb.rdrecord(record_path)

        if not download:
            raise WFDBUnavailable(
                f"record {self.record_name} is not in {self.data_dir} and "
                "--no-ecg-download was given"
            )

        try:
            # `pn_dir` names the PhysioNet *database*; wfdb appends the record
            # name itself, so passing "mitdb/100" would ask for 100/100.hea.
            record = wfdb.rdrecord(self.record_name, pn_dir="mitdb")
            self.streamed = True
            return record
        except Exception as exc:  # noqa: BLE001 - fall through to the download
            stream_error = exc

        try:
            wfdb.dl_database(
                "mitdb",
                dl_dir=self.data_dir,
                records=[self.record_name],
                overwrite=False,
            )
        except Exception as exc:  # noqa: BLE001 - report the first failure
            raise WFDBUnavailable(
                f"could not stream or download {self.record_name!r} from PhysioNet: "
                f"{stream_error}; download also failed: {exc}"
            ) from exc

        self.downloaded = True
        return wfdb.rdrecord(record_path)

    # -- ECGSource ---------------------------------------------------------

    def _next_frame(self) -> Iterator[float]:
        """Read `frame_samples` samples, looping back to the start at the end.

        The physical value is extracted one sample at a time, and only for the
        samples that are actually consumed: a MIT-BIH record is 650 000 samples,
        a 30-second run needs 6 000 of them, and converting the whole record up
        front is seconds of work for data nothing will look at. Looping is
        deliberate - a record is 30 minutes and a session may be longer, and a
        repeating trace is a far better failure mode for a demo than an
        exception in the middle of it.
        """
        for _ in range(self._frame_samples):
            if self._cursor >= self._row_count:
                self._cursor = 0
            yield float(self._signal[self._cursor, self.channel])
            self._cursor += 1


def _record_is_local(path: str) -> bool:
    """A WFDB record is a pair: `<name>.hea` (header) and `<name>.dat` (signal)."""
    return os.path.exists(path + ".hea") and os.path.exists(path + ".dat")


__all__ = [
    "DEFAULT_ECG_DATA_DIR",
    "DEFAULT_PN_DIR",
    "DEFAULT_RECORD",
    "WFDBECGSource",
    "WFDBUnavailable",
]
