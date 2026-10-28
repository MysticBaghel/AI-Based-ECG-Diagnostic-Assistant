import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Both backends are proxied through the Vite origin during development, so the
// browser never needs CORS and the WebSocket handshake shares the same origin.
//
//   /api/*        -> Django    (identity, patients, devices, sessions)
//   /telemetry/*  -> FastAPI   (readings, ECG chunks, /sensor/status, /ws/sensor)
//
// `/telemetry` is stripped before the request reaches FastAPI, whose routes are
// mounted at the root (`/sensor/status`, `/ws/sensor`, ...).
// The defaults are the documented ports. The environment overrides exist so a
// second dev stack can run alongside a first one (and for the Phase 4 smoke
// test, which uses 8010/8011 when 8000/8001 are already taken).
const djangoTarget = process.env.VITE_DJANGO_PROXY ?? 'http://127.0.0.1:8000'
const fastapiTarget = process.env.VITE_FASTAPI_PROXY ?? 'http://127.0.0.1:8001'

const proxy = {
  '/api': {
    target: djangoTarget,
    changeOrigin: true,
  },
  '/telemetry': {
    target: fastapiTarget,
    changeOrigin: true,
    ws: true,
    rewrite: (path: string) => path.replace(/^\/telemetry/, ''),
  },
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy,
  },
  preview: {
    port: 5173,
    proxy,
  },
})
