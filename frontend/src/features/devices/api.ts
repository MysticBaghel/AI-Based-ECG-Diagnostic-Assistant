import { request } from '@/shared/api/http'
import type { Device } from '@/shared/types'

export const devicesApi = {
  list(): Promise<Device[]> {
    return request<Device[]>('/devices/')
  },

  create(name: string): Promise<Device & { device_token: string }> {
    return request<Device & { device_token: string }>('/devices/', {
      method: 'POST',
      body: { name },
    })
  },

  rotateToken(deviceId: string): Promise<{ device_token: string }> {
    return request<{ device_token: string }>(
      `/devices/${encodeURIComponent(deviceId)}/rotate-token/`,
      { method: 'POST' },
    )
  },

  assignPatient(deviceId: string, patientId: number | null): Promise<Device> {
    return request<Device>(
      `/devices/${encodeURIComponent(deviceId)}/assign-patient/`,
      { method: 'POST', body: { patient: patientId } },
    )
  },

  setStatus(deviceId: string, status: 'active' | 'disabled'): Promise<Device> {
    return request<Device>(`/devices/${encodeURIComponent(deviceId)}/status/`, {
      method: 'POST',
      body: { status },
    })
  },
}
