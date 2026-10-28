# Phase 4 notes — the React dashboard

Phase 4 answers one question: **can a person run and understand a monitoring
session from a browser, with no physical sensor attached?** It is the first
phase where the two backends are used together by something other than a test:
Django supplies identity and the session lifecycle, FastAPI supplies the live
stream and the stored waveform, and the browser has to make those two services
feel like one application.

Scope: `frontend/` plus two small read endpoints added to the APIs it consumes.
The ingestion contract did not change; the simulator and a future ESP32 still
send exactly the payloads documented in `docs/api-contract.md`.

The system is a **screening aid, not a medical diagnosis**. The disclaimer is
not a footer decoration: it is in the login pitch, in a strip that stays visible
inside the application shell, in the live monitor's notes, in the recording
summary, and in the browser tab's description. A waveform on this screen is raw
telemetry, not a finding.

---

## 1. What is on screen

The dashboard is a single-page application with seven screens and one
not-found wall.

| Route | Who sees it | What it is for |
| --- | --- | --- |
| `/login` | anyone | Username/password sign-in against Django, with demo accounts and the disclaimer |
| `/` | all roles | Overview: active sessions, patient/device counts, heartbeat count, how the demo flows |
| `/patients` | all roles | Patient list (patient: own profile); doctors/admins can start a session |
| `/devices` | doctor, admin | Register a device, see heartbeats, copy the device id, rotate a token |
| `/sessions` | all roles | Session history with search, status filter and links to live/recording |
| `/sessions/:sessionId` | whoever may see the session | Stored waveform viewer, vital summary, session lifecycle |
| `/live` | all roles | Active-session picker |
| `/live/:sessionId` | whoever may see the session | Live ECG, four vitals, socket state, device heartbeat, stop button |
| `*` | signed-in users | Not found |

A patient never sees a "start session" or "stop session" control. A doctor sees
only their assigned patients, only their own devices, and only sessions of
assigned patients. An admin sees everything. That scoping is not implemented in
React: every list is scoped by the Django queryset, and the UI merely reflects
what the server returned. Hiding a nav link is a convenience; `RoleGate` and the
API's own permission classes are the boundary.

## 2. Layout — which folders are involved

```
frontend/
  index.html                    title, favicon, theme colour, description
  vite.config.ts                /api and /telemetry proxies, WebSocket upgrade
  package.json                  React 19, React Router 7, uPlot 1.6
  src/
    main.tsx                    StrictMode + BrowserRouter
    App.tsx                     route table, AuthProvider, role gates
    index.css                   the design system (tokens, shell, cards, chart, login)
    api/
      client.ts                 fetch wrapper, token storage, refresh, ApiError, WS URL
      types.ts                  Django + FastAPI response types
    auth/
      auth-context.ts           the context object and its value type
      AuthContext.tsx           AuthProvider: restore, login, logout, expiry
      useAuth.ts                the hook
      Guards.tsx                RequireAuth and RoleGate
    components/
      AppShell.tsx              sidebar, top bar, service health, disclaimer strip
      Icon.tsx                  inline SVG icon set
      EcgChart.tsx              uPlot wrapper (one series, resize-aware)
      Sparkline.tsx             tiny SVG trend line for the vital cards
      VitalCard.tsx             one scalar sensor: value, unit, trend, age
      SessionList.tsx           table and card presentations of sessions
      DeviceStatusBadge.tsx     online/offline/revoked/never-seen badges
      Modal.tsx                 portal dialog with Escape and scroll lock
      StartSessionDialog.tsx    patient + device -> POST /api/sessions/
      TokenDialog.tsx           "shown once" device token with copy
      ui.tsx                    Badge, Spinner, banners, EmptyState, panels, stats
    hooks/
      useResource.ts            load/poll/refresh one API resource
      useData.ts                typed resources (patients, devices, sessions, ...)
      useLiveMonitor.ts         WebSocket + REST chunk seeding + reconnect
      useNow.ts                 a clock for elapsed/relative labels
    lib/
      format.ts                 dates, durations, initials, sensor metadata
      ecg.ts                    chunks -> uPlot x/y series
    pages/
      LoginPage.tsx
      DashboardPage.tsx
      PatientsPage.tsx
      DevicesPage.tsx
      SessionsPage.tsx
      LivePage.tsx
      RecordingPage.tsx
      NotFoundPage.tsx
```

The two API additions this phase depends on are in:

| Path | Change |
| --- | --- |
| `backend/fastapi/app/routes/sensor.py` | `GET /sessions/<id>/ecg` returns the chunk index (metadata only) |
| `backend/fastapi/app/schemas.py` | `ECGChunkSummary`, `ECGChunkListResponse` |
| `backend/django/monitoring/serializers.py` | `patient_name`, `device_name` on a session |
| `backend/django/devices/serializers.py` | `owner_username` on a device, for the admin list |

No new database table is needed for the dashboard. The chunk index reads
`ecg_chunks`; the session labels come from foreign keys that were already
`select_related`; the owner label comes from the owner row Django already
joined.

## 3. The browser and the two backends

The browser is on one origin (`http://127.0.0.1:5173` in development). Vite
proxies two paths, so no CORS configuration is involved on the happy path:

```
/api/*        -> http://127.0.0.1:8000   Django    (identity, patients, devices, sessions)
/telemetry/*  -> http://127.0.0.1:8001   FastAPI   (readings, ECG chunks, status, WS)
```

`/telemetry` is stripped before the request reaches FastAPI, whose routes are
mounted at the root. The WebSocket upgrade is part of the same proxy entry
(`ws: true`), which is why the live socket has the same origin as the page.

The proxy targets can be overridden with `VITE_DJANGO_PROXY` and
`VITE_FASTAPI_PROXY` so a second dev stack can run beside a first one. In
production a reverse proxy must make the same two mappings; the frontend itself
never knows the backend ports.

### 3.1 Authentication, and the clock on a token

`POST /api/auth/login/` returns an access token (60 minutes) and a refresh token
(7 days). They are stored in `localStorage` under `ecg.access` and `ecg.refresh`;
`GET /api/auth/me/` supplies the role that drives navigation.

Every request goes through `api/client.ts`:

1. attach `Authorization: Bearer <access>`;
2. on a `401`, refresh **once** through `/api/auth/refresh/`, update the access
   token and replay the original request;
3. if the refresh also fails, clear the tokens, fire `auth:expired`, and let the
   provider send the user to `/login`;
4. concurrent `401`s share one refresh promise, so ten parallel page requests do
   not start ten refreshes.

Local storage is a deliberate trade-off. It survives a reload and is simple to
reason about, but any script that can run in the page can read it. A cookie-based
session with CSRF protection is the more defensive design; this phase keeps the
JWT flow that Phase 1 already issues, and records the cost rather than hiding it.

### 3.2 Why the WebSocket puts the token in the query string

Browsers cannot set headers on a WebSocket handshake. The alternative designs
are a first-message auth protocol (which leaves an unauthenticated socket open
until the message arrives) or a cookie (which does not exist here). The socket
therefore uses:

```
ws://127.0.0.1:8001/ws/sensor?session_id=<uuid>&token=<user access token>
```

FastAPI validates the token before accepting the socket. The cost is that the
token appears in access logs; short access-token lifetimes limit the exposure,
and a one-time socket ticket is the Phase 7 hardening fix already named in
`docs/api-contract.md`.

## 4. Screen by screen

### 4.1 Login

Two panels: what the system is on the left, a form and demo accounts on the
right. The demo accounts are the ones `python manage.py seed_demo` creates:
`doctor1`, `patient1`, `admin`, all with password `demo12345`. Choosing an
account fills the form; it does not sign in silently, so the credentials are
visible before they are used.

A failed login shows the server's message. A `401` from the login endpoint is
translated to "That username and password do not match", because SimpleJWT's
default body is not a useful sentence for a person.

### 4.2 The shell, navigation and the disclaimer

The shell is a fixed sidebar plus a scrolling main column. The sidebar contains:

* the brand;
* a **Monitor** group: Dashboard, Live monitor, Sessions;
* a **Manage** group: Patients (or "My profile" for a patient), and Devices for
  doctors/admins;
* the health of both services (Django and FastAPI are probed every 30 s);
* the signed-in user, role and sign-out.

The top bar carries the current screen, a date/time clock and the role chip.
Below it, every screen in the shell shares a persistent amber strip:

> **Screening aid, not a medical diagnosis.** Data shown here is synthetic or
> replayed research data unless a real device is connected.

On narrow screens the sidebar becomes an off-canvas drawer with a scrim. The
table and monitor layouts collapse to one column rather than shrinking a
waveform to an unreadable width.

### 4.3 Dashboard

The dashboard is role-aware by composition, not by conditionals inside one
component: `DashboardPage` renders `ProviderDashboard` for doctors/admins and
`PatientDashboard` for patients. Each component calls only the resources its
role may read.

The provider view shows:

* active sessions, patients in view, registered devices, and devices online;
* a "Live now" table with links to the live monitor;
* a three-step demo explanation (start a session, run the simulator, watch then
  revisit);
* the most recent sessions.

A patient sees their own active session, their devices-on-sessions count, a
read-only access note, their profile from Django, and their session history.
A patient account that has no active session gets an explanation, not an error.

### 4.4 Patients

A searchable card grid. Each card carries the username, email, date of birth,
patient id, notes, session count and the active session if there is one. A card
links to the live monitor when a session is active, otherwise to the latest
recording.

Doctors and admins get a "Start session" button on each card. The dialog picks a
device and explains the consequence: the server creates the session and pushes it
to FastAPI's registry. The API rejects a disabled device, another doctor's
device, an unassigned patient, or a second active session on the same device;
those messages are rendered in the dialog rather than swallowed.

The patient view of `/patients` is "My profile": one card and the identity
fields. It is the same route because the server already scopes the patient list
to one row, and a separate component would duplicate the fetch.

### 4.5 Devices

A table of the devices the caller may see, plus two registration facts:

* **the token is returned once and never stored**, so it is displayed in a
  dialog with a copy button and a warning; losing it means rotating it;
* **online is a heartbeat**, not a guess from the last reading. The badge comes
  from `GET /sensor/status`, whose `online` field is
  `seconds_since_seen <= threshold_seconds` (120 s by default).

Each row shows registration state (`active`/`disabled` from Django), heartbeat
state (online/offline/revoked/never seen from FastAPI), last seen time, the
device UUID with a copy button, and a rotate-token action. Admins also see the
owner's username.

A device that has never connected has no row in `device_connections`, so it
correctly reads "No heartbeat yet" rather than "offline". Disabling a device in
Django and revoking it in FastAPI are still two different actions (Phase 7
joins them); the UI reports each service's own truth.

### 4.6 Sessions

The history page lists every session the caller may see, newest first, with
search over patient, device and session id, a status filter, and a URL-driven
patient filter (`/sessions?patient=<id>`). A row opens the live monitor if the
session is active and the recording viewer if it is not.

Sessions carry `patient_name` and `device_name` from Django. Without those
fields the page would have to join two extra lists in the browser just to say
whose session it is; the labels are read-only projections of the foreign keys,
so they cannot be spoofed by a request body.

### 4.7 Live monitor — `WS /ws/sensor` plus REST for samples

The live screen is the part that makes the dashboard worth building. It uses
both backend paths at once:

```
open session
  ├─ REST  GET /sessions/<id>            (Django: patient, device, status)
  ├─ REST  GET /sessions/<id>/ecg        (FastAPI: chunk index, metadata only)
  │        └─ fetch the last 6 chunks    (FastAPI: samples)
  ├─ WS    /ws/sensor?session_id&token
  │        ├─ snapshot: last 20 scalar readings
  │        ├─ reading: temperature / spo2 / pulse / motion
  │        └─ ecg_chunk: chunk_index, sample_count, rate, start_time
  └─ REST  GET /sensor/status            (FastAPI: device heartbeat)
```

The socket deliberately does **not** carry thousands of samples. The contract
says `ecg_chunk` is metadata only; pushing 400 samples every two seconds down
every viewer socket is the wrong shape for a viewer that may be on a phone. When
a chunk announcement arrives, the screen fetches that one chunk over REST and
appends it to the chart buffer. A late viewer does not wait for the next chunk:
the initial REST read seeds the last six chunks, and the snapshot gives the last
20 scalar readings.

The chart is uPlot, wrapped in `EcgChart.tsx`. React never re-renders 2 000
points: the wrapper creates one plot, measures its container with a
`ResizeObserver`, and calls `setData` when the series changes. The y-axis is
symmetric around zero, so a waveform does not drift up the canvas as the signal
baseline wanders.

The buffer keeps the most recent 12 seconds (six 2-second chunks at 200 Hz). x
positions are derived from each chunk's `start_time`, not from a running
counter, so a dropped chunk appears as a real gap instead of silently squashing
the waveform. The buffer is bounded at 18 chunks so a long session cannot grow
browser memory without limit.

Below the waveform, four vital cards show the latest value, unit, time, age and
a sparkline of the recent history (240 readings per sensor). The values come from
the socket; the cards do not invent ranges, alarms or a "normal" band. The
heart-rate card is the device's `pulse` reading, not a BPM computed from the ECG;
beat detection is Phase 5.

Socket lifecycle:

| Event | UI |
| --- | --- |
| first connect | "Connecting" badge; snapshot and REST seed fill the screen |
| open | "Live" badge; ping every 20 s |
| unexpected close | "Reconnecting" with exponential backoff, capped at 10 s; data stays on screen |
| close `4401` | "Sign in again" — no automatic retry loop |
| close `4403` | "You are not allowed to watch this session" |
| close `4404` | FastAPI does not know the session; explains the registry push |
| manual retry | "Reconnect now" increments a generation and reopens the socket |

The device badge is refreshed from `/sensor/status` every 15 s. The session
header shows the elapsed time from `start_time`, updating once a second without
refetching the session. A doctor or admin can stop the session from this screen;
the button posts `/stop/`, and the header switches to completed. A patient never
sees the control.

### 4.8 Recording viewer — history

The recording page reads the chunk index, then loads a **window** of chunks
rather than the whole recording. The default window is 12 chunks (24 s at 200
Hz); the user can choose 6, 12 or 24, step earlier/later, or use a range slider
that starts at any chunk. This keeps the request bounded and makes a session
with hundreds of chunks usable without a server-side downsampler.

The waveform is the same `EcgChart` and the same `buildEcgSeries` function as
the live view, but x starts at the first selected chunk instead of at "now", and
gaps between chunk start times are preserved. The chunk list on the side is a
shortcut into the index; clicking a chunk moves the window near it.

The vital summary is arithmetic over the newest 500 scalar readings the API
returns: latest, minimum, maximum and average per sensor, plus a sparkline. It is
computed in the browser because Phase 2 exposes no aggregation endpoint; the
page says "newest 500" when the limit is reached rather than implying it has the
whole session. No clinical range, flag or score is inferred.

The session panel shows patient, device, start, end and status. An active
session links to the live monitor and offers the same stop control; a completed
one links back to history. The page is reachable for active sessions too, which
is useful when the live socket cannot be used.

## 5. State, polling and error handling

There is no Redux, no React Query and no global cache. The application is small
enough that one hook, `useResource(key, loader, { pollMs, enabled })`, covers the
readable state:

* `key` identifies the request; changing it reloads;
* `pollMs` refreshes in the background without clearing the table underneath;
* `enabled` lets a provider-only resource stay idle for a patient;
* `refresh()` is the same loader on demand, used by Retry buttons.

Polling intervals are conscious choices, not a default: sessions 15 s, device
status 15 s, devices 30 s, patients 60 s, session detail 30 s, recording
readings/chunks 30 s. The live screen does not poll the socket; it reacts to
frames.

Every page distinguishes three states: loading (spinner), error (a banner with
Retry), and empty (an explanation with the next useful action). A network error
from FastAPI says "Is FastAPI running on port 8001?" instead of showing
`TypeError: Failed to fetch`. A `404` on a session is shown as an error banner,
not as a blank page.

The live hook deduplicates readings by `(sensor_type, recorded_at)`, so the
snapshot after a reconnect does not duplicate the history that is already on
screen. Chunk fetches are deduplicated by index and by an in-flight set, so a
reconnect and a chunk announcement cannot race into two copies of the same
chunk.

## 6. Backend additions made for the dashboard

### 6.1 `GET /sessions/<session_id>/ecg` — the chunk index

Before Phase 4 there was a "read one chunk" endpoint but no way to discover
which chunks exist. A history viewer cannot ask for chunk 7 without knowing that
7 exists, and probing indexes until a 404 is both wasteful and racy.

The new endpoint returns metadata only:

```json
{
  "session_id": "9b2e…",
  "count": 17,
  "chunks": [
    {
      "chunk_id": "7d1f…",
      "chunk_index": 0,
      "sample_rate_hz": 200,
      "sample_count": 400,
      "start_time": "2026-10-05T12:00:00Z",
      "duration_seconds": 2.0
    }
  ]
}
```

It uses the same viewer permission check as the single-chunk read: patient on
the session, assigned doctor, or admin. Samples are still fetched one chunk at a
time. This is the only new FastAPI route in the phase.

### 6.2 Session and device labels in Django

`SessionSerializer` now includes `patient_name` and `device_name`; both are
read-only fields derived from the foreign keys. `DeviceSerializer` adds
`owner_username` for the admin device list. These are presentation fields, not
new authorization: they are only present on rows the queryset already allowed
the caller to read.

### 6.3 The expiry claim is now enforced

`docs/api-contract.md` section 3 already said a token without `exp` is rejected.
The verifier did not actually require the claim: PyJWT verifies an expiry when
one is present, but accepts a token that has none. The Phase 4 work tightened
`decode` with `options={"require": ["exp"]}`, so the code now matches the
contract and a device token cannot become immortal by omitting one field.

### 6.4 Small correctness fixes the dashboard exposed

These are not dashboard features, but the live path could not be trusted
without them:

* **SQLite migration defaults.** The Alembic migration used `sa.text("now()")`
  for `registered_at`/`received_at` defaults. That is PostgreSQL syntax; a SQLite
  insert failed with `unknown function: now()` at the exact moment the dashboard
  tried to register a session. It now uses `sa.func.now()`, which compiles to
  `CURRENT_TIMESTAMP` on SQLite and `now()` on PostgreSQL. Tests on SQLite only
  create tables from the models, which is why the migration path had not caught
  it.
* **Simulator timing flags.** `--duration`, `--interval`, `--heartbeat-seconds`
  and `--offline-after` were parsed onto `args.duration`, `args.interval`, etc.,
  while `build_config` looked for the `*_seconds` field names. Every timing flag
  was silently ignored and the run used its 30 s/1 s defaults. The parser now
  uses the `Config` field names, with a regression test.
* **WebSocket test isolation.** The socket route imported `SessionFactory` by
  value, so the test suite's engine patch did not reach it and socket tests saw
  an empty database. The fixture now patches the route's binding too (test-only).
* **Django manager migration state.** `accounts.User` uses a custom
  `UserManager`, but migration `0001` recorded Django's stock manager. The
  generated `accounts/migrations/0003_alter_user_managers.py` records the manager
  the model actually uses; it changes no tables or columns.

## 7. Decisions made while building this (recorded, as requested)

1. **One origin in development, two proxies.** The browser never learns that
   Django and FastAPI are separate processes. No CORS relaxation was needed for
   the dashboard, and the WebSocket shares the page origin.
2. **The socket carries readings and chunk announcements, not samples.** REST is
   the right place for a 400-sample array; the socket stays small enough for a
   phone and the recording endpoint is reused for late viewers.
3. **The chunk index is a first-class endpoint.** Discovering what exists should
   not be a loop of guessed 404s, and a list of metadata is cheap.
4. **uPlot, not a React chart per point.** The chart owns its canvas; React owns
   the page. A 2 000-point series updating four times a second does not belong in
   the React render path.
5. **The chart buffer is bounded by time, not by a sample count that differs per
   rate.** Twelve seconds is the visual unit; 200 Hz makes that 2 400 points at
   the simulator's rate, but a 500 Hz device would still show twelve seconds.
6. **A dropped chunk must look like a gap.** x comes from `start_time`, not from
   `chunk_index × duration`, so a hole in the recording is visible and the
   waveform does not slide left.
7. **The device badge is heartbeat truth, not inference.** A reading proves the
   device was alive earlier; only `last_seen` from `/sensor/connect` answers
   "is it online now".
8. **The dashboard does not compute BPM.** Drawing the signal is Phase 4; R-peak
   detection, BPM and signal quality are Phase 5 and belong on the server, where
   they can be tested against MIT-BIH annotations and reused by reports.
9. **Session labels come from Django, not from a browser join.** The browser
   already has enough lists to join; adding two read-only fields removes a
   fragile id-to-name map from every page.
10. **Role-aware composition over one component full of conditionals.** The
    provider and patient dashboards call different endpoints; keeping them as
    separate components makes the allowed requests obvious and prevents a
    patient's page from firing a `/devices/` request that can only 403.
11. **Tokens in local storage, recorded as a trade-off.** It is the simplest
    thing that survives a reload with the existing JWT flow. The alternative
    (httpOnly cookies + CSRF) is stronger and is a later hardening task, not
    something to pretend away in the notes.
12. **The demo accounts are visible but not auto-submitted.** A login screen that
    signs itself in is convenient for a video and terrible for explaining what
    authentication is doing.

## 8. Deliberate limits

* **No BPM, no beat markers, no arrhythmia classification, no signal-quality
  score.** The ECG is drawn, not interpreted. Those arrive in Phase 5 behind the
  `/inference` slot.
* **No server-side downsampling or full-recording view.** The viewer loads a
  bounded window of chunks. A 10-minute recording is navigated, not rendered in
  one canvas. This is adequate for the demo and honest about the browser's
  limits.
* **No export or PDF report.** The vital summary is on screen; Phase 6 owns
  reports and the audit of who downloaded one.
* **No WebSocket fan-out across processes.** The live socket is Phase 2's
  in-process hub. Two FastAPI replicas would each see only their own viewers;
  Redis pub/sub is the later fix.
* **No push for session lifecycle.** A newly started session can take up to the
  15 s session poll to appear in another tab. The tab that starts it navigates
  directly, so the common path is immediate.
* **A newly registered device has no heartbeat.** It appears in the device list
  from Django, but FastAPI has no `device_connections` row until the first
  `/sensor/connect`. The badge says "No heartbeat yet" rather than pretending to
  know.
* **Django "disabled" and FastAPI "revoked" are separate.** The device page
  reports each; the two are joined in Phase 7.
* **An admin who registers a device owns it.** `DeviceViewSet.create` sets
  `owner=request.user`, and the UI says so. Creating a device *for* a doctor is
  an admin-panel operation, not a dashboard action.
* **Patients cannot list devices.** The Django device endpoint is
  doctor/admin-only, so a patient's session shows the device name (from the
  session label) but the patient has no device inventory page.
* **The token is in local storage and the socket's query string.** Both are
  documented costs. The access token is short-lived; a one-time socket ticket and
  httpOnly cookies are hardening, not Phase 4.
* **One dark theme.** The dashboard is designed for a dim monitoring room; there
  is no light-mode toggle and no user preference.
* **No React component test runner yet.** TypeScript strict mode, ESLint and the
  backend suites are the current guardrails; the data path was exercised against
  a live simulator. A Vitest/Playwright layer is worth adding when the UI has
  more branches than one person can click through.
* **StrictMode opens and closes the socket twice in development.** React 19's
  StrictMode double-invokes effects; the cleanup closes the first socket, so the
  user sees one live connection. Production builds do not double-mount.
* **Not a clinical device.** No calibration, no alarm thresholds, no regulatory
  claim. Screening aid, not a medical diagnosis.

## 9. Running the dashboard

Prerequisites are the two services from Phases 1–3.

```bash
# Django (identity + sessions)
cd backend/django
python manage.py migrate
python manage.py seed_demo          # admin, doctor1/doctor2, patient1..4, password demo12345
python manage.py runserver 8000

# FastAPI (telemetry)
cd backend/fastapi
python -m alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001

# React
cd frontend
npm install
npm run dev                         # http://localhost:5173
```

FastAPI must be running when a session is started: Django pushes the session to
`/internal/sessions` as a best-effort side effect. If FastAPI was down at that
moment, the session appears in Django's history but its live socket answers
`4404` until the registry is re-synced (the endpoint is an idempotent upsert).

To run a second stack beside an existing one, override the proxy targets and the
Vite port:

```bash
VITE_DJANGO_PROXY=http://127.0.0.1:8010 \
VITE_FASTAPI_PROXY=http://127.0.0.1:8011 \
npm run dev -- --host 127.0.0.1 --port 5175
```

Other frontend commands:

| Command | What it does |
| --- | --- |
| `npm run dev` | Vite dev server on 5173, with both proxies |
| `npm run build` | `tsc -b` then a production bundle in `dist/` |
| `npm run preview` | Serve the built bundle on 5173 (also proxied) |
| `npm run lint` | ESLint, including the React hooks rules |
| `npm run typecheck` | TypeScript only |

The demo path, once all three processes are up:

1. sign in as `doctor1` / `demo12345`;
2. open **Patients**, choose `patient1`, **Start session**;
3. open the live monitor for it;
4. run the simulator with that session's device token and id, or let
   `mint_new_run.py` create its own session and open that one;
5. watch the waveform and vitals, stop the session, then find it under
   **Sessions**.

The simulator's ECG chunks are uploaded as fast as they are produced, so a
viewer that opens after a short run may receive no new `ecg_chunk` frames; the
REST seed is what fills the screen in that case. A real device streams in real
time and the socket path is the one that matters.

## 10. What Phase 5 inherits

Phase 5 can add analysis without moving the dashboard:

* the samples are already in `ecg_chunks` with a rate and a start time;
* `EcgChart` accepts any `{x, y}` series, so a filtered signal or an R-peak
  overlay is another series, not a new chart;
* `useLiveMonitor` is the one place that knows about socket frames, so a
  `prediction` frame can be added beside `reading` and `ecg_chunk`;
* the recording page already has the chunk index and a window selector, which is
  where "run inference on this window" belongs;
* BPM and quality flags should be stored and returned by FastAPI, not computed
  in the browser, so reports and the dashboard cannot disagree;
* the screening disclaimer is already everywhere the new output will appear.

The contract remains the contract: a new field or a new analysis endpoint, not a
new ingestion format for the ESP32.
