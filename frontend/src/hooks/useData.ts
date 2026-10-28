import { api, telemetry } from '../api/client'
import { useResource, type Resource } from './useResource'
import type {
  Device,
  EcgChunk,
  EcgChunkList,
  Patient,
  ReadingsResponse,
  Session,
  StatusResponse,
} from '../api/types'

export function usePatients(enabled = true): Resource<Patient[]> {
  return useResource('patients', () => api.patients(), { enabled, pollMs: 60_000 })
}

export function useDevices(enabled = true): Resource<Device[]> {
  return useResource('devices', () => api.devices(), { enabled, pollMs: 30_000 })
}

export function useSessions(enabled = true): Resource<Session[]> {
  return useResource('sessions', () => api.sessions(), { enabled, pollMs: 15_000 })
}

export function useDeviceStatus(enabled = true): Resource<StatusResponse> {
  return useResource('device-status', () => telemetry.status(), {
    enabled,
    pollMs: 15_000,
  })
}

export function useSession(sessionId: string | undefined): Resource<Session> {
  return useResource(
    `session:${sessionId ?? ''}`,
    () => api.session(sessionId ?? ''),
    { enabled: Boolean(sessionId), pollMs: 30_000 },
  )
}

export function useReadings(
  sessionId: string | undefined,
  limit = 200,
): Resource<ReadingsResponse> {
  return useResource(
    `readings:${sessionId ?? ''}:${limit}`,
    () => telemetry.readings(sessionId ?? '', limit),
    { enabled: Boolean(sessionId), pollMs: 30_000 },
  )
}

export function useChunkIndex(
  sessionId: string | undefined,
): Resource<EcgChunkList> {
  return useResource(
    `chunks:${sessionId ?? ''}`,
    () => telemetry.chunkIndex(sessionId ?? ''),
    { enabled: Boolean(sessionId), pollMs: 30_000 },
  )
}

export function useChunk(
  sessionId: string | undefined,
  chunkIndex: number | null,
): Resource<EcgChunk> {
  return useResource(
    `chunk:${sessionId ?? ''}:${chunkIndex ?? 'none'}`,
    () => telemetry.chunk(sessionId ?? '', chunkIndex ?? 0),
    { enabled: Boolean(sessionId) && chunkIndex !== null },
  )
}

export function statusFor(
  status: StatusResponse | null,
  deviceId: string,
): StatusResponse['devices'][number] | null {
  return status?.devices.find((device) => device.device_id === deviceId) ?? null
}
