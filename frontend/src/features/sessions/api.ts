import { request } from '@/shared/api/http'
import type { Session } from '@/shared/types'

export interface SessionFilters {
  patient?: number
  status?: string
  q?: string
}

export const sessionsApi = {
  list(params: SessionFilters = {}): Promise<Session[]> {
    const query = new URLSearchParams()
    if (params.patient !== undefined) query.set('patient', String(params.patient))
    if (params.status) query.set('status', params.status)
    if (params.q) query.set('q', params.q)
    const suffix = query.toString() ? `?${query.toString()}` : ''
    return request<Session[]>(`/sessions/${suffix}`)
  },

  get(sessionId: string): Promise<Session> {
    return request<Session>(`/sessions/${encodeURIComponent(sessionId)}/`)
  },

  start(patientId: number, deviceId: string): Promise<Session> {
    return request<Session>('/sessions/', {
      method: 'POST',
      body: { patient: patientId, device: deviceId },
    })
  },

  stop(sessionId: string): Promise<Session> {
    return request<Session>(`/sessions/${encodeURIComponent(sessionId)}/stop/`, {
      method: 'POST',
    })
  },
}
