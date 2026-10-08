# API contract — FastAPI telemetry service (Phase 2)

This is the contract the ESP32 firmware, the simulator, the React dashboard and
the WebSocket viewer all code against. It matches `backend/fastapi/` exactly; if
the two ever disagree, the code is right and this document is a bug.

The service is a **screening aid, not a medical diagnosis**. Nothing it returns
is a clinical finding.

Contents:

1. [Scope and services](#1-scope-and-services)
2. [Conventions](#2-conventions)
3. [Auth](#3-auth)
4. [Data model](#4-data-model)
5. [Endpoints](#5-endpoints)
6. [WebSocket /ws/sensor](#6-websocket-wssensor)
7. [Validation rules](#7-validation-rules)
8. [Error format](#8-error-format)
9. [Idempotency](#9-idempotency)
10. [Known-session registry](#10-known-session-registry)
11. [Revocation](#11-revocation)
12. [Known limits](#12-known-limits)

---

## 1. Scope and services

| Service | Role | Owns |
| --- | --- | --- |
| Django (`backend/django`) | identity + business data | users, roles, patients, doctors, devices, sessions, `JWT_SIGNING_KEY` |
| FastAPI (`backend/fastapi`) | telemetry + compute | sensor readings, ECG chunks, device connections, session registry, revocation list |

FastAPI **never calls Django** on a request path. It holds the same
`JWT_SIGNING_KEY` and verifies tokens locally, so a Django outage does not stop
a device uploading data. The only Django → FastAPI traffic is the session
registry push (section 10), which is best-effort and off the device path.

Ports: Django `8000`, FastAPI `8001`, Postgres `5432`.

## 2. Conventions

* Base path for REST: `/`. The health probe is `GET /health`.
* All request and response bodies are JSON, `Content-Type: application/json`.
* Timestamps are RFC 3339 / ISO 8601 with an offset. A timestamp with no offset
  is read as UTC, not as local time.
* IDs are UUID strings (`session_id`, `device_id`) and plain integers (`user_id`,
  `owner_id`) — the same values Django puts in its JWTs.
* The maximum request body is **1 MiB** (`MAX_PAYLOAD_BYTES`). A larger body is
  rejected by middleware before it is parsed, with `413`.
* Unknown fields are ignored by Pydantic (`extra="ignore"`) so firmware can send
  a superset without breaking. A field whose *value* is wrong is still a `422`.

## 3. Auth

Two token audiences, two dependencies, and each rejects the other.

| Header | Token | Dependency | Used by |
| --- | --- | --- | --- |
| `Authorization: Bearer <token>` | Django **device** token | `require_device` | `POST /sensor/connect`, `POST /sensor/data`, `POST /sensor/ecg` |
| `Authorization: Bearer <token>` | Django **user access** token | `require_user` | `GET /sensor/status`, `GET /sessions/<id>/readings`, `GET /sessions/<id>/ecg/<chunk_index>`, `POST /internal/sessions` (admin only) |
| `?token=<token>` (query string) | either, depending on the socket's role | `require_viewer_token` | `WS /ws/sensor` |

Verification is local and identical for both:

* `jwt.decode(token, JWT_SIGNING_KEY, algorithms=["HS256"])` — the algorithm list
  is **pinned**, so a token that claims `alg: none` or `alg: RS256` is rejected
  before the signature is looked at.
* Signature and `exp` are both verified. A missing `exp` is a rejection.
* No default signing key exists. If `JWT_SIGNING_KEY` is unset the process does
  not start (`ImproperlyConfigured` at settings load).

Claim requirements:

| Token | Required claims | Rejected when |
| --- | --- | --- |
| Device | `type == "device"`, `device_id` (UUID), `owner_id` (int) | any missing/wrong, or `type == "access"` |
| User access | `token_type == "access"`, `user_id` (int), `role` in `{patient, doctor, admin}` | any missing/wrong, or `token_type == "refresh"`, or a device token |

A user token on a device endpoint returns **401**, and a device token on a user
endpoint returns **401**; the messages differ (`Device token required` vs
`User access token required`) so a misconfigured client is easy to spot.

`Authorization` must be `Bearer <token>`; any other scheme is `401` with
`WWW-Authenticate: Bearer`.

### Why the WebSocket authenticates with a query string

`WS /ws/sensor?session_id=<uuid>&token=<jwt>`.

Browsers cannot set headers on a WebSocket handshake, so an `Authorization`
header is not available to the React dashboard — which is the main viewer. The
alternatives are (a) a first-message auth handshake, which every client has to
implement and which leaves an unauthenticated socket open until the message
arrives, or (b) a cookie, which does not exist because JWTs are not stored in
cookies. The query string is the only option the browser supports natively, so
it is the documented one. The token is validated **before** the socket is
accepted; on failure the socket is closed with `4401` (or `4403` for a viewer
that is not allowed to see that session) and a JSON `{"error": {...}}` frame.

The cost is that the token lands in server access logs (URLs are logged). That
is accepted here and mitigated by short access-token lifetimes (60 minutes) —
and it is written down rather than hidden. A one-time socket ticket endpoint is
the Phase 7 hardening fix if logs become sensitive.

## 4. Data model

PostgreSQL, one schema: **`telemetry`**. (`TELEMETRY_SCHEMA=""` switches to no
schema so the test suite can run on SQLite; production always uses `telemetry`.)

No foreign keys point at Django tables. `session_id` and `device_id` are plain
`UUID` columns and `owner_id`/`patient_id`/`doctor_ids` are plain integers,
because the two services share an identifier space, not a database.

| Table | Columns | Notes |
| --- | --- | --- |
| `known_sessions` | `session_id` UUID **PK**, `patient_id` int, `device_id` UUID, `doctor_ids` int[], `status` text, `registered_at`, `updated_at` | mirror of Django sessions, written by section 10 |
| `device_connections` | `device_id` UUID **PK**, `owner_id` int, `last_seen` timestamptz, `firmware_version` text, `ip_address` text, `created_at` | one row per device, updated by `POST /sensor/connect` |
| `sensor_readings` | `id` UUID **PK**, `session_id` UUID → `known_sessions`, `device_id` UUID, `sensor_type` text, `value` double, `unit` text, `recorded_at` timestamptz, `received_at` timestamptz | scalar readings; **unique** `(session_id, sensor_type, recorded_at)` |
| `ecg_chunks` | `id` UUID **PK**, `session_id` UUID → `known_sessions`, `device_id` UUID, `start_time` timestamptz, `sample_rate_hz` int, `samples` JSON, `sample_count` int, `chunk_index` int, `received_at` | **one row per chunk**; **unique** `(session_id, chunk_index)` |
| `revoked_devices` | `device_id` UUID **PK**, `reason` text, `revoked_at` timestamptz | section 11 |

`device_id` on `sensor_readings`/`ecg_chunks` is copied from the verified token,
never from the body: a device cannot write data attributed to another device.

Alembic version table: `telemetry.alembic_version`.

## 5. Endpoints

### `GET /` and `GET /health`

Public. `GET /health` is the liveness probe; `GET /` names the service and
carries the disclaimer.

```json
{"status": "ok", "service": "fastapi"}
```

```json
{"service": "ECG telemetry API", "version": "2.0.0", "docs": "/docs",
 "notice": "Screening aid, not a medical diagnosis."}
```

### `POST /sensor/connect` — device token

Registers or updates the device connection and its `last_seen`.

Request:

```json
{"firmware_version": "1.2.0", "ip_address": "10.0.0.7"}
```

Both fields optional. `owner_id` comes from the token.

Response `200`:

```json
{"device_id": "3f1c…", "owner_id": 7, "last_seen": "2026-10-05T12:00:00Z",
 "online": true, "firmware_version": "1.2.0"}
```

### `GET /sensor/status` — user token

Heartbeat. One row per device the caller may see: a patient sees the devices on
their own sessions, a doctor the devices on sessions of their assigned patients,
an admin all of them.

Query parameters: `device_id` (optional UUID — narrows to one device).

Response `200`:

```json
{"threshold_seconds": 120,
 "devices": [{"device_id": "3f1c…", "owner_id": 7,
              "last_seen": "2026-10-05T12:00:00Z", "seconds_since_seen": 12.4,
              "online": true, "revoked": false}]}
```

`online` is `seconds_since_seen <= threshold_seconds`; a device that has never
connected is `online: false` with `last_seen: null`. The threshold comes from
`HEARTBEAT_THRESHOLD_SECONDS` (default 120).

### `POST /sensor/data` — device token

One scalar reading.

Request:

```json
{"session_id": "9b2e…", "sensor_type": "temperature", "value": 36.8,
 "unit": "celsius", "recorded_at": "2026-10-05T12:00:00Z"}
```

`recorded_at` is optional and defaults to the server clock; prefer sending it,
because it is part of the idempotency key. Accepted `sensor_type`:
`temperature`, `spo2`, `pulse`, `motion`.

Response `200`:

```json
{"stored": true, "duplicate": false, "reading_id": "5c0a…",
 "session_id": "9b2e…", "sensor_type": "temperature",
 "value": 36.8, "unit": "celsius", "recorded_at": "2026-10-05T12:00:00Z"}
```

A byte-identical retry returns `stored: false, duplicate: true` and the id of
the row that already exists (section 9).

### `POST /sensor/ecg` — device token

One chunk of samples. **One row per chunk, never one row per sample.**

Request:

```json
{"session_id": "9b2e…", "chunk_index": 0,
 "start_time": "2026-10-05T12:00:00Z", "sample_rate_hz": 250,
 "samples": [0.12, -0.03, 0.44, "…"]}
```

Response `200`:

```json
{"stored": true, "duplicate": false, "chunk_id": "7d1f…",
 "session_id": "9b2e…", "chunk_index": 0, "sample_count": 250,
 "sample_rate_hz": 250, "start_time": "2026-10-05T12:00:00Z",
 "duration_seconds": 1.0}
```

### `GET /sessions/<session_id>/readings` — user token

Latest scalar readings, newest first, for a viewer allowed to see the session.

Query parameters: `limit` (default 100, max 500), `sensor_type` (optional).

Response `200`:

```json
{"session_id": "9b2e…", "count": 2,
 "readings": [{"reading_id": "5c0a…", "sensor_type": "pulse", "value": 78,
               "unit": "bpm", "recorded_at": "2026-10-05T12:00:05Z"}]}
```

### `GET /sessions/<session_id>/ecg/<chunk_index>` — user token

One stored chunk, samples included. `404` when the chunk does not exist.

### `POST /internal/sessions` — user token, `role == "admin"`

Upserts the session registry entry (section 10). Called by Django.

Request:

```json
{"session_id": "9b2e…", "patient_id": 4, "device_id": "3f1c…",
 "doctor_ids": [2], "status": "active"}
```

Response `200`: `{"session_id": "9b2e…", "status": "active", "known": true}`.

### `POST /internal/devices/<device_id>/revoke` — user token, `role == "admin"`

Adds the device to the revocation list (section 11). Response `200`:
`{"device_id": "3f1c…", "revoked": true}`.

## 6. WebSocket `/ws/sensor`

```
ws://127.0.0.1:8001/ws/sensor?session_id=<uuid>&token=<jwt>
```

The token may be a **user access token** (patient on the session, assigned
doctor, or admin) or a **device token whose `device_id` is the session's
device** — so the simulator can watch what it is uploading.

Handshake:

1. `session_id` must parse as a UUID and the token must verify → otherwise the
   socket is accepted and immediately closed with `4401` plus a JSON error frame.
2. The session must be in the registry and the caller must be allowed to see it
   (section 10) → otherwise close `4403`.
3. The socket is accepted, then receives a `snapshot` frame (last 20 scalar
   readings) followed by live `reading` frames.

Server → client frames:

```json
{"event": "snapshot", "session_id": "9b2e…", "readings": [ … ]}
{"event": "reading", "session_id": "9b2e…", "sensor_type": "temperature",
 "value": 36.8, "unit": "celsius", "recorded_at": "2026-10-05T12:00:00Z"}
{"event": "ecg_chunk", "session_id": "9b2e…", "chunk_index": 0,
 "sample_count": 250, "sample_rate_hz": 250, "start_time": "…"}
{"event": "error", "error": {"code": "forbidden", "message": "…"}}
```

`ecg_chunk` carries metadata only — pushing thousands of samples down every
viewer socket is what the REST endpoint is for.

Client → server: nothing is required. `ping` as a text frame is answered with
`{"event":"pong"}`, so a client can measure the socket without leaving it idle;
any other frame is ignored. The close frame ends the subscription.

Close codes: `4401` unauthenticated/bad token, `4403` not allowed to view this
session (or a revoked device), `4404` unknown session.

## 7. Validation rules

All of these produce `422` (Pydantic) or `400` (business rule) — never a `500`.

| Field | Rule |
| --- | --- |
| `temperature` value | 25.0 – 45.0, unit must be `celsius` (or `°C`, normalised) |
| `spo2` value | 50.0 – 100.0, unit must be `percent` (or `%`) |
| `pulse` value | 20.0 – 250.0, unit must be `bpm` |
| `motion` value | 0.0 – 100.0, unit must be `a.u.` (or `au`, `g`) |
| `recorded_at` | at most `MAX_FUTURE_SECONDS` (default 300) in the future; not before 2000-01-01 |
| `chunk_index` | integer, 0 ≤ index ≤ 1 000 000 |
| `sample_rate_hz` | 100 – 2 000 |
| `samples` | 1 – 5 000 values, each finite and within ±20.0 mV |
| body size | ≤ 1 MiB, else `413` |
| `session_id` | must exist in `known_sessions`, else `404` |
| session `status` | must be `active` for `POST /sensor/data` and `POST /sensor/ecg`, else `409` |
| `device_id` (token) | must match `known_sessions.device_id` for that session, else `403` |
| device | must not be revoked, else `403` |

`session_id` that is not a UUID is a `422` before any database work happens.

## 8. Error format

Every error response is the same object:

```json
{"detail": "human readable message",
 "code": "machine_readable_code",
 "errors": [{"field": "value", "message": "…"}]}
```

| Status | `code` | When |
| --- | --- | --- |
| 400 | `bad_request` | business rule rejected an otherwise well-formed body |
| 401 | `unauthorized` | missing/malformed/expired/wrong-audience token, or missing `Authorization` header |
| 403 | `forbidden` | valid token, not allowed (viewer without access, device mismatch, revoked device) |
| 404 | `unknown_session` / `not_found` | no such session in the registry, or no such chunk |
| 409 | `session_not_active` | session exists but is completed/aborted |
| 413 | `payload_too_large` | body over `MAX_PAYLOAD_BYTES` |
| 422 | `validation_error` | Pydantic rejected the body; `errors` lists every field |
| 500 | `internal_error` | a bug. It is still JSON, never an HTML traceback. |

`errors[].field` is the dotted location, e.g. `value`, `samples.3`, `body.session_id`.

## 9. Idempotency

Devices retry. The rules:

* **Scalar readings** are idempotent on `(session_id, sensor_type, recorded_at)`.
  A retry with the same triple stores nothing new, returns `200` with
  `stored: false, duplicate: true`, and returns the existing `reading_id`.
  Consequence: two genuine readings of the same sensor at exactly the same
  timestamp across the whole session are treated as one. At 1 Hz per sensor that
  is not reachable; a device that samples faster than its timestamp resolution
  must send real timestamps.
* **ECG chunks** are idempotent on `(session_id, chunk_index)`. A retry stores
  one row total and returns `200` with `stored: false, duplicate: true` and the
  existing `chunk_id`. `chunk_index` is therefore the device's at-least-once
  delivery key: keep uploading the same index until you get a `200`.
* Neither rule re-broadcasts a duplicate: a WebSocket viewer sees each reading
  once.
* Uniqueness is enforced by a **database unique index**, not only by a
  pre-check, so two concurrent retries cannot both insert. The loser catches the
  integrity error, re-reads the winner's row and answers `200 duplicate`.

## 10. Known-session registry

FastAPI has no foreign key to Django, and it must be able to reject data for a
session it does not know **without calling Django**. The mechanism is a push:

* Django `POST`s to `/internal/sessions` after a session is created and after it
  is stopped (authenticated with a short-lived **admin** user token that Django
  mints for itself).
* FastAPI upserts `known_sessions` from it.
* Every write endpoint looks the session up in `known_sessions` first.

Tradeoff, stated plainly:

* **Good**: zero Django dependency on the hot path; a device upload costs one
  indexed lookup; a Django outage cannot stop ingestion.
* **Bad**: the registry is a cache and can be stale. If Django is up but the
  push failed (FastAPI was down at session start), a legitimate device gets
  `404 unknown_session` until the next successful push. Django logs the failure
  and does not fail the session creation, because a telemetry outage must not
  block clinical workflow.
* **Limit**: there is no automatic reconciliation yet. `POST /internal/sessions`
  is safe to replay — re-sending any session at any time repairs the cache — and
  a Phase 7 job that replays active sessions every minute is the intended fix.
* **Limit**: a session that is `completed` in Django stays in the registry with
  `status: completed`, so its late data is refused with `409` rather than `404`.
  That is deliberate: it distinguishes "never heard of it" from "too late".

## 11. Revocation

Device tokens are stateless: Django cannot invalidate a token it already
issued, and this service cannot either. What is implemented is a small
FastAPI-owned **deny list**:

* `revoked_devices` (one row per revoked device, PK `device_id`).
* Every device-token dependency checks it (one primary-key lookup).
* `POST /internal/devices/<device_id>/revoke` (admin token) adds a row.

Cost and limits:

* It is real revocation at the *next request*, not token expiry — that is the
  point of having it.
* It is per-device, not per-token: revoking blocks the device, and un-revoking
  (a `DELETE`, not implemented yet) would let any still-valid token work again.
* It does not stop the device from *connecting* being recorded, but it does
  refuse `POST /sensor/data` and `POST /sensor/ecg` and it refuses
  `POST /sensor/connect` too, so a revoked device learns immediately.
* `GET /sensor/status` reports `revoked: true` so the dashboard can show it.
* Django's "disable device" button does **not** write this row yet — Phase 7
  wires the two together. Until then, disable a device in Django *and* call the
  revoke endpoint.

## 12. Known limits

* No pagination on `/sessions/<id>/readings` beyond `limit`; a Phase 5 concern.
* No retention policy: `sensor_readings` and `ecg_chunks` grow forever.
* No per-token rate limiting; a runaway device can fill the tables.
* The viewer access check uses the registry snapshot, so a doctor who is
  assigned to a patient *after* the session started can see it only after the
  next registry push.
* `known_sessions.doctor_ids` reflects assignment at push time; reassignment
  mid-session needs another push.
* WebSocket fan-out is in-process only: two FastAPI replicas would each deliver
  live frames only to their own viewers. Redis pub/sub is the Phase 7 fix.
* The token in the WebSocket query string is logged (section 3).
* No `DELETE` for revocations.
* No ECG waveform reconstruction, filtering or ML inference here — that is
  Phase 5.
