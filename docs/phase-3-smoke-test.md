# Phase 3 smoke test — copy/paste proof that the simulator fills the database

Every command below is ready to paste. It proves, in order:

1. a fresh session is minted in Django and registered with FastAPI;
2. the simulator stores a heartbeat and **four scalar sensors** — temperature,
   SpO2, pulse and motion — every second;
3. it replays **MIT-BIH ECG** and stores it as **one row per chunk**, never one
   row per sample;
4. a re-sent chunk (`--resend-chunks 1.0`) still stores exactly one row;
5. a dropped chunk (`--drop-chunks`) leaves a gap in `chunk_index` and no row;
6. `--offline-after` stops the device and the heartbeat stops advancing;
7. the row counts read back out of the database match what the simulator said it
   sent.

The contract these calls implement is `docs/api-contract.md`. The design behind
the simulator is `docs/phase-3-notes.md`, the same checks exist as a pytest suite
(`simulator/tests/`), and all of it is automated in `scripts/smoke-phase3.ps1`.

> The simulator produces synthetic data or replayed research data. This is a
> **screening aid, not a medical diagnosis** — nothing it sends is a clinical
> finding.

---

## 0. What is being simulated

**Four scalar sensors** go to `POST /sensor/data`:

| Signal | Unit | Phase 2 accepts | The simulator sends |
| --- | --- | --- | --- |
| `temperature` | `celsius` | 25 – 45 | 35.8 – 38.2 (0.1 steps) |
| `spo2` | `percent` | 50 – 100 | 94 – 99 (0.1 steps) |
| `pulse` | `bpm` | 20 – 250 | 55 – 105 (whole) |
| `motion` | `a.u.` | 0 – 100 | 0 – 40 (0.01 steps) |

**One ECG waveform** goes to `POST /sensor/ecg`: a single lead (channel 0 / MLII
of a MIT-BIH record, or the built-in synthetic PQRST when offline), resampled to
**200 Hz**, cut into **2 s chunks of 400 samples**, each sample in mV and inside
±20 mV.

So: **4 scalar sensors + 1 ECG stream**, which land as rows in
`sensor_readings` and `ecg_chunks` respectively.

Which folders are involved is spelled out in `docs/phase-3-notes.md` §1; the
short version is that everything the simulator *is* lives in `simulator/`, and
the two smoke helpers it needs live in `backend/django/scripts/`.

## 1. Start the services

Two terminals, from the repository root. Django is only needed to mint a token
and a session; the simulator itself only talks to FastAPI on **8001**.

**Terminal A — Django (port 8000):**

```powershell
cd backend\django
..\.venv\Scripts\Activate.ps1
python manage.py migrate
python manage.py seed_demo
python manage.py runserver 8000
```

**Terminal B — FastAPI (port 8001):**

```powershell
cd backend\fastapi
.\.venv\Scripts\Activate.ps1
# PostgreSQL: uncomment the two lines below. Skip them to use the SQLite default
# from backend\fastapi\.env (fastapi-dev.sqlite3), which is what the row counts
# in step 7 read.
# $env:DATABASE_URL = "postgresql+psycopg://ecg:ecg@127.0.0.1:5432/ecg"
# $env:TELEMETRY_SCHEMA = "telemetry"
python -m alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Check both:

```powershell
curl.exe -s http://127.0.0.1:8000/api/health/     # {"status":"ok","service":"django"}
curl.exe -s http://127.0.0.1:8001/health          # {"status":"ok","service":"fastapi"}
```

`curl.exe` is used explicitly: in PowerShell, `curl` is an alias for
`Invoke-WebRequest`, which does not understand `-H`/`-d`.

## 2. Create the simulator's virtualenv (once)

```powershell
cd <repository root>
python -m venv simulator\.venv
simulator\.venv\Scripts\python.exe -m pip install -r simulator\requirements-dev.txt
simulator\.venv\Scripts\python.exe -m simulator --help
```

`requirements-dev.txt` includes the backend's requirements so that the
integration test can drive the real FastAPI app in-process. For a
simulator-only install, `simulator\requirements.txt` is enough (httpx + wfdb) and
the integration test skips itself with that reason.

## 3. Mint a **fresh** session and register it

Phase 3 uses `mint_new_run.py` rather than Phase 2's `mint_run.py`: counting rows
per session needs a session that nothing else has written to, and Django allows
one active session per device, so the new script closes the open one first.

```powershell
cd <repository root>
$env:MINT_OUT = "$PWD\.smoke\mint.txt"
backend\.venv\Scripts\python.exe backend\django\scripts\mint_new_run.py
Get-Content .smoke\mint.txt
```

Expected (trimmed):

```
DEVICE_TOKEN=eyJhbGciOi…
SESSION_ID=0991011d-6931-4a2a-b978-c851fe043cf2
USER_TOKEN=eyJhbGciOi…
PATIENT_ID=14
DEVICE_ID=9692be3b-29d7-4e85-a147-c66146331e69
SESSION_CREATED_NEW=1
PREVIOUS_SESSION_CLOSED=1a2b3c4d-…
```

Load them into the current shell — every later step needs them:

```powershell
$v = @{}
Get-Content .smoke\mint.txt | ForEach-Object { if ($_ -match "^([A-Z_]+)=(.+)$") { $v[$Matches[1]] = $Matches[2] } }
$deviceToken = $v["DEVICE_TOKEN"]; $sessionId = $v["SESSION_ID"]; $userToken = $v["USER_TOKEN"]
$deviceId = $v["DEVICE_ID"]; $patientId = $v["PATIENT_ID"]
```

> With the full stack running, Django pushes a new session to FastAPI itself
> (`monitoring/telemetry.py`). Registering it by hand is only needed when FastAPI
> was started *after* the session, and it is safe to repeat — the endpoint is an
> upsert.

```powershell
curl.exe -s -X POST http://127.0.0.1:8001/internal/sessions `
  -H "Authorization: Bearer $userToken" -H "Content-Type: application/json" `
  -d "{`"session_id`":`"$sessionId`",`"patient_id`":$patientId,`"device_id`":`"$deviceId`",`"doctor_ids`":[],`"status`":`"active`"}"
```

```json
{"session_id":"0991011d-…","status":"active","known":true}
```

## 4. Run the simulator for 30 seconds with ECG on ✅

This is the headline command. With `.smoke\mint.txt` present, the token and the
session are read from it, so no arguments are needed for those.

```powershell
cd <repository root>
simulator\.venv\Scripts\python.exe -m simulator --duration 30 --interval 1 --ecg
```

`python simulator\run.py …` is the same entry point if you prefer that spelling.
Expected log lines, one per request (trimmed):

```
INFO  simulator: configuration: base_url=http://127.0.0.1:8001 session_id=0991011d-… duration=30s interval=1s heartbeat=10s ecg=on chunk=2s source=auto
INFO  simulator: credentials: session_id from argument, device_token from argument, user_token from mint.txt
INFO  simulator: preflight: GET /health and the device heartbeat
INFO  simulator.transport: /sensor/connect              -> 200    18.0 ms {'device_id': '9692be3b-…', 'owner_id': 13, 'online': True, …}
INFO  simulator.ecg.source: ECG source: MIT-BIH record 100 (360 Hz, channel 0) (local cache)
INFO  simulator: resampling 360 Hz -> 200 Hz
INFO  simulator.transport: POST /sensor/connect         -> 200    12.4 ms {… 'online': True, 'firmware_version': 'sim-3.0.0'}
INFO  simulator.transport: POST /sensor/ecg #0          -> 200    15.1 ms {'stored': True, 'duplicate': False, 'chunk_index': 0, 'sample_count': 400, 'sample_rate_hz': 200, …}
INFO  simulator.transport: POST /sensor/data temperature -> 200    14.1 ms {'stored': True, … 'value': 36.8, 'unit': 'celsius'}
INFO  simulator.transport: POST /sensor/data spo2       -> 200    16.0 ms {'stored': True, … 'value': 97.1, 'unit': 'percent'}
INFO  simulator.transport: POST /sensor/data pulse      -> 200    14.4 ms {'stored': True, … 'value': 72.0, 'unit': 'bpm'}
INFO  simulator.transport: POST /sensor/data motion     -> 200    14.8 ms {'stored': True, … 'value': 5.09, 'unit': 'a.u.'}
```

The summary it prints at the end:

```
========================================================================
SIMULATOR SUMMARY (screening aid, not a medical diagnosis)
========================================================================
session            : 0991011d-6931-4a2a-b978-c851fe043cf2
wall clock         : 30.0s of 30s requested

sensor           sent  stored    dup  failed  last value
temperature        29      29      0       0  36.8
spo2               29      29      0       0  98.2
pulse              29      29      0       0  72.0
motion             29      29      0       0  13.01
TOTAL             116     116      0       0

heartbeats         : sent 3, failed 0
ECG chunks         : produced 17, sent 17, stored 17 (of which 0 re-sends), duplicates 0, dropped 0, failed 0
ECG samples        : 6600 stored, range -0.652 .. 1.05 mV, clamped 0
HTTP               : 137 requests, 0 retries, 0 failed, statuses {'200': 137}
ECG source         : MIT-BIH 100 at 360 Hz (local cache)
========================================================================
```

Read that as: **4 sensor types filled, 116 readings, 17 ECG chunk rows.** `29`
per sensor is expected rather than 30 — the loop targets a 1 s interval and the
run ends between ticks (see `docs/phase-3-notes.md` §8).

### 4.1 No ECG (heartbeat + scalars only)

```powershell
simulator\.venv\Scripts\python.exe -m simulator --duration 10 --interval 1
```

Half the reason to have this mode is that it needs neither `wfdb` nor a network.

## 5. The edge cases, one flag at a time ✅

All four together, on its own fresh session so the counts are unambiguous. Mint
again first (`mint_new_run.py` mints a new session each time) and re-load
`$deviceToken`/`$sessionId` as in step 3 — or just reuse the current session and
read the *duplicate* counters instead of the row counts.

```powershell
simulator\.venv\Scripts\python.exe -m simulator `
  --duration 12 --interval 0.5 `
  --ecg --noise `
  --drop-chunks 0.3 --resend-chunks 1.0 `
  --offline-after 12 `
  --seed 20261006 `
  --output-json .smoke\edge-summary.json
```

Expected shape (the exact counts depend on `--seed`):

```
ECG chunks         : produced 17, sent 26, stored 13 (of which 13 re-sends), duplicates 13, dropped 4, failed 0
dropped indexes    : [0, 10, 13, 16]
re-sent indexes    : [1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 14, 15]
offline            : stopped after 12s (device went away; last_seen in the DB stops advancing)
```

What each flag proves:

* **`--drop-chunks 0.3`** — 4 chunks were computed and never sent (`0, 10, 13,
  16`). Note what did **not** happen: no error, and the later chunks kept their
  own indexes. A `chunk_index` gap is what a real radio dropout looks like, and
  the dashboard has to cope with it.
* **`--resend-chunks 1.0`** — every chunk was sent twice: `13` accepted,
  `13` answered `duplicate: true`. `chunks_unique_stored` in the JSON is
  `stored − re-sends`, which is the number of rows that exist.
* **`--noise`** — compare `ECG samples … clamped 0` with a run without it; a
  non-zero clamp count would mean a spike had to be clipped to stay inside
  ±20 mV.
* **`--offline-after 12`** — `POST /sensor/connect` stops, so `last_seen` stops
  advancing. Watch it from the API's side:

```powershell
curl.exe -s "http://127.0.0.1:8001/sensor/status?device_id=$deviceId" -H "Authorization: Bearer $userToken"
```

Run it once during the run and once 30 s later: `online` flips to `false` after
the API's 120 s threshold (`HEARTBEAT_THRESHOLD_SECONDS`), not after 12 s — the
simulator has no way to declare itself offline, and that is the point.

`--offline-after` as a hard failure — no retries, no error:

```powershell
simulator\.venv\Scripts\python.exe -m simulator --duration 30 --interval 1 --ecg --offline-after 0
```

## 6. Watch the idempotency at the API level ✅

The re-send proof, by hand, with the same chunk twice:

```powershell
$now = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$chunk = "{`"session_id`":`"$sessionId`",`"chunk_index`":900,`"start_time`":`"$now`",`"sample_rate_hz`":200,`"samples`":[0.1,0.2,0.3,0.4]}"
curl.exe -s -X POST http://127.0.0.1:8001/sensor/ecg -H "Authorization: Bearer $deviceToken" -H "Content-Type: application/json" -d $chunk
curl.exe -s -X POST http://127.0.0.1:8001/sensor/ecg -H "Authorization: Bearer $deviceToken" -H "Content-Type: application/json" -d $chunk
```

`stored:true` then `stored:false, duplicate:true` with the **same** `chunk_id`.
Read the row back:

```powershell
curl.exe -s http://127.0.0.1:8001/sessions/$sessionId/ecg/900 -H "Authorization: Bearer $userToken"
```

`ecg_chunks` has `UNIQUE (session_id, chunk_index)` — that constraint, not the
pre-check, is what makes the retry safe.

## 7. Count the rows in the database ✅

The simulator's word is not the proof; these are the rows.

**SQLite (the local default)** — the simulator's venv already has everything
needed, and the query runs read-only so it works while the server holds the file:

```powershell
simulator\.venv\Scripts\python.exe -c "import sqlite3,sys; s=sys.argv[1].replace('-','').lower(); c=sqlite3.connect('file:backend/fastapi/fastapi-dev.sqlite3?mode=ro',uri=True); print('readings:', dict(c.execute('select sensor_type, count(*) from sensor_readings where session_id=? group by sensor_type',(s,)).fetchall())); print('ecg chunks:', c.execute('select count(*) from ecg_chunks where session_id=?',(s,)).fetchone()[0]); print('ecg samples:', c.execute('select coalesce(sum(sample_count),0) from ecg_chunks where session_id=?',(s,)).fetchone()[0])" $sessionId
```

Expected — a real run of the command in step 4:

```
readings: {'temperature': 58, 'spo2': 58, 'pulse': 58, 'motion': 58}
ecg chunks: 17
ecg samples: 6600
```

**PostgreSQL:**

```powershell
docker exec ecg-postgres psql -U ecg -d ecg -c "select sensor_type, count(*) from telemetry.sensor_readings where session_id = '$sessionId' group by sensor_type order by sensor_type;"
docker exec ecg-postgres psql -U ecg -d ecg -c "select count(*) as chunks, sum(sample_count) as samples from telemetry.ecg_chunks where session_id = '$sessionId';"
```

Two things to check in the numbers:

* **`ecg chunks` equals the chunk rows, not the samples.** 6600 samples live in
  17 rows. One row per sample would be 6600 rows, which is the bug this proves
  against.
* **`ecg chunks` is not the number of POSTs.** With `--resend-chunks` the API saw
  more requests than there are rows, because the second POST of an index stored
  nothing.

## 8. Offline behaviour, on purpose

The synthetic ECG makes the whole thing runnable with no network and no `wfdb`:

```powershell
simulator\.venv\Scripts\python.exe -m simulator --duration 10 --ecg --ecg-source synthetic
```

```
INFO  simulator.ecg.source: ECG source: synthetic sinus rhythm at 200 Hz (requested)
```

To prove the fallback rather than ask for it, point the cache somewhere empty and
refuse to download:

```powershell
simulator\.venv\Scripts\python.exe -m simulator --duration 10 --ecg --no-ecg-download
```

With `--ecg-source auto` it falls back with a warning; with `--ecg-source mitbih`
it **fails loudly** instead, which is the setting to use when you want to know
that MIT-BIH really loaded:

```powershell
simulator\.venv\Scripts\python.exe -m simulator --duration 10 --ecg --ecg-source mitbih --no-ecg-download
# -> The API refused the run: ... could not be loaded ...  (exit code 1)
```

The first real fetch caches the record in `simulator\.ecg-data\`; record 100 is
~1.9 MB and took ~95 s on this connection, after which every run is offline and
instant.

## 9. One command instead of steps 3–7

```powershell
cd <repository root>
powershell -ExecutionPolicy Bypass -File scripts\smoke-phase3.ps1
# shorter, or without the edge-case phase:
powershell -ExecutionPolicy Bypass -File scripts\smoke-phase3.ps1 -Duration 10 -SkipEdgeCases
```

It mints a fresh session, registers it, runs the edge-case phase, runs the real
run, counts the rows, asserts each of the numbers above and exits non-zero if any
of them is wrong. The transcript is also written to
`.smoke\smoke-phase3.txt`.

## 10. Test suites

```powershell
cd simulator ;      ..\.venv\Scripts\python -m pytest -q     # 95 tests
cd backend\fastapi ; python -m pytest -q                      # Phase 2, untouched
cd backend\django ;  python -m pytest -q                      # Phase 1, untouched
```

The simulator suite covers the same ground as this document *plus* what is
awkward to type by hand: every generated value inside the Phase 2 ranges across
many seeds, the resample count at six source/target rate pairs, a hand-computed
ramp that pins the interpolation, the chunker's short final chunk and its
1–5000 sample limit, and the range file being compared against the API's own
(`test_ranges_match_api.py`). `test_api_integration.py` drives the real FastAPI
app in-process through `TestClient` and asserts the row counts — including that a
re-sent chunk stores exactly one row.

## 11. Troubleshooting

| Symptom | Cause, and the fix |
| --- | --- |
| `--device-token is required` | no argument, no `ECG_SIM_DEVICE_TOKEN`, and no `DEVICE_TOKEN` in `.smoke\mint.txt` — mint first (step 3) or pass it |
| `The API refused the run: POST /sensor/connect -> 404` | the session is not in `known_sessions`: register it (step 3) |
| `-> 403 This session belongs to a different device` | the token is for another device; the mint script prints a matching pair |
| `-> 409 Session is 'completed'` | the session was closed — `mint_new_run.py` mints a new one |
| `-> 401 Device token required.` | a **user** token was passed to a device endpoint |
| `MIT-BIH ... falling back` | no network, no `wfdb`, or no cached record; use `--ecg-source synthetic` deliberately, or pre-fetch the record |
| the first ECG run takes ~90 s | that is the one-time PhysioNet fetch into `simulator\.ecg-data\` |
| `could not create named pipe` from `wfdb` | `dl_database`'s thread pool is blocked in this environment; the loader streams over HTTP instead, so this is only a fallback failing |
| every request is retried and then fails | the service is down; `curl.exe http://127.0.0.1:8001/health` |
| `python -m simulator` says "No module named simulator" | run it from the repository root, or use `python simulator\run.py` |
| `pytest` cannot import `app` | `simulator\requirements-dev.txt` was not installed, or pytest was run outside `simulator/`; that test skips itself with this reason |
| row counts look double | the run reused a session that already had data; mint a fresh one |
