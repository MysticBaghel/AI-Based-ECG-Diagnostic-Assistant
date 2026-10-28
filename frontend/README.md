# Frontend — React + TypeScript (Vite)

The Phase 4 dashboard for the AI-Based ECG Diagnostic Assistant. It signs into
Django, lists patients, devices and sessions, starts and stops monitoring
sessions, and watches a session live over `WS /ws/sensor` with an ECG waveform
and four vital signs.

> **Screening aid, not a medical diagnosis.** Data shown here is synthetic or
> replayed research data unless a real device is connected. Nothing on screen is
> a clinical finding.

## Requirements

- Node.js 20.19+ or 22.12+ (developed on Node 24)
- npm 10+
- Django on `http://127.0.0.1:8000`
- FastAPI on `http://127.0.0.1:8001`

## Quick start

```bash
# Django
cd backend/django
python manage.py migrate
python manage.py seed_demo          # admin, doctor1/2, patient1..4; password demo12345
python manage.py runserver 8000

# FastAPI
cd backend/fastapi
python -m alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001

# Dashboard
cd frontend
npm install
npm run dev                         # http://localhost:5173
```

Sign in as `doctor1` / `demo12345` to start a session, or `patient1` /
`demo12345` to see the read-only view. `admin` / `demo12345` sees every patient
and device.

## Routes

| Route | Who | Purpose |
| --- | --- | --- |
| `/login` | public | Sign in against Django |
| `/` | all roles | Overview and active sessions |
| `/patients` | all roles | Patient list; patients see their own profile |
| `/devices` | doctor, admin | Register devices, heartbeats, rotate tokens |
| `/sessions` | all roles | Session history with search and filters |
| `/sessions/:id` | viewers | Stored waveform, vital summary, stop session |
| `/live` | all roles | Pick an active session |
| `/live/:id` | viewers | Live ECG and vitals over WebSocket |

Role scoping is enforced by the Django queries and FastAPI's viewer checks. The
client-side navigation and `RoleGate` only keep unneeded pages out of the way.

## Backend connection

`vite.config.ts` keeps the browser on one origin and proxies two paths:

| Browser path | Target | Service |
| --- | --- | --- |
| `/api/*` | `http://127.0.0.1:8000` | Django (identity, patients, devices, sessions) |
| `/telemetry/*` | `http://127.0.0.1:8001` | FastAPI (readings, chunks, status, WebSocket) |

`/telemetry` is stripped before the request reaches FastAPI. The proxy entry has
`ws: true`, so `/telemetry/ws/sensor` upgrades to FastAPI's `/ws/sensor` on the
same page origin.

Both targets can be overridden for a second local stack:

```bash
VITE_DJANGO_PROXY=http://127.0.0.1:8010 \
VITE_FASTAPI_PROXY=http://127.0.0.1:8011 \
npm run dev -- --port 5175
```

For a production build, a reverse proxy must make the same two mappings; the
frontend has no hard-coded backend ports beyond the defaults.

## Scripts

| Command | What it does |
| --- | --- |
| `npm run dev` | Vite dev server on 5173 with both proxies |
| `npm run build` | `tsc -b` and a production bundle in `dist/` |
| `npm run preview` | Serve `dist/` with the same proxies |
| `npm run lint` | ESLint, including React hooks rules |
| `npm run typecheck` | TypeScript only |

## Layout

```
frontend/
├── index.html            # Vite entry, title and meta description
├── vite.config.ts        # /api and /telemetry proxies, WebSocket upgrade
├── package.json          # React, React Router, uPlot
├── public/ecg.svg        # favicon
└── src/
    ├── main.tsx          # StrictMode + BrowserRouter
    ├── App.tsx           # routes, AuthProvider, role gates
    ├── index.css         # design tokens and all component styles
    ├── api/              # fetch client, token refresh, API types
    ├── auth/             # auth context, useAuth, RequireAuth/RoleGate
    ├── components/       # shell, ECG chart, vitals, tables, dialogs
    ├── hooks/            # useResource, typed data hooks, useLiveMonitor
    ├── lib/              # formatting and chunk -> series conversion
    └── pages/            # one file per screen
```

## How the live screen works

1. Load the session from Django.
2. Load the chunk index from FastAPI (`GET /sessions/:id/ecg`) and seed the last
   six chunks of samples.
3. Open `WS /ws/sensor` for the last 20 readings (snapshot), live scalar
   readings, and `ecg_chunk` metadata.
4. On each `ecg_chunk`, fetch that chunk over REST and append it to the uPlot
   buffer. The chart keeps a rolling 12 second window.
5. Poll `/sensor/status` every 15 seconds for the device heartbeat.

The socket deliberately sends no samples; the REST endpoint is reused for the
waveform. See [Phase 4 notes](../docs/phase-4-notes.md) for the design decisions
and limits.

## Note on installing dependencies

If `npm install` fails with `EPERM` on the npm cache directory, the shell is
sandboxed and cannot write to the default user cache. Point the cache inside the
project instead:

```bash
npm_config_cache=../.npm-cache npm install
```

On PowerShell:

```powershell
$env:npm_config_cache = "..\.npm-cache"
npm install
```
