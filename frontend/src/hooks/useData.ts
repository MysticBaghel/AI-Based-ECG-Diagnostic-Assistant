import { api, telemetry } from '../api/client'
import { useResource, type Resource } from './useResource'
import type {
  AnalysisResult,
  Device,
  EcgChunk,
  EcgChunkList,
  Patient,
  ReportMeta,
  Session,
  StatusResponse,
} from '../api/types'

export function usePatients(query = '', enabled = true): Resource<Patient[]> {
  return useResource(`patients:${query}`, () => api.patients(query), {
    enabled,
    pollMs: query ? undefined : 60_000,
  })
}

export function usePatient(patientId: number | undefined): Resource<Patient> {
  return useResource(
    `patient:${patientId ?? ''}`,
    () => api.patient(patientId ?? 0),
    { enabled: Boolean(patientId), pollMs: 60_000 },
  )
}

export function useDevices(enabled = true): Resource<Device[]> {
  return useResource('devices', () => api.devices(), { enabled, pollMs: 30_000 })
}

export function useSessions(
  params: { patient?: number; status?: string; q?: string } = {},
  enabled = true,
): Resource<Session[]> {
  const key = `sessions:${params.patient ?? 'all'}:${params.status ?? 'all'}:${params.q ?? ''}`
  return useResource(key, () => api.sessions(params), { enabled, pollMs: 15_000 })
}

export function useSession(sessionId: string | undefined): Resource<Session> {
  return useResource(
    `session:${sessionId ?? ''}`,
    () => api.session(sessionId ?? ''),
    { enabled: Boolean(sessionId), pollMs: 30_000 },
  )
}

export function useDeviceStatus(enabled = true): Resource<StatusResponse> {
  return useResource('device-status', () => telemetry.status(), {
    enabled,
    pollMs: 15_000,
  })
}

export function useAnalysis(
  sessionId: string | undefined,
  enabled = true,
): Resource<AnalysisResult> {
  return useResource(
    `analysis:${sessionId ?? ''}`,
    () => api.analysis(sessionId ?? '').then((record) => record.result),
    { enabled: Boolean(sessionId) && enabled, pollMs: 30_000 },
  )
}

export function useLatestReport(
  sessionId: string | undefined,
  enabled = true,
): Resource<ReportMeta> {
  return useResource(
    `report:${sessionId ?? ''}`,
    () => api.latestReport(sessionId ?? ''),
    { enabled: Boolean(sessionId) && enabled, pollMs: 30_000 },
  )
}

export function useReports(
  sessionId: string | undefined,
  enabled = true,
): Resource<ReportMeta[]> {
  return useResource(
    `reports:${sessionId ?? ''}`,
    () => api.reports(sessionId ?? ''),
    { enabled: Boolean(sessionId) && enabled, pollMs: 30_000 },
  )
}

export function useChunkIndex(
  sessionId: string | undefined,
  enabled = true,
): Resource<EcgChunkList> {
  return useResource(
    `chunks:${sessionId ?? ''}`,
    () => telemetry.chunkIndex(sessionId ?? ''),
    { enabled: Boolean(sessionId) && enabled, pollMs: 30_000 },
  )
}

export function useChunkWindow(
  sessionId: string | undefined,
  chunkIndexes: number[],
): Resource<EcgChunk[]> {
  const key = `chunk-window:${sessionId ?? ''}:${chunkIndexes.join(',')}`
  return useResource(
    key,
    () =>
      chunkIndexes.length === 0
        ? Promise.resolve([])
        : Promise.all(chunkIndexes.map((index) => telemetry.chunk(sessionId ?? '', index))),
    { enabled: Boolean(sessionId) && chunkIndexes.length > 0 },
  )
}

export function useLiveAnalysis(
  sessionId: string | undefined,
  enabled: boolean,
): Resource<AnalysisResult> {
  return useResource(
    `live-analysis:${sessionId ?? ''}`,
    () => telemetry.liveAnalysis(sessionId ?? ''),
    { enabled: Boolean(sessionId) && enabled, pollMs: 4_000 },
  )
}

export function statusFor(
  status: StatusResponse | null,
  deviceId: string,
): StatusResponse['devices'][number] | null {
  return status?.devices.find((device) => device.device_id === deviceId) ?? null
}
