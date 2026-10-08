# Phase 3 notes — the device simulator

Phase 3 answers one question: **what does a real device look like from the
telemetry service's point of view, and how do we produce that on demand?** It is
a program that plays a patient monitor — heartbeat, four scalar vitals and a
stream of ECG — against the Phase 2 FastAPI service, using exactly the payloads
the ESP32 firmware will send.

Scope: `simulator/` plus the two smoke-test helpers it needs in
`backend/django/scripts/`. Nothing under `backend/fastapi/` changed; the
simulator was written *to* that contract, not the other way round.

The system is a **screening aid, not a medical diagnosis**. Every sample the
simulator sends is synthetic or replayed research data, and none of it is a
clinical finding. The wording appears in the simulator's log banner, in its
`--help`, in the `User-Agent` it sends, and at the end of its summary.

---

## 1. Layout — which folders are involved

### 1.1 Simulation (the code that produces data)

```
simulator/                        <- the whole simulator; its own venv, its own requirements
  __init__.py                     the package, and the version string
  __main__.py                     `python -m simulator` -> cli.main
  run.py                          `python simulator/run.py` -> the same main()
  cli.py                          argument parsing, env vars, validation, exit codes
  config.py                       the Config object; where each value comes from
  ranges.py                       the Phase 2 limits, in one place
  sensors.py                      the four scalar random walks
  simulator.py                    the run loop, the stats, the summary
  transport.py                    the retrying, logging HTTP client
  ecg/
    __init__.py                   the ECG pipeline's public surface
    source.py                     ECGSource + the synthetic PQRST generator + NoiseLayer
    mitbih.py                     real MIT-BIH records through the wfdb library
    sources.py                    the auto / mitbih / synthetic decision and the fallback
    signal.py                     resampling and chunking
  tests/                          the pytest suite (see 1.3)
  requirements.txt                httpx + wfdb
  requirements-dev.txt            the above + the backend's test requirements
  pytest.ini                      pythonpath, basetemp, norecursedirs
  .venv/                          created once; gitignored
  .ecg-data/                      MIT-BIH records cached on disk; gitignored
```

The pipeline is one direction only:

```
source (360 Hz, mV) ──> +noise ──> resample (200 Hz) ──> chunk (2 s) ──> POST /sensor/ecg
sensors.py (random walks) ────────────────────────────────────────────> POST /sensor/data
heartbeat every 10 s ─────────────────────────────────────────────────> POST /sensor/connect
```

### 1.2 Folders outside `simulator/` that Phase 3 touches

| Path | Why Phase 3 needs it | Changed? |
| --- | --- | --- |
| `backend/fastapi/` | the service being simulated — read for the contract, never modified | no |
| `backend/django/scripts/mint_run.py` | Phase 2's mint helper: reuses the device's existing active session | no |
| `backend/django/scripts/mint_common.py` | **new** — the demo users/device/tokens shared by both mint scripts | yes |
| `backend/django/scripts/mint_new.py` | **new** — mints a *brand new* session, which is what row counting needs | yes |
| `backend/django/scripts/mint_new_run.py` | **new** — bootstraps Django, then runs `mint_new.py` (mirrors `mint_run.py`) | yes |
| `scripts/smoke-phase3.ps1` | **new** — the automated end-to-end proof | yes |
| `docs/phase-3-notes.md` | this file | new |
| `docs/phase-3-smoke-test.md` | the copy/paste proof | new |
| `.smoke/` | `mint.txt`, run summaries, row counts, transcripts (gitignored) | — |

`backend/django/scripts/mint_new.py` exists because Django enforces **one active
session per device** with a partial unique index. Phase 2's `mint.py` reuses the
active session, which is right for "does ingestion work" but wrong for "count the
rows this run stored": a re-send would look like a duplicate because of an
earlier run rather than because of the retry being tested. `mint_new.py` closes
the open session and creates a fresh one, so a run's counts belong to that run
alone.

### 1.3 Testing (where the tests live and what runs them)

```
simulator/tests/
  __init__.py
  conftest.py                     shared fixtures: app environment, identity, workdir
  test_sensors.py                 the four scalar walks: range, band, drift, movement
  test_ecg_signal.py              resampling counts, ramp interpolation, noise, chunking
  test_ecg_sources.py             synthetic generator, source choice, MIT-BIH failure path
  test_config_cli.py              mint-file parsing, precedence, validation, argparse
  test_ranges_match_api.py        the simulator's limits == the API's limits
  test_api_integration.py         the simulator against the real FastAPI app (TestClient)
```

| Runner | Command | What it needs |
| --- | --- | --- |
| Simulator suite | `cd simulator ; ..\.venv\Scripts\python -m pytest -q` | `simulator/requirements-dev.txt` |
| Phase 2 suite | `cd backend\fastapi ; python -m pytest -q` | unchanged, untouched by Phase 3 |

`test_api_integration.py` imports `app.*`, so it needs the backend's requirements
*and* the backend on `sys.path`. Both are handled without a `pip install -e`:
`simulator/requirements-dev.txt` includes `backend/fastapi/requirements-dev.txt`,
and `simulator/pytest.ini` sets `pythonpath = . ../backend/fastapi`. Run under a
venv that has neither and the file skips itself with that reason instead of
erroring.

## 2. What is being simulated: 4 sensors + 1 waveform

The device is simulated at the level the API models it: **four scalar sensors**
plus **one ECG waveform stream**. That is not an arbitrary split — it is exactly
what `POST /sensor/data` and `POST /sensor/ecg` accept.

| # | Signal | Endpoint | Unit | Legal range (Phase 2) | Band the simulator keeps to | Reported as |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `temperature` | `/sensor/data` | `celsius` | 25 – 45 °C | 35.8 – 38.2 °C | 0.1 °C steps |
| 2 | `spo2` | `/sensor/data` | `percent` | 50 – 100 % | 94 – 99 % | 0.1 % steps |
| 3 | `pulse` | `/sensor/data` | `bpm` | 20 – 250 bpm | 55 – 105 bpm | whole bpm |
| 4 | `motion` | `/sensor/data` | `a.u.` | 0 – 100 a.u. | 0 – 40 a.u. | 0.01 a.u. steps |
| 5 | ECG waveform | `/sensor/ecg` | millivolts | ±20 mV per sample, 100–2000 Hz, 1–5000 samples/chunk | R wave ≈ 1.0 mV | 400 samples/chunk at 200 Hz |

**A note on the count.** There are **four scalar sensors** (temperature, SpO2,
pulse, motion) and **one ECG channel** (a single lead, channel 0 / MLII of the
MIT-BIH record). The simulator is not pretending to be a 12-lead ECG machine:
the Phase 2 API stores one `samples` array per chunk, and the firmware this
stands in for reads one lead. So "how many sensors" has two honest answers —
**4 scalar + 1 ECG stream = 5 things on the wire**, of which 4 are rows in
`sensor_readings` and 1 is rows in `ecg_chunks`.

Per batch (default: every 1 s) the simulator sends **four** readings, all sharing
one `recorded_at`, which is what real firmware does and what keeps the
idempotency key `(session_id, sensor_type, recorded_at)` stable across a retry.
The heartbeat goes to `/sensor/connect` every 10 s (the API's own `online`
threshold is 120 s, so 10 s is comfortably inside it).

### 2.1 The scalar sensors: a bounded random walk

`ranges.py` holds one `ScalarSpec` per sensor: the protocol limits, a tighter
realistic band, the largest per-second step, and the resolution of the *reading*.
`sensors.py` walks each value by a random step, clamped to the band.

Two decisions matter:

* **The walk is continuous and only the reading is rounded.** Rounding the state
  freezes the walk: temperature moves ~0.02 °C per second, so a state rounded to
  0.1 °C rounds straight back to where it started, every second, forever — the
  original bug, a flat line at 36.8. Keeping the state as a float and rounding on
  the way out gives a thermometer that reads 36.8 for a while and then ticks to
  36.9. `test_the_walk_is_continuous_even_when_the_reading_is_not` is the
  regression test.
* **The band is well inside the legal range.** A boundary value is one rounding
  error from a 422, and a body temperature of 45 °C is meaningless as data even
  though the API would take it.

Each sensor has its own RNG stream but they share one seed, so a `--seed` value
reproduces a whole run. `--drop-chunks` and `--resend-chunks` draw from a
*different* stream than the vitals, so changing a drop probability does not
change the readings.

### 2.2 The ECG: a real record, or a synthetic one

| Piece | File | What it does |
| --- | --- | --- |
| `ECGSource` | `ecg/source.py` | the interface: frames of mV at a fixed rate, plus `total_samples` when the length is known |
| `SyntheticECGSource` | `ecg/source.py` | PQRST generator: five Gaussian bumps per beat (P, Q, R, S, T), ~72 bpm with R-R jitter. Standard library only, loops forever |
| `WFDBECGSource` | `ecg/mitbih.py` | one MIT-BIH Arrhythmia Database record via `wfdb`, channel 0, in mV, loops forever |
| `NoiseLayer` | `ecg/source.py` | 50 Hz mains hum, 0.25 Hz breathing/0.05 Hz drift wander, rare 0.5–2 mV movement spikes |
| `ResampledECGSource` | `ecg/signal.py` | linear interpolation to the target rate, with an exact output length |
| `Chunker` | `ecg/signal.py` | cuts the stream into 1–5 s chunks with stable `chunk_index` and `start_time` |

Three source modes, chosen by `--ecg-source`:

* `auto` (default) — try MIT-BIH, fall back to synthetic with a warning;
* `mitbih` — demand MIT-BIH and fail loudly if it cannot be read;
* `synthetic` — never touch the network or `wfdb`.

**Why "stream over HTTP, then cache" and not just `wfdb.dl_database`.** The MIT-BIH
loader tries three things in cost order: the local cache in `simulator/.ecg-data/`
(two files, `<record>.hea` + `<record>.dat`), then `wfdb.rdrecord(name,
pn_dir="mitdb")`, which reads the record straight over HTTP and writes nothing,
then `wfdb.dl_database` to populate the cache. The middle path exists because
`dl_database` builds a thread pool, and a thread pool needs a named pipe — which
a confined Windows sandbox refuses to create. Streaming works where the download
does not, and the cache means the cost is paid once. A cold fetch of record 100 is
~1.9 MB and took ~95 s on this connection; every later run is offline and instant.

**Why noise is applied to the *source*, not to the resampler.** A real front-end
picks up hum before the rate is changed, so the resampler band-limits it — that is
the honest order. It is also much cheaper: four `sin` calls per source sample
instead of per interpolated sample. This was measured, not assumed: the
resampler-located version managed ~300 interpolated samples/second, which is a
fifth of what a 200 Hz stream needs.

**Why resampling is exact.** `resampled_length(n, source_rate, target_rate)`
computes the output count up front (`round(n × target / source)`), and the
iterator is a counted loop. Stopping on "the source ran out" is what produces a
chunk one sample short — a seam in the waveform that is invisible in a 400-sample
list and impossible to argue about in a demo. There is a test with a hand-computed
ramp (`0, 0.5, 1, 1.5, …`) that pins both the count and the interpolation, and it
is the test that caught the trim window dropping the lower neighbour.

**Chunk identity.** `chunk_index` is derived from the chunk's position in the
stream, never from a counter that the drop logic could skip — otherwise a dropped
chunk would renumber every chunk after it and a re-send would carry the wrong
index. `start_time` is `epoch + chunk_index × chunk_seconds`, computed once at
`Simulator` construction, so it is a strictly increasing absolute UTC timestamp in
the past and byte-identical on a re-send.

## 3. The run loop

One thread, one `time.monotonic()` clock, and a loop that sleeps only until the
next thing is due (`simulator/simulator.py`). No `asyncio`, no threads: at a few
requests a second a simple scheduler is easier to read and to explain than a task
graph, and every request is logged in the order it happened, which is what makes a
smoke transcript useful.

```
connect ──┬─ every --interval (1 s)      : four scalar readings
          ├─ every --heartbeat-seconds   : POST /sensor/connect
          └─ every --ecg-chunk-seconds   : one ECG chunk (sent as fast as produced)
```

`--offline-after N` sets the loop's deadline to `min(duration, N)` and logs the
transition: the device simply stops. Nothing is closed, because the API decides
offline from `last_seen` — which is the point of testing it.

## 4. Edge-case flags

| Flag | What it does | Where it shows up |
| --- | --- | --- |
| `--noise` | 50 Hz hum, baseline wander, random spikes at the source rate | clamp counter in the summary; `clamped 0` on a clean run |
| `--drop-chunks P` | skips a produced chunk with probability P | a **gap in `chunk_index`** — no row, no error |
| `--resend-chunks P` | re-sends an already-sent chunk with probability P | `duplicate: true`, one row in the DB |
| `--offline-after S` | stops heartbeat and data after S seconds | `last_seen` stops advancing |

Each is one or two lines in `_send_due_chunks`, deliberately: an edge case that
needs a special code path is an edge case nobody tests.

## 5. Reliability

| Property | How |
| --- | --- |
| Retry | `Transport.post` retries connection errors, timeouts, 429 and 5xx |
| Backoff | exponential with full jitter, capped at 8 s; a `Retry-After` is not required to be well-behaved |
| No pointless retries | a 4xx that is not 429/408 is *permanent*: returned immediately and counted, because retrying a 422 five times wastes five round trips |
| Every response logged | one line per request: label, status, milliseconds, body — the body is where `code` and the per-field messages live |
| Fail fast | `POST /sensor/connect` is a preflight; 401/403/404 there ends the run with the server's own message instead of 30 seconds of pointless retries |
| Deterministic | `--seed` reproduces a run; retries rebuild the same body, which is what makes a retry a duplicate rather than a second reading |
| Summary | per-sensor sent/stored/duplicate/failed, ECG produced/sent/stored/duplicate/dropped/resent, sample count and mV range, HTTP status histogram — printed as a table and written as JSON with `--output-json` |

## 6. Tests

```powershell
cd simulator
..\.venv\Scripts\python -m pytest -q
```

95 tests, and they are not decoration — four real bugs were found by them
(a frozen temperature walk, an off-by-one resample, a trim window that dropped the
interpolation's lower neighbour, and a missing epoch in the chunk timestamp).

| File | Covers |
| --- | --- |
| `test_sensors.py` | every generated value inside the protocol range and the tighter band, across many seeds; no step larger than the spec; the walk moves even when the reading repeats; clamp/round boundaries |
| `test_ecg_signal.py` | `N` seconds at `R` Hz is exactly `N × R` samples (six rate pairs); a hand-computed ramp interpolates correctly; a looping source must be given a length; noise changes the signal and stays legal; the sanitiser clamps and counts; chunk indexes, start times, short final chunk, `chunk_index` independent of sample values, the 1–5000 sample limit |
| `test_ecg_sources.py` | the synthetic generator's amplitude, beat count (~12 in 10 s at 72 bpm) and reproducibility; `auto` falls back with a reason; `mitbih` raises instead of hiding a failure; the cache is detected by `.hea` **and** `.dat` |
| `test_config_cli.py` | `.smoke/mint.txt` parsing; argument > environment > file precedence; `ECG_SIM_*` typing; `--offline-after` shortens the run; ten invalid configurations are refused |
| `test_ranges_match_api.py` | the simulator's `SCALARS`, unit spellings and ECG limits equal `backend/fastapi/app/schemas.py` and `core/config.py`; generated values pass the **real** `SensorDataRequest` model; `chunk_index`'s upper bound matches the API's |
| `test_api_integration.py` | the simulator against the real app in-process: heartbeat row; all four sensors stored with units and ranges read back from SQLite; one row per chunk with array-valued `samples`; `--resend-chunks 1.0` → twice the requests, half the rows; `--drop-chunks 1.0` → no requests, no rows; duplicate scalar reading → one row; the summary JSON's shape |

The `test_ranges_match_api.py` file is the one that keeps **two copies of a
number** honest. `ranges.py` restates the API's ranges because the simulator must
not import the service it is testing; the test compares them, so a range widened
in the backend fails the simulator's suite instead of letting it generate 46 °C
readings that answer 422.

## 7. Running it

```powershell
cd simulator
..\.venv\Scripts\Activate.ps1

python -m simulator --help
python -m simulator --duration 30                    # heartbeat + scalars only
python -m simulator --duration 30 --ecg              # + MIT-BIH ECG chunks
python -m simulator --ecg --noise --drop-chunks 0.1 --resend-chunks 0.1
python -m simulator --ecg --offline-after 10 --duration 30
```

`--device-token` and `--session-id` (and the rest) are read from
`ECG_SIM_*` environment variables and then from `.smoke/mint.txt`, so with a
minted session the command is just the one line above. `python simulator/run.py`
is the same entry point for anyone who prefers that spelling.

## 8. Deliberate limits

* **One device, one session per run.** The simulator does not fan out to N
  devices; that is a load test, and `--duration`/`--interval` plus a shell loop
  is the honest way to get it.
* **One ECG lead.** The API stores one `samples` array per chunk; a 12-lead
  device would need 12 chunks per window and a schema change. Not pretended.
* **The ECG record is replayed, not interpreted.** No arrhythmia labels are read
  from the `.atr` file and no beat annotations are sent — the API has nowhere to
  put them and Phase 5 is where ECG inference lives.
* **`--noise` is additive and uncalibrated.** It is an artefact generator for
  testing an ingest path, not a signal-quality model.
* **The random walk is not physiology.** It is a plausible drift, bounded by the
  protocol, and it will not produce a fever curve or a desaturation event on its
  own; `--drop-chunks` and a scripted `force()` are how you stage those.
* **No WebSocket client.** The socket is Phase 2's viewer path and
  `backend/fastapi/scripts/ws_watch.py` already covers it; the simulator's own
  WebSocket testing is a browser or that script.
* **Timing is best-effort.** The loop aims at `--interval` and drifts when a
  request retries; a run of 30 s at 1 s produced 29 batches, not 31. Exact rate
  control needs a scheduler that the demo does not justify.
* **`--duration` is wall-clock, not sample-exact.** A 30 s run at 2 s chunks
  produced 17 chunks (34 s of signal) because the last partial chunk is sent
  rather than padded with invented samples.
* **The MIT-BIH cache is per-repository.** `simulator/.ecg-data/` is gitignored,
  so a fresh clone pays one slow download (or falls back to synthetic, which is
  the designed behaviour).
* **Not a clinical device.** No calibration, no alarm thresholds, no
  regulatory anything. Screening aid, not a medical diagnosis.

## 9. Decisions made while building this (recorded, as requested)

1. **The contract was read before a line was written**, and `ranges.py` restates
   its numbers rather than importing them — with `test_ranges_match_api.py` as the
   guard against drift. The simulator must be able to run without the service.
2. **Rounding is applied to readings, not to state.** The first version of the
   temperature walk sat at exactly 36.8 forever; the fix and its regression test
   are described in §2.1.
3. **The resample length is computed, not accumulated.** `round(n × target /
   source)` plus a counted loop replaced a float-position `while` that stopped one
   sample early.
4. **Noise moved from the resampler to the source.** Honest order, and ~4× the
   throughput; the measurement is in §2.2.
5. **`_next_frame` yields instead of returning a list.** Building a 200-sample
   frame of PQRST arithmetic that the resampler only partly consumes was the most
   expensive thing in the program.
6. **MIT-BIH streams over HTTP before it downloads.** `dl_database`'s thread pool
   needs a named pipe, which the confinement here denies; `rdrecord(pn_dir=...)`
   does not, and the local cache makes it a one-time cost.
7. **A second mint script was added instead of editing Phase 2's.** `mint.py`
   reuses the active session (right for Phase 2's proof); counting rows needs a
   session nothing else has written to, so `mint_new.py` closes the open session
   and makes a new one. The shared setup moved into `mint_common.py` rather than
   being copied.
8. **The integration test drives the real app through `TestClient`,** swapping only
   the HTTP call under `Transport` — so retries, response parsing and the stats are
   the production code, and the duplicate-chunk assertion is a statement about the
   database's unique index rather than about a mock.
9. **Both the script and the suite were kept.** `scripts/smoke-phase3.ps1` is what
   proves the journey against a live service and prints the row counts; the suite
   is what keeps it true on a machine with nothing running.
10. **The simulator's values were verified live**: against a real Django session and
    the live FastAPI service, 30 s with `--ecg` on stored 58 readings per sensor
    (232 rows) and 17 ECG chunks / 6600 samples, with 146 requests, 0 retries and 0
    failures — every status 200. The transcript is in
    `docs/phase-3-smoke-test.md`.
