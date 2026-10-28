export const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '/api').replace(/\/$/, '')

export const TELEMETRY_DEFAULT = (
  import.meta.env.VITE_TELEMETRY_BASE_URL ?? '/telemetry'
).replace(/\/$/, '')

const TELEMETRY_OVERRIDE_KEY = 'ecg.telemetryBase'

export type ApiBase = 'django' | 'telemetry'

export function telemetryBase(): string {
  return (localStorage.getItem(TELEMETRY_OVERRIDE_KEY) || TELEMETRY_DEFAULT).replace(
    /\/$/,
    '',
  )
}

export function setTelemetryBase(value: string | null): void {
  if (value && value.trim()) {
    localStorage.setItem(TELEMETRY_OVERRIDE_KEY, value.trim().replace(/\/$/, ''))
  } else {
    localStorage.removeItem(TELEMETRY_OVERRIDE_KEY)
  }
}

export function defaultTelemetryBase(): string {
  return TELEMETRY_DEFAULT
}
