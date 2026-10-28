import { useResource, type Resource } from '@/shared/api/useResource'
import type { Patient } from '@/shared/types'
import { patientsApi } from '../api'

export function usePatients(query = '', enabled = true): Resource<Patient[]> {
  return useResource(`patients:${query}`, () => patientsApi.list(query), {
    enabled,
    pollMs: query ? undefined : 60_000,
  })
}

export function usePatient(patientId: number | undefined): Resource<Patient> {
  return useResource(`patient:${patientId ?? ''}`, () => patientsApi.get(patientId ?? 0), {
    enabled: Boolean(patientId),
    pollMs: 60_000,
  })
}
