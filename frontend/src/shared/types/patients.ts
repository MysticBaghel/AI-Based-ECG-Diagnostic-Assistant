export type Sex = 'unknown' | 'female' | 'male' | 'other'

export interface Patient {
  id: number
  patient_id: string
  full_name: string
  phone: string
  email: string
  date_of_birth: string | null
  age: number | null
  age_years: number | null
  sex: Sex
  notes: string
  session_count: number
  created_at: string
  updated_at: string
}

export interface PatientInput {
  full_name: string
  phone?: string
  email?: string
  date_of_birth?: string | null
  age_years?: number | null
  sex?: Sex
  notes?: string
}
