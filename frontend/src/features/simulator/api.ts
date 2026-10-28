import { telemetryBase } from '@/shared/api/config'
import { ApiError, request } from '@/shared/api/http'
import { getAccessToken } from '@/shared/api/tokenStore'
import type { ReplayStarted, SimulationStatus } from '@/shared/types'

/**
 * Upload a CSV to an active session and start replaying it.
 *
 * The body is the file itself, not JSON: the server parses it as CSV (see
 * `app/simulation/csv_source.py`). `fetch` is used directly because the shared
 * `request` helper serialises everything to JSON.
 */
export async function replayCsv(
  sessionId: string,
  file: File,
  rateHz: number,
): Promise<ReplayStarted> {
  const token = getAccessToken()
  if (!token) {
    throw new ApiError('You are not signed in.', { code: 'unauthorized', status: 401 })
  }

  const query = new URLSearchParams({ name: file.name, rate_hz: String(rateHz) })
  const url = `${telemetryBase()}/sessions/${encodeURIComponent(sessionId)}/replay?${query.toString()}`

  let response: Response
  try {
    response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'text/csv', Authorization: `Bearer ${token}` },
      body: file,
    })
  } catch {
    throw new ApiError('Could not reach the telemetry service. Is FastAPI running?')
  }

  if (!response.ok) {
    let body: { detail?: unknown; code?: string } = {}
    try {
      body = (await response.json()) as { detail?: unknown; code?: string }
    } catch {
      // The service can answer with an empty body; the status is still useful.
    }
    throw new ApiError(
      typeof body.detail === 'string' && body.detail
        ? body.detail
        : `Upload failed with HTTP ${response.status}.`,
      { status: response.status, code: body.code },
    )
  }

  return (await response.json()) as ReplayStarted
}

export interface ScenarioInfo {
  key: string
  label: string
  description: string
  heart_rate_bpm: number
}

/** The built-in teaching rhythms the server can generate. */
// `async` on purpose: a synchronous throw (an import or config error) then
// becomes a rejected promise the caller's `.catch` can handle, instead of
// escaping a render effect into the error boundary.
export async function simulationScenarios(): Promise<ScenarioInfo[]> {
  return request<ScenarioInfo[]>('/simulator/scenarios', { base: 'telemetry' })
}

/** Stream a generated scenario into an active session. */
export function startScenario(
  sessionId: string,
  scenario: string,
  durationSeconds: number,
): Promise<SimulationStatus> {
  return request<SimulationStatus>(
    `/sessions/${encodeURIComponent(sessionId)}/simulation`,
    {
      method: 'POST',
      base: 'telemetry',
      body: { scenario, duration_seconds: durationSeconds },
    },
  )
}
