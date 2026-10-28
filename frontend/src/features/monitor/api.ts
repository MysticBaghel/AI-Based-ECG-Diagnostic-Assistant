import { ApiError, request } from '@/shared/api/http'
import { telemetryBase } from '@/shared/api/config'
import { getAccessToken } from '@/shared/api/tokenStore'
import type {
  AnalysisResult,
  EcgChunk,
  EcgChunkList,
  ReadingsResponse,
  StatusResponse,
} from '@/shared/types'

export const monitorApi = {
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
