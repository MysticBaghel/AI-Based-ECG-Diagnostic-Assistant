"""The run loop: heartbeat, scalars and ECG chunks on their own timers.

Shape of one run:

    connect (heartbeat) ──┬─ every `--interval` : four scalar readings
                          ├─ every 10 s          : another heartbeat
                          └─ every `--ecg-chunk-seconds` : one ECG chunk

One thread, one `time.monotonic()` clock, and a loop that sleeps only until the
next thing is due. No `asyncio`, no threads: at a few requests per second a
simple scheduler is easier to read - and to explain - than a task graph, and
every request is logged in the order it happened, which is what makes a smoke
transcript useful.

The four edge-case flags are one or two lines each, which is deliberate: an
edge case that needs a special code path is an edge case nobody tests.

Screening aid, not a medical diagnosis.
"""

from __future__ import annotations

import json
import logging
import random
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from simulator.config import Config
from simulator.ecg import Chunker, NoiseConfig, ResampledECGSource, SourceRequest, build_ecg_source
from simulator.ranges import SENSOR_TYPES
from simulator.sensors import ScalarSensorSet
from simulator.transport import Transport, utc_now_iso

logger = logging.getLogger("simulator")

#: Reported by `POST /sensor/connect`; also what the device row shows.
FIRMWARE_VERSION = "sim-3.0.0"
DEVICE_IP = "127.0.0.1"


@dataclass
class ReadingStats:
    """Per-sensor counters: what happened to every reading we tried to send."""

    sent: int = 0
    stored: int = 0
    duplicates: int = 0
    failed: int = 0
    last_value: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "sent": self.sent,
            "stored": self.stored,
            "duplicates": self.duplicates,
            "failed": self.failed,
            "last_value": self.last_value,
        }


@dataclass
class RunStats:
    """Everything the end-of-run summary reports."""

    readings: dict[str, ReadingStats] = field(
        default_factory=lambda: {name: ReadingStats() for name in SENSOR_TYPES}
    )
    heartbeats_sent: int = 0
    heartbeats_failed: int = 0
    #: chunk_index values the ECG stream produced
    chunks_produced: int = 0
    #: chunk_index values deliberately skipped by `--drop-chunks`
    chunks_dropped: int = 0
    #: chunks that reached the server (first attempt or retry, all count)
    chunks_sent: int = 0
    #: `stored: true` answers
    chunks_stored: int = 0
    #: `duplicate: true` answers - `--resend-chunks`, or a retry after a timeout
    chunks_duplicate: int = 0
    chunks_failed: int = 0
    #: deliberate re-sends of an already-sent index (`--resend-chunks`)
    chunks_resent: int = 0
    samples_sent: int = 0
    #: samples clamped to +/-20 mV so the API would not reject the chunk
    samples_clamped: int = 0
    #: lowest and highest sample actually sent, in mV
    sample_min_mv: float | None = None
    sample_max_mv: float | None = None
    dropped_indexes: list[int] = field(default_factory=list)
    resent_indexes: list[int] = field(default_factory=list)
    offline_at_seconds: float | None = None
    started_at: str = ""
    finished_at: str = ""
    wall_seconds: float = 0.0
    transport: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """The JSON written to `--output-json` and printed as `SUMMARY ...`."""
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "wall_seconds": round(self.wall_seconds, 3),
            "readings": {name: stats.as_dict() for name, stats in self.readings.items()},
            "readings_total": {
                "sent": sum(s.sent for s in self.readings.values()),
                "stored": sum(s.stored for s in self.readings.values()),
                "duplicates": sum(s.duplicates for s in self.readings.values()),
                "failed": sum(s.failed for s in self.readings.values()),
            },
            "heartbeats": {"sent": self.heartbeats_sent, "failed": self.heartbeats_failed},
            "ecg": {
                "chunks_produced": self.chunks_produced,
                "chunks_sent": self.chunks_sent,
                "chunks_stored": self.chunks_stored,
                "chunks_duplicate": self.chunks_duplicate,
                "chunks_resent": self.chunks_resent,
                "chunks_dropped": self.chunks_dropped,
                "chunks_failed": self.chunks_failed,
                "chunks_unique_stored": self.chunks_stored - self.chunks_resent,
                "samples_sent": self.samples_sent,
                "samples_clamped": self.samples_clamped,
                "sample_min_mv": self.sample_min_mv,
                "sample_max_mv": self.sample_max_mv,
                "dropped_indexes": self.dropped_indexes[:50],
                "resent_indexes": self.resent_indexes[:50],
                "offline_at_seconds": self.offline_at_seconds,
            },
            "transport": self.transport,
            "notes": self.notes,
        }


class ECGSimulator:
    """Runs one simulated device against one session."""

    def __init__(self, config: Config, *, transport: Transport | None = None) -> None:
        self.config = config
        self.sensors = ScalarSensorSet(seed=config.seed)
        # Deliberately a *different* RNG stream from the sensors, so that
        # `--drop-chunks` decisions do not change the vitals sequence. With one
        # stream, changing the drop probability would change the data too, and
        # the run would stop being reproducible in the way that matters.
        self.rng = random.Random(None if config.seed is None else config.seed + 1)
        self.transport = transport or Transport(
            base_url=config.base_url,
            token=config.device_token or "",
            timeout_seconds=config.timeout_seconds,
            max_attempts=config.max_attempts,
            seed=config.seed,
        )
        self.stats = RunStats(notes=[])

        # One wall-clock reference for the whole run. Every timestamp the
        # simulator sends - `recorded_at` on a reading, `start_time` on a chunk -
        # is this instant plus an offset in seconds, so all of them line up on
        # one timeline and a retry reproduces the same value byte for byte.
        self.start_epoch = time.time()

    # -- helpers -----------------------------------------------------------

    @property
    def session_id(self) -> str:
        return self.config.session_id or ""

    def _iso(self, seconds_since_start: float) -> str:
        """`start_epoch` plus an offset, as the RFC 3339 UTC string the API wants.

        The API rejects a timestamp more than `MAX_FUTURE_SECONDS` (300) ahead of
        its own clock, so the offset is always in the past by construction:
        a chunk's `start_time` is `chunk_index x chunk_seconds`, and that much
        time has already elapsed by the time the chunk is sent.
        """
        return datetime.fromtimestamp(
            self.start_epoch + seconds_since_start, tz=timezone.utc
        ).isoformat()

    def _record_reading(self, sensor_type: str, value: float, response) -> None:
        stats = self.stats.readings[sensor_type]
        stats.sent += 1
        stats.last_value = value
        if not response.ok:
            stats.failed += 1
        elif response.body.get("duplicate"):
            stats.duplicates += 1
        else:
            stats.stored += 1

    # -- the individual sends ----------------------------------------------

    def send_heartbeat(self) -> None:
        """`POST /sensor/connect` - the heartbeat the dashboard reads."""
        response = self.transport.post(
            "/sensor/connect",
            {"firmware_version": FIRMWARE_VERSION, "ip_address": DEVICE_IP},
            label="POST /sensor/connect",
        )
        if response.ok:
            self.stats.heartbeats_sent += 1
        else:
            self.stats.heartbeats_failed += 1

    def send_scalars(self, recorded_at: str) -> None:
        """One reading per sensor, all sharing one timestamp for the batch.

        The timestamp is generated once per tick and reused for all four
        readings: it is half of the idempotency key `(session, type,
        recorded_at)`, so a fixed value means a retry after a timeout is
        recognised as a duplicate instead of being stored twice.
        """
        for reading in self.sensors.sample_all():
            payload = {
                "session_id": self.session_id,
                "sensor_type": reading.sensor_type,
                "value": reading.value,
                "unit": reading.unit,
                "recorded_at": recorded_at,
            }
            response = self.transport.post(
                "/sensor/data",
                payload,
                label=f"POST /sensor/data {reading.sensor_type}",
            )
            self._record_reading(reading.sensor_type, reading.value, response)

    def send_chunk(self, chunk, *, resent: bool) -> None:
        """`POST /sensor/ecg` for one chunk, with its `chunk_index` intact.

        `chunk.start_time` is seconds since the start of the ECG stream, so it
        becomes an absolute UTC timestamp only after the run epoch is added.
        """
        payload = {
            "session_id": self.session_id,
            "chunk_index": chunk.chunk_index,
            "start_time": self._iso(chunk.start_time),
            "sample_rate_hz": chunk.sample_rate_hz,
            "samples": chunk.samples,
        }
        response = self.transport.post(
            "/sensor/ecg",
            payload,
            label=f"POST /sensor/ecg #{chunk.chunk_index}",
        )

        self.stats.chunks_sent += 1
        if resent:
            self.stats.chunks_resent += 1
        if not response.ok:
            self.stats.chunks_failed += 1
            return
        if response.body.get("duplicate"):
            self.stats.chunks_duplicate += 1
        else:
            self.stats.chunks_stored += 1
            self.stats.samples_sent += chunk.sample_count
            self._note_samples(chunk.samples)

    def _note_samples(self, samples: list[float]) -> None:
        """Track the range of what we actually sent, for the summary."""
        if not samples:
            return
        low, high = min(samples), max(samples)
        self.stats.sample_min_mv = low if self.stats.sample_min_mv is None else min(self.stats.sample_min_mv, low)
        self.stats.sample_max_mv = high if self.stats.sample_max_mv is None else max(self.stats.sample_max_mv, high)

    # -- the loop ----------------------------------------------------------

    def run(self) -> RunStats:
        """Produce data until the duration (or `--offline-after`) is up."""
        started = time.monotonic()
        self.stats.started_at = self._iso(0.0)
        effective = self.config.effective_duration()

        logger.info("session %s", self.session_id)
        logger.info("plan: %s", self.config.describe())
        if self.config.offline_after_seconds is not None and effective < self.config.duration_seconds:
            logger.info(
                "the device will stop after %.0fs and do nothing for the rest of the %.0fs run "
                "(simulating a dropped-off device)",
                effective,
                self.config.duration_seconds,
            )

        # The first heartbeat is sent even when `--offline-after 0` is asked
        # for: the point of that flag is a device that *goes* offline, and a
        # device that never appeared is a different scenario.
        self.send_heartbeat()

        next_heartbeat = self.config.heartbeat_seconds
        next_scalar = self.config.interval_seconds
        chunks = self._chunk_stream() if self.config.ecg else None

        while True:
            elapsed = time.monotonic() - started
            if elapsed >= effective:
                break

            if elapsed >= next_heartbeat:
                self.send_heartbeat()
                next_heartbeat += self.config.heartbeat_seconds

            if chunks is not None:
                # ECG goes out as fast as the chunks are produced: at 200 Hz a
                # 2 s chunk is 400 samples, which is a millisecond of work.
                # `next(...)` returns None once the stream is finished.
                self._send_due_chunks(chunks)

            if elapsed >= next_scalar:
                # Batch timestamp: the same instant for all four sensors, as
                # real firmware would do, and stable across a retry of the
                # batch - which is what makes the retry a duplicate.
                self.send_scalars(self._iso(elapsed))
                next_scalar += self.config.interval_seconds
                continue

            self._sleep_until(min(next_heartbeat, next_scalar, effective) - elapsed)

        # A final scalar batch when the run ends between two ticks, so a short
        # `--duration` still produces readings rather than a lone heartbeat.
        if self.config.interval_seconds > effective:
            self.send_scalars(self._iso(effective))

        if self.config.offline_after_seconds is not None:
            self.stats.offline_at_seconds = self.config.offline_after_seconds
            logger.info(
                "device offline after %.0fs: heartbeat and data stopped, no close message sent "
                "(the API decides offline from last_seen)",
                self.config.offline_after_seconds,
            )

        self.stats.wall_seconds = time.monotonic() - started
        self.stats.finished_at = utc_now_iso()
        stream = getattr(self, "_stream", None)
        self.stats.samples_clamped = stream.sanitiser.clamped if stream is not None else 0
        self._collect_transport_stats()
        return self.stats

    def _sleep_until(self, remaining: float) -> None:
        """Sleep, but never more than 0.25 s, so Ctrl+C stays responsive."""
        time.sleep(max(0.0, min(remaining, 0.25)))

    def _send_due_chunks(self, chunks) -> None:
        """Send one chunk if one is ready, applying the edge-case flags."""
        chunk = next(chunks, None)
        if chunk is None:
            return
        self.stats.chunks_produced += 1

        if self.config.drop_chunks > 0 and self.rng.random() < self.config.drop_chunks:
            # A dropped chunk is not "lost data" from the API's point of view:
            # the chunk_index simply never arrives. That is the gap the
            # dashboard has to cope with.
            self.stats.chunks_dropped += 1
            self.stats.dropped_indexes.append(chunk.chunk_index)
            logger.warning(
                "[drop] computed chunk #%d and skipped it on purpose (chunk_index will be missing)",
                chunk.chunk_index,
            )
            return

        self.send_chunk(chunk, resent=False)

        if self.config.resend_chunks > 0 and self.rng.random() < self.config.resend_chunks:
            # Same index, same samples, sent again: the API must answer
            # duplicate and store nothing. This is the idempotency proof.
            self.stats.resent_indexes.append(chunk.chunk_index)
            logger.info("[resend] sending chunk #%d a second time", chunk.chunk_index)
            self.send_chunk(chunk, resent=True)

    def _chunk_stream(self):
        """Build the ECG pipeline: source (+noise) -> resample -> chunk."""
        request = SourceRequest(
            kind=self.config.ecg_source,
            record=self.config.ecg_record,
            data_dir=self.config.ecg_data_dir,
            download=self.config.ecg_download,
            seed=self.config.seed,
            noise=NoiseConfig.all() if self.config.noise else NoiseConfig.none(),
        )
        source = build_ecg_source(request)
        self.stats.notes.extend(request.notes)

        if source.sample_rate_hz != self.config.ecg_sample_rate_hz:
            logger.info(
                "resampling %s Hz -> %s Hz",
                int(source.sample_rate_hz),
                self.config.ecg_sample_rate_hz,
            )
        else:
            logger.info(
                "source is already %s Hz; the resampler is a pass-through",
                self.config.ecg_sample_rate_hz,
            )
        if self.config.noise:
            logger.info(
                "noise on: 50 Hz mains hum, baseline wander and random spikes, "
                "added at %s Hz before resampling",
                int(source.sample_rate_hz),
            )

        stream = ResampledECGSource(
            source,
            target_sample_rate_hz=self.config.ecg_sample_rate_hz,
            max_source_samples=self._source_sample_budget(source),
        )
        # Kept so the run can report how many samples the +/-20 mV clamp saved.
        self._stream = stream
        return Chunker(
            stream,
            sample_rate_hz=self.config.ecg_sample_rate_hz,
            chunk_seconds=self.config.ecg_chunk_seconds,
        ).iter_chunks()

    def _source_sample_budget(self, source) -> int:
        """How many source samples this run will need, plus a margin.

        A source whose length it knows (MIT-BIH) reports it. The synthetic
        generator *can* produce `frames x frame_samples` samples, but that is its
        ceiling, not the run's requirement: asking for all of it would make the
        resampler interpolate 20 000 frames of signal for a 30-second run. A
        looping record reports no length at all, for the same reason.

        Either way the answer is the same: whatever `duration x source rate`
        needs, plus a chunk of slack for the final partial chunk.
        """
        needed_seconds = self.config.effective_duration() + self.config.ecg_chunk_seconds + 1.0
        return max(1, int(round(needed_seconds * float(source.sample_rate_hz))))

    def _collect_transport_stats(self) -> None:
        stats = self.transport.stats
        self.stats.transport = {
            "requests": stats.requests,
            "retries": stats.retries,
            "failures": stats.failures,
            "permanent_failures": stats.permanent_failures,
            "by_status": dict(sorted(stats.by_status.items())),
        }

    # -- reporting ---------------------------------------------------------

    def summary_text(self) -> str:
        """The end-of-run table a human reads."""
        lines: list[str] = []
        data = self.stats.as_dict()
        lines.append("")
        lines.append("=" * 72)
        lines.append("SIMULATOR SUMMARY (screening aid, not a medical diagnosis)")
        lines.append("=" * 72)
        lines.append(f"session            : {self.session_id}")
        lines.append(f"base url           : {self.config.base_url}")
        lines.append(f"wall clock         : {data['wall_seconds']:.1f}s of {self.config.duration_seconds:g}s requested")
        lines.append("")
        lines.append(f"{'sensor':<14}{'sent':>7}{'stored':>8}{'dup':>7}{'failed':>8}  last value")
        for name in SENSOR_TYPES:
            row = data["readings"][name]
            lines.append(
                f"{name:<14}{row['sent']:>7}{row['stored']:>8}{row['duplicates']:>7}"
                f"{row['failed']:>8}  {row['last_value']}"
            )
        total = data["readings_total"]
        lines.append(
            f"{'TOTAL':<14}{total['sent']:>7}{total['stored']:>8}{total['duplicates']:>7}"
            f"{total['failed']:>8}"
        )
        lines.append("")
        lines.append(f"heartbeats         : sent {data['heartbeats']['sent']}, failed {data['heartbeats']['failed']}")

        if self.config.ecg:
            ecg = data["ecg"]
            lines.append(
                f"ECG chunks         : produced {ecg['chunks_produced']}, sent {ecg['chunks_sent']}, "
                f"stored {ecg['chunks_stored']} (of which {ecg['chunks_resent']} re-sends), "
                f"duplicates {ecg['chunks_duplicate']}, dropped {ecg['chunks_dropped']}, "
                f"failed {ecg['chunks_failed']}"
            )
            lines.append(
                f"ECG samples        : {ecg['samples_sent']} stored, range "
                f"{ecg['sample_min_mv']} .. {ecg['sample_max_mv']} mV, "
                f"clamped {ecg['samples_clamped']}"
            )
            lines.append(
                f"ECG unique rows    : {ecg['chunks_unique_stored']} "
                "(stored minus deliberate re-sends) - must equal `ecg_chunks` rows for this session"
            )
            if ecg["dropped_indexes"]:
                lines.append(f"dropped indexes    : {ecg['dropped_indexes']}")
            if ecg["resent_indexes"]:
                lines.append(f"re-sent indexes    : {ecg['resent_indexes']}")
        else:
            lines.append("ECG chunks         : disabled (pass --ecg to send some)")

        lines.append(
            f"HTTP               : {data['transport'].get('requests', 0)} requests, "
            f"{data['transport'].get('retries', 0)} retries, "
            f"{data['transport'].get('failures', 0)} failed, statuses "
            f"{data['transport'].get('by_status', {})}"
        )
        if self.stats.offline_at_seconds is not None:
            lines.append(
                f"offline            : stopped after {self.stats.offline_at_seconds:g}s "
                "(device went away; last_seen in the DB stops advancing)"
            )
        if self.stats.notes:
            lines.append(f"ECG source         : {'; '.join(self.stats.notes)}")
        lines.append("=" * 72)
        return "\n".join(lines)

    def write_summary(self, path: str | None = None) -> str | None:
        """Write the machine-readable summary, if a path was configured."""
        target = path or self.config.output_json
        if not target:
            return None
        with open(target, "w", encoding="utf-8") as handle:
            json.dump(self.stats.as_dict(), handle, indent=2, sort_keys=True)
        logger.info("summary written to %s", target)
        return target


__all__ = ["ECGSimulator", "ReadingStats", "RunStats"]
