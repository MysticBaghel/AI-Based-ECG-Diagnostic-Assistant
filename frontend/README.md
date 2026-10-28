# Frontend — PulseTrace ECG

React 19 + TypeScript + Vite application for the AI-Based ECG Diagnostic Assistant.

## Commands

```bash
npm install
npm run dev        # http://localhost:5173
npm run build
npm run lint
npm run typecheck
npm test           # Vitest + React Testing Library
npm run test:watch
```

## Architecture

The frontend is organised by **feature**, not by file type:

```text
src/
  app/                     application composition
    App.tsx                providers + suspense + error boundary
    providers.tsx          QueryClient + AuthProvider
    routes.tsx             lazy route table
    shell/                 AppShell, Sidebar, Topbar, GlobalSearch,
                           Notifications, UserMenu, navigation model
  features/
    auth/                  AuthContext, route guard, login page, auth API
    dashboard/             dashboard page + focused cards
    patients/              registry API/hooks, table, filters, pagination,
                           patient form (RHF + Zod), profile cards
    sessions/              session API/hooks and shared session components
    monitor/               live socket, live analysis, monitor components
    analysis/              analysis cards, waveform, report history
    reports/               report API and report history page
    devices/               device API/hooks/components/page
    settings/              API/model settings page
  shared/
    api/                   HTTP + token store + query adapter + health
    charts/                uPlot ECG wrapper
    hooks/                 useNow and other cross-feature hooks
    icons/                 Icon component and icon map
    lib/                   formatting and ECG series helpers
    types/                 domain API contracts split by domain
    ui/                    design primitives and dialogs
  styles/                  tokens, base, shell, controls, feature styles,
                           theme overrides and responsive rules
  test/                    Vitest setup
```

Import direction:

```text
pages → feature components/hooks → shared
```

Absolute imports use the `@/` alias configured in both `tsconfig.app.json`
and `vite.config.ts`.

## Server state

Server state is handled by **TanStack Query** through the small
`useResource` adapter in `shared/api/useResource.ts`. Feature hooks own their
query keys and polling intervals; components do not know about the query
library. Mutations (patient form) use `useMutation`.

## Forms

Patient registration/editing uses **React Hook Form + Zod**. Validation is
schema-driven, and the duplicate-phone `409` flow is handled explicitly.

## Code splitting

Every page is loaded with `React.lazy` + `Suspense`; the shell stays mounted
while a feature page loads. `ErrorBoundary` prevents one page error from
blanking the shell.

## Routes

| Route | Purpose |
| --- | --- |
| `/login` | Operator sign-in |
| `/` | Dashboard |
| `/patients` | Registry table, filters, pagination |
| `/patients/:id` | Patient profile and ECG history |
| `/monitor` | Active recording picker |
| `/monitor/:sessionId` | Live ECG monitor |
| `/reports` | Report history and downloads |
| `/sessions/:sessionId` | Analysis and PDF report |
| `/devices` | Device registration and heartbeat |
| `/settings` | API/model settings |

## Data flow

Django owns identity, patients, sessions, analysis snapshots and reports.
FastAPI owns ECG chunks, scalar telemetry, DSP and optional inference. The
monitor uses the WebSocket for chunk announcements and the REST chunk endpoint
for samples; the analysis page works from stored data.

## Safety

Every screen carries the screening-aid notice. AI output is rendered only when
a validated model actually produced it; otherwise the interface states that AI
is unavailable. Simulator ECG is synthetic or replayed research data and does
not demonstrate diagnostic accuracy.
