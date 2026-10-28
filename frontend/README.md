# Frontend — React + TypeScript (Vite)

The operator interface for the AI-Based ECG Diagnostic Assistant. It is a focused
ECG workflow, not a hospital management dashboard.

## Screens

| Route | Purpose |
| --- | --- |
| `/login` | Operator sign-in (JWT) |
| `/` | Dashboard: patient search, start a recording, recent recordings, service/device/AI status |
| `/patients` | Search by name, phone or patient ID; register a patient |
| `/patients/:id` | Patient profile, previous ECG sessions, analysis availability, report downloads, start a new recording |
| `/monitor/:sessionId` | Live ECG waveform, socket/recording status, live signal quality and heart-rate estimate, stop & analyse |
| `/sessions/:sessionId` | Stored waveform, measured parameters, AI findings or explicit unavailability, PDF report generation/download |
| `/settings` | API connections, device registration/tokens, heartbeat, AI model status |

Removed with the hospital workflow: doctor lists, doctor profiles, doctor-patient
assignment, role-gated navigation, admin patient creation, session history as a
separate administration screen, and the four-vital dashboard.

## Run

```bash
npm install
npm run dev        # http://localhost:5173
npm run build
npm run lint
npm run typecheck
```

The Vite dev server proxies `/api` to Django (`127.0.0.1:8000`) and
`/telemetry` to FastAPI (`127.0.0.1:8001`). Override with `VITE_DJANGO_PROXY` and
`VITE_FASTAPI_PROXY`. The telemetry base URL can also be changed at runtime in
**Settings**.

## Data flow

* Django owns authentication, the permanent patient registry, sessions,
  analysis snapshots and report metadata/downloads.
* FastAPI owns ECG chunks, scalar telemetry, the session registry, DSP and the
  optional inference interface.
* The live monitor uses `WS /ws/sensor` for chunk announcements and fetches the
  samples over REST; it polls `GET /sessions/:id/analysis/live` for quality and
  heart rate without persisting a version.
* The analysis page reads stored data only and can generate/download the PDF.

## Safety

Every screen carries the screening-aid disclaimer. AI output is shown only when
a validated model actually produced it; otherwise the UI says it is unavailable.
Simulator ECG is synthetic or replayed research data and does not demonstrate
diagnostic accuracy.
