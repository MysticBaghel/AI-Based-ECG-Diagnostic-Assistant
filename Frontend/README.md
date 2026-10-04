# Frontend — React + TypeScript (Vite)

Single-page app for the Major Project, built with React 19, TypeScript and Vite 8.

## Requirements

- Node.js 20.19+ or 22.12+ (developed on Node 24)
- npm 10+

## Scripts

| Command             | What it does                                          |
| ------------------- | ----------------------------------------------------- |
| `npm run dev`       | Start the dev server on http://localhost:5173         |
| `npm run build`     | Type-check (`tsc -b`) and build to `dist/`            |
| `npm run preview`   | Serve the built `dist/` locally                       |
| `npm run lint`      | Run ESLint over the project                           |
| `npm run typecheck` | Type-check only                                       |

## Backend connection

`vite.config.ts` proxies any request starting with `/api` to the backend at
`http://127.0.0.1:8000` (Django + FastAPI). This keeps the browser on a single
origin during development, so no CORS configuration is needed.

The starter page calls `GET /api/health` on load and shows whether the backend
is reachable.

## Layout

```
Frontend/
├── index.html          # Vite entry HTML
├── vite.config.ts      # Vite config + /api proxy to the backend
├── tsconfig*.json      # TypeScript project references
├── eslint.config.js    # ESLint flat config
├── public/             # Static assets served as-is
└── src/
    ├── main.tsx        # React root
    ├── App.tsx         # Root component (backend health check)
    ├── App.css
    ├── index.css
    └── vite-env.d.ts
```

## Note on installing dependencies

If `npm install` fails with `EPERM` on the npm cache directory, the shell is
sandboxed and cannot write to `%LOCALAPPDATA%\npm-cache`. Point the cache inside
the project instead:

```powershell
$env:npm_config_cache = "D:\Major Project\.npm-cache"
npm install
```
