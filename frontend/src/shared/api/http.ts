import type { Patient } from '@/shared/types'

import { API_BASE, telemetryBase, type ApiBase } from './config'
import {
  AUTH_EXPIRED_EVENT,
  clearTokens,
  getAccessToken,
  getRefreshToken,
  isPersistent,
} from './tokenStore'

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: unknown
  auth?: boolean
  base?: ApiBase
  signal?: AbortSignal
}

export interface ErrorBody {
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

async function toApiError(response: Response, base: ApiBase): Promise<ApiError> {
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
        const storage = isPersistent() ? localStorage : sessionStorage
        storage.setItem('ecg.access', data.access)
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

async function authorizedFetch(
  path: string,
  options: RequestOptions = {},
): Promise<Response> {
  const base: ApiBase = options.base ?? 'django'
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

export async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const response = await authorizedFetch(path, options)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export async function requestBlob(
  path: string,
  options: RequestOptions = {},
): Promise<Blob> {
  const response = await authorizedFetch(path, options)
  return response.blob()
}

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}
