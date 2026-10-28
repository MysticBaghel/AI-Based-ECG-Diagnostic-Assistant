import { useResource, type Resource } from '@/shared/api/useResource'
import type { Device, StatusResponse } from '@/shared/types'
import { devicesApi } from '../api'
import { monitorApi } from '@/features/monitor/api'

export function useDevices(enabled = true): Resource<Device[]> {
  return useResource('devices', () => devicesApi.list(), { enabled, pollMs: 30_000 })
}

export function useDeviceStatus(enabled = true): Resource<StatusResponse> {
  return useResource('device-status', () => monitorApi.status(), { enabled, pollMs: 15_000 })
}

export function statusFor(
  status: StatusResponse | null,
  deviceId: string,
): StatusResponse['devices'][number] | null {
  return status?.devices.find((device) => device.device_id === deviceId) ?? null
}
