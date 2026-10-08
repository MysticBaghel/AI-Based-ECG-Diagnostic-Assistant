# Phase 2 smoke test — copy/paste proof that telemetry works

Every command below is ready to paste. It proves, in order:

1. a real device token issued by Django stores a temperature reading;
2. a bad token is rejected;
3. an out-of-range value is rejected;
4. the same ECG chunk twice stores one row;
5. a WebSocket client sees a reading live.

The contract these calls implement is `docs/api-contract.md`. The same checks
exist as a pytest suite (`backend/fastapi/tests/`) and as a script
(`scripts/smoke-phase2.ps1`).

> This service is a **screening aid, not a medical diagnosis**. Nothing it
> returns is a clinical finding.

---

## 0. Start the services

Three terminals, from the repository root.

**Terminal A — PostgreSQL (optional; SQLite works for a smoke test):**

```powershell
docker compose up -d postgres
```

**Terminal B — Django (port 8000):**

```powershell
cd backend\django
.\.venv\Scripts\Activate.ps1        # or: ..\.venv\Scripts\Activate.ps1
python manage.py migrate
python manage.py seed_demo
python manage.py runserver 8000
```

**Terminal C — FastAPI (port 8001):**

```powershell
cd backend\fastapi
.\.venv\Scripts\Activate.ps1
# PostgreSQL (recommended). Skip these two lines to use the SQLite default from
# backend\fastapi\.env.
$env:DATABASE_URL = "postgresql+psycopg://ecg:ecg@127.0.0.1:5432/ecg"
$env:TELEMETRY_SCHEMA = "telemetry"
python -m alembic upgrade head      # creates the telemetry schema + tables
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Check both:

```powershell
curl.exe -s http://127.0.0.1:8000/api/health/     # {"status": "ok", "service": "django"}
curl.exe -s http://127.0.0.1:8001/health          # {"status": "ok", "service": "fastapi"}
```

`curl.exe` is used explicitly: in PowerShell, `curl` is an alias for
`Invoke-WebRequest`, which does not understand `-H`/`-d`.

## 1. Get a real device token from Django

Two ways. Both create `smoke_doctor`, `smoke_patient`, a device and an active
session, and print `DEVICE_TOKEN`, `SESSION_ID`, `USER_TOKEN`, `PATIENT_ID` and
`DEVICE_ID`.

**Scripted (writes the values into `.smoke\mint.txt`):**

```powershell
cd backend\django
$env:MINT_OUT = "..\..\.smoke\mint.txt"
python scripts\mint_run.py
Get-Content ..\..\.smoke\mint.txt
```

**By hand:** `python manage.py shell`, then paste the contents of
`scripts/mint.py`.

Load them into the current shell (all later commands need them):

```powershell
$v = @{}
Get-Content .smoke\mint.txt | ForEach-Object { if ($_ -match "^([A-Z_]+)=(.+)$") { $v[$Matches[1]] = $Matches[2] } }
$deviceToken = $v["DEVICE_TOKEN"]; $sessionId = $v["SESSION_ID"]; $userToken = $v["USER_TOKEN"]
$deviceId = $v["DEVICE_ID"]; $patientId = $v["PATIENT_ID"]
```

> With the full stack running, session creation pushes itself to FastAPI
> (`monitoring/telemetry.py`), so step 2 is only needed when the service was
> started *after* the session. It is safe to repeat: the endpoint is an upsert.

## 2. Register the session with FastAPI (idempotent)

```powershell
curl.exe -s -X POST http://127.0.0.1:8001/internal/sessions `
  -H "Authorization: Bearer $userToken" -H "Content-Type: application/json" `
  -d "{`"session_id`":`"$sessionId`",`"patient_id`":$patientId,`"device_id`":`"$deviceId`",`"doctor_ids`":[],`"status`":`"active`"}"
```

Expected `200`:

```json
{"session_id":"e366de96-…","status":"active","known":true}
```

## 3. A valid device token stores a temperature reading ✅

```powershell
$now = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
curl.exe -s -X POST http://127.0.0.1:8001/sensor/data `
  -H "Authorization: Bearer $deviceToken" -H "Content-Type: application/json" `
  -d "{`"session_id`":`"$sessionId`",`"sensor_type`":`"temperature`",`"value`":36.8,`"unit`":`"celsius`",`"recorded_at`":`"$now`"}"
```

Expected `200` — this is the headline requirement:

```json
{"stored":true,"duplicate":false,"reading_id":"ba0a2941-…","session_id":"e366de96-…",
 "sensor_type":"temperature","value":36.8,"unit":"celsius","recorded_at":"2026-10-05T07:30:34Z"}
```

The heartbeat, in the same style:

```powershell
curl.exe -s -X POST http://127.0.0.1:8001/sensor/connect `
  -H "Authorization: Bearer $deviceToken" -H "Content-Type: application/json" `
  -d '{\"firmware_version\":\"smoke-1.0\"}'
```

```json
{"device_id":"9692be3b-…","owner_id":13,"last_seen":"2026-10-05T07:30:34.770439Z",
 "online":true,"firmware_version":"smoke-1.0"}
```

## 4. A bad token is rejected ✅

```powershell
curl.exe -s -o - -w "`nHTTP %{http_code}`n" -X POST http://127.0.0.1:8001/sensor/data `
  -H "Authorization: Bearer not.a.real.token" -H "Content-Type: application/json" `
  -d "{`"session_id`":`"$sessionId`",`"sensor_type`":`"temperature`",`"value`":36.8,`"unit`":`"celsius`"}"
```

Expected `401`:

```json
{"detail":"Token is invalid.","code":"unauthorized"}
```

A **user** token on a device endpoint is the same status with a different
message, and a **device** token on a user endpoint is rejected the other way:

```powershell
curl.exe -s http://127.0.0.1:8001/sensor/status -H "Authorization: Bearer $userToken"     # 200
curl.exe -s http://127.0.0.1:8001/sensor/status -H "Authorization: Bearer $deviceToken"   # 401 User access token required.
```

## 5. An out-of-range value is rejected ✅

```powershell
curl.exe -s -o - -w "`nHTTP %{http_code}`n" -X POST http://127.0.0.1:8001/sensor/data `
  -H "Authorization: Bearer $deviceToken" -H "Content-Type: application/json" `
  -d "{`"session_id`":`"$sessionId`",`"sensor_type`":`"temperature`",`"value`":99.0,`"unit`":`"celsius`"}"
```

Expected `422`:

```json
{"detail":"Request body failed validation.","code":"validation_error",
 "errors":[{"field":"body","message":"Value error, temperature must be between 25.0 and 45.0, got 99.0"}]}
```

Two more rejections worth seeing, both cheap:

```powershell
# The same value in the future by hours -> 422 (timestamp guard)
curl.exe -s -X POST http://127.0.0.1:8001/sensor/data -H "Authorization: Bearer $deviceToken" -H "Content-Type: application/json" `
  -d "{`"session_id`":`"$sessionId`",`"sensor_type`":`"temperature`",`"value`":36.8,`"unit`":`"celsius`",`"recorded_at`":`"2099-01-01T00:00:00Z`"}"
# A session the service has never heard of -> 404 unknown_session
curl.exe -s -X POST http://127.0.0.1:8001/sensor/data -H "Authorization: Bearer $deviceToken" -H "Content-Type: application/json" `
  -d '{"session_id":"99999999-9999-4999-8999-999999999999","sensor_type":"temperature","value":36.8,"unit":"celsius"}'
```

## 6. The same ECG chunk twice stores one row ✅

```powershell
$chunk = "{`"session_id`":`"$sessionId`",`"chunk_index`":0,`"start_time`":`"$now`",`"sample_rate_hz`":250,`"samples`":[0.1,0.2,0.3,0.4]}"
curl.exe -s -X POST http://127.0.0.1:8001/sensor/ecg -H "Authorization: Bearer $deviceToken" -H "Content-Type: application/json" -d $chunk
curl.exe -s -X POST http://127.0.0.1:8001/sensor/ecg -H "Authorization: Bearer $deviceToken" -H "Content-Type: application/json" -d $chunk
```

First response `stored:true`, second `stored:false, duplicate:true` with the
**same** `chunk_id`. Confirm one row:

```powershell
curl.exe -s http://127.0.0.1:8001/sessions/$sessionId/ecg/0 -H "Authorization: Bearer $userToken"
```

With PostgreSQL, the row count is one query away:

```powershell
docker exec ecg-postgres psql -U ecg -d ecg -c "select count(*) from telemetry.ecg_chunks where session_id = '$sessionId';"
```

(`ecg_chunks` has `UNIQUE (session_id, chunk_index)` — that is what makes the
retry safe, not the code path that checks first.)

## 7. A WebSocket client sees a reading live ✅

`scripts/ws_watch.py` connects, prints the snapshot frame, uploads one
temperature reading a second later, and prints the live frame it receives:

```powershell
cd backend\fastapi
.\.venv\Scripts\Activate.ps1
python scripts\ws_watch.py $sessionId $userToken $deviceToken 15
```

Expected output (trimmed):

```
connected; waiting for frames
frame <- {"event":"snapshot","session_id":"e366de96-…","readings":[…]}
frame <- {"event":"reading","session_id":"e366de96-…","sensor_type":"temperature","value":37.1,"unit":"celsius","recorded_at":"2026-10-05T07:31:02.960154+00:00"}
SUCCESS: a live reading arrived over the socket
upload -> 200 {"stored":true,…}
```

A browser can do the same in one line from the console:

```js
const ws = new WebSocket(`ws://127.0.0.1:8001/ws/sensor?session_id=${sessionId}&token=${userToken}`);
ws.onmessage = (event) => console.log(event.data);
```

Failure modes, if you want to see them: an invalid token closes with `4401`, a
user who is not on the session closes with `4403`, an unknown session with
`4404`, and each is preceded by
`{"event":"error","error":{"code":"…","message":"…"}}`.

## 8. One command instead of steps 1–7

```powershell
cd <repository root>
powershell -ExecutionPolicy Bypass -File scripts\smoke-phase2.ps1
# or, skipping the socket:
powershell -ExecutionPolicy Bypass -File scripts\smoke-phase2.ps1 -WsSeconds 0
```

## 9. Test suites

```powershell
cd backend\django ;  python -m pytest -q --ignore=pytest-cache-files-88wctrkw
cd backend\fastapi ; python -m pytest -q
```

The FastAPI suite covers the same ground as this document plus the token
matrix, session states, ECG validation ranges and the hub's back-pressure rule.
