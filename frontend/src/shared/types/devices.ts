export type DeviceState = 'active' | 'disabled'

export interface Device {
  id: string
  name: string
  owner: number
  owner_username: string
  status: DeviceState
  assigned_patient: number | null
  assigned_patient_name: string | null
  assigned_patient_code: string | null
  created_at: string
}
