/**
 * The browser's only door to the two backends.
 *
 * Django is reached through `/api` (identity, patients, devices, sessions,
 * analysis records, reports). FastAPI is reached through `/telemetry` in
 * development; Vite proxies both, so the browser stays on one origin.
 */

import type {
  AnalysisResult,
  Device,
  EcgChunk,
  EcgChunkList,
  Health,
  Patient,
  PatientInput,
  ReadingsResponse,
  ReportMeta,
  Session,
  StatusResponse,
  TokenPair,
  User,
} from './types'

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '/api').replace(/\/$/, '')
const TELEMETRY_DEFAULT = (
  import.meta.env.VITE_TELEMETRY_BASE_URL ?? '/telemetry'
).replace(/\/$/, '')
const TELEMETRY_OVERRIDE_KEY = 'ecg.telemetryBase'

const ACCESS_KEY = 'ecg.access'
const REFRESH_KEY = 'ecg.refresh'

export const AUTH_EXPIRED_EVENT = 'ecg:auth-expired'

type Base = 'django' | 'telemetry'

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: unknown
  auth?: boolean
  base?: Base
  signal?: AbortSignal
}

interface ErrorBody {
  detail?: unknown
  code?: string
  errors?: { field?: string; message?: string }[]
  duplicates?: Patient[]
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly fields: Record<string, string>
  readonly payload: ErrorBody

  constructor(
    message: string,
    options: {
      status?: number
      code?: string
      fields?: Record<string, string>
      payload?: ErrorBody
    } = {},
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = options.status ?? 0
    this.code = options.code ?? 'network_error'
    this.fields = options.fields ?? {}
    this.payload = options.payload ?? {}
  }
}

// --- runtime configuration -------------------------------------------------

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

// --- token storage ---------------------------------------------------------

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_KEY)
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY)
}

export function storeTokens(tokens: TokenPair): void {
  localStorage.setItem(ACCESS_KEY, tokens.access)
  localStorage.setItem(REFRESH_KEY, tokens.refresh)
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
}

// --- errors ----------------------------------------------------------------

function describeDetail(body: ErrorBody): string {
  if (typeof body.detail === 'string' && body.detail.trim()) return body.detail
  if (Array.isArray(body.errors) && body.errors.length > 0) {
    return body.errors
      .map((error) => (error.field ? `${error.field}: ${error.message}` : error.message))
      .filter(Boolean)
      .join('; ')
  }
  if (body.detail && typeof body.detail === 'object') {
    return Object.entries(body.detail as Record<string, unknown>)
      .map(([field, messages]) => `${field}: ${String(messages)}`)
      .join('; ')
  }
  return ''
}

async function toApiError(response: Response, base: Base): Promise<ApiError> {
  let body: ErrorBody = {}
  try {
    body = (await response.json()) as ErrorBody
  } catch {
    // A proxy or a crashed service can answer with HTML or an empty body.
  }

  const fallback =
    base === 'telemetry'
      ? `Telemetry service answered HTTP ${response.status}.`
      : `Request failed with HTTP ${response.status}.`
  const fields: Record<string, string> = {}
  for (const error of body.errors ?? []) {
    if (error.field) fields[error.field] = error.message ?? 'Invalid value'
  }

  return new ApiError(describeDetail(body) || fallback, {
    status: response.status,
    code: body.code ?? `http_${response.status}`,
    fields,
    payload: body,
  })
}

// --- refresh ---------------------------------------------------------------

let refreshInFlight: Promise<string | null> | null = null

function expireSession(): void {
  clearTokens()
  window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT))
}

async function refreshAccessToken(): Promise<string | null> {
  const refresh = getRefreshToken()
  if (!refresh) return null

  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const response = await fetch(`${API_BASE}/auth/refresh/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh }),
        })
        if (!response.ok) {
          expireSession()
          return null
        }
        const data = (await response.json()) as { access: string }
        localStorage.setItem(ACCESS_KEY, data.access)
        return data.access
      } catch {
        return null
      } finally {
        refreshInFlight = null
      }
    })()
  }

  return refreshInFlight
}

// --- request ---------------------------------------------------------------

async function authorizedFetch(
  path: string,
  options: RequestOptions = {},
): Promise<Response> {
  const base: Base = options.base ?? 'django'
  const root = base === 'telemetry' ? telemetryBase() : API_BASE
  const wantsAuth = options.auth !== false

  const send = (token: string | null): Promise<Response> => {
    const headers: Record<string, string> = {}
    if (options.body !== undefined) headers['Content-Type'] = 'application/json'
    if (wantsAuth && token) headers.Authorization = `Bearer ${token}`

    return fetch(`${root}${path}`, {
      method: options.method ?? 'GET',
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal,
    })
  }

  let response: Response
  try {
    response = await send(getAccessToken())
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(
      base === 'telemetry'
        ? 'Cannot reach the telemetry service. Is FastAPI running on port 8001?'
        : 'Cannot reach the Django API. Is it running on port 8000?',
      { code: 'network_error' },
    )
  }

  if (response.status === 401 && wantsAuth && getRefreshToken()) {
    const token = await refreshAccessToken()
    if (token) {
      try {
        response = await send(token)
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') throw error
        throw new ApiError('Cannot reach the backend after refreshing the session.', {
          code: 'network_error',
        })
      }
    }
  }

  if (!response.ok) {
    if (response.status === 401 && wantsAuth) expireSession()
    throw await toApiError(response, base)
  }

  return response
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await authorizedFetch(path, options)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

async function requestBlob(
  path: string,
  options: RequestOptions = {},
): Promise<Blob> {
  const response = await authorizedFetch(path, options)
  return response.blob()
}

// --- Django endpoints ------------------------------------------------------

export const api = {
  health(): Promise<Health> {
    return request<Health>('/health/', { auth: false })
  },

  login(username: string, password: string): Promise<TokenPair> {
    return request<TokenPair>('/auth/login/', {
      method: 'POST',
      body: { username, password },
      auth: false,
    })
  },

  me(): Promise<User> {
    return request<User>('/auth/me/')
  },

  // -- patients ------------------------------------------------------------
  patients(query = ''): Promise<Patient[]> {
    const suffix = query.trim() ? `?q=${encodeURIComponent(query.trim())}` : ''
    return request<Patient[]>(`/patients/${suffix}`)
  },

  patient(patientId: number): Promise<Patient> {
    return request<Patient>(`/patients/${patientId}/`)
  },

  createPatient(input: PatientInput, confirmDuplicate = false): Promise<Patient> {
    return request<Patient>('/patients/', {
      method: 'POST',
      body: { ...input, confirm_duplicate: confirmDuplicate },
    })
  },

  updatePatient(patientId: number, input: Partial<PatientInput>): Promise<Patient> {
    return request<Patient>(`/patients/${patientId}/`, {
      method: 'PATCH',
      body: input,
    })
  },

  patientSessions(patientId: number): Promise<Session[]> {
    return request<Session[]>(`/patients/${patientId}/sessions/`)
  },

  // -- devices -------------------------------------------------------------
  devices(): Promise<Device[]> {
    return request<Device[]>('/devices/')
  },

  createDevice(name: string): Promise<Device & { device_token: string }> {
    return request<Device & { device_token: string }>('/devices/', {
      method: 'POST',
      body: { name },
    })
  },

  rotateDeviceToken(deviceId: string): Promise<{ device_token: string }> {
    return request<{ device_token: string }>(
      `/devices/${encodeURIComponent(deviceId)}/rotate-token/`,
      { method: 'POST' },
    )
  },

  assignDevicePatient(deviceId: string, patientId: number | null): Promise<Device> {
    return request<Device>(
      `/devices/${encodeURIComponent(deviceId)}/assign-patient/`,
      { method: 'POST', body: { patient: patientId } },
    )
  },

  setDeviceStatus(deviceId: string, status: 'active' | 'disabled'): Promise<Device> {
    return request<Device>(`/devices/${encodeURIComponent(deviceId)}/status/`, {
      method: 'POST',
      body: { status },
    })
  },

  // -- sessions ------------------------------------------------------------
  sessions(params: { patient?: number; status?: string; q?: string } = {}): Promise<Session[]> {
    const query = new URLSearchParams()
    if (params.patient !== undefined) query.set('patient', String(params.patient))
    if (params.status) query.set('status', params.status)
    if (params.q) query.set('q', params.q)
    const suffix = query.toString() ? `?${query.toString()}` : ''
    return request<Session[]>(`/sessions/${suffix}`)
  },

  session(sessionId: string): Promise<Session> {
    return request<Session>(`/sessions/${encodeURIComponent(sessionId)}/`)
  },

  startSession(patientId: number, deviceId: string): Promise<Session> {
    return request<Session>('/sessions/', {
      method: 'POST',
      body: { patient: patientId, device: deviceId },
    })
  },

  stopSession(sessionId: string): Promise<Session> {
    return request<Session>(`/sessions/${encodeURIComponent(sessionId)}/stop/`, {
      method: 'POST',
    })
  },

  analyze(sessionId: string): Promise<{
    status: string
    result: AnalysisResult
    error: string
  }> {
    return request(`/sessions/${encodeURIComponent(sessionId)}/analyze/`, {
      method: 'POST',
    })
  },

  analysis(sessionId: string): Promise<{
    status: string
    result: AnalysisResult
    error: string
  }> {
    return request(`/sessions/${encodeURIComponent(sessionId)}/analysis/`)
  },

  // -- reports -------------------------------------------------------------
  generateReport(sessionId: string, regenerate = false): Promise<ReportMeta> {
    return request<ReportMeta>(`/sessions/${encodeURIComponent(sessionId)}/report/`, {
      method: 'POST',
      body: { regenerate },
    })
  },

  latestReport(sessionId: string): Promise<ReportMeta> {
    return request<ReportMeta>(`/sessions/${encodeURIComponent(sessionId)}/report/`)
  },

  reports(sessionId: string): Promise<ReportMeta[]> {
    return request<ReportMeta[]>(`/sessions/${encodeURIComponent(sessionId)}/reports/`)
  },

  async downloadReport(report: ReportMeta): Promise<void> {
    const blob = await requestBlob(`/reports/${report.id}/download/`)
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${report.report_id}-${report.patient_code}.pdf`
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 10_000)
  },
}

// --- FastAPI endpoints -----------------------------------------------------

export const telemetry = {
  health(): Promise<Health> {
    return request<Health>('/health', { auth: false, base: 'telemetry' })
  },

  status(deviceId?: string): Promise<StatusResponse> {
    const query = deviceId ? `?device_id=${encodeURIComponent(deviceId)}` : ''
    return request<StatusResponse>(`/sensor/status${query}`, { base: 'telemetry' })
  },

  readings(sessionId: string, limit = 200): Promise<ReadingsResponse> {
    return request<ReadingsResponse>(
      `/sessions/${encodeURIComponent(sessionId)}/readings?limit=${limit}`,
      { base: 'telemetry' },
    )
  },

  chunkIndex(sessionId: string): Promise<EcgChunkList> {
    return request<EcgChunkList>(
      `/sessions/${encodeURIComponent(sessionId)}/ecg`,
      { base: 'telemetry' },
    )
  },

  chunk(sessionId: string, chunkIndex: number): Promise<EcgChunk> {
    return request<EcgChunk>(
      `/sessions/${encodeURIComponent(sessionId)}/ecg/${chunkIndex}`,
      { base: 'telemetry' },
    )
  },

  liveAnalysis(sessionId: string): Promise<AnalysisResult> {
    return request<AnalysisResult>(
      `/sessions/${encodeURIComponent(sessionId)}/analysis/live`,
      { base: 'telemetry' },
    )
  },
}

/**
 * The socket's token is a query parameter because browsers cannot set headers
 * on a WebSocket handshake.
 */
export function sensorSocketUrl(sessionId: string): string {
  const token = getAccessToken()
  if (!token) throw new ApiError('You are not signed in.', { code: 'unauthorized' })

  const explicit = import.meta.env.VITE_TELEMETRY_WS_URL as string | undefined
  let root: string
  if (explicit) {
    root = explicit.replace(/\/$/, '')
  } else if (telemetryBase().startsWith('http')) {
    root = telemetryBase().replace(/^http/, 'ws')
  } else {
    const scheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    root = `${scheme}//${window.location.host}${telemetryBase()}`
  }

  return `${root}/ws/sensor?session_id=${encodeURIComponent(
    sessionId,
  )}&token=${encodeURIComponent(token)}`
}

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}
