import { request } from '@/shared/api/http'
import type { Patient, PatientInput, Session } from '@/shared/types'

export const patientsApi = {
  list(query = ''): Promise<Patient[]> {
    const suffix = query.trim() ? `?q=${encodeURIComponent(query.trim())}` : ''
    return request<Patient[]>(`/patients/${suffix}`)
  },

  get(patientId: number): Promise<Patient> {
    return request<Patient>(`/patients/${patientId}/`)
  },

  create(input: PatientInput, confirmDuplicate = false): Promise<Patient> {
    return request<Patient>('/patients/', {
      method: 'POST',
      body: { ...input, confirm_duplicate: confirmDuplicate },
    })
  },

  update(patientId: number, input: Partial<PatientInput>): Promise<Patient> {
    return request<Patient>(`/patients/${patientId}/`, {
      method: 'PATCH',
      body: input,
    })
  },

  sessions(patientId: number): Promise<Session[]> {
    return request<Session[]>(`/patients/${patientId}/sessions/`)
  },
}
