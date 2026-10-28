/** Shared API types for the Django business API and the FastAPI telemetry API. */

export type Role = 'operator' | 'admin'

export interface User {
  id: number
  username: string
  role: Role
  is_staff: boolean
}

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

export type SessionState = 'active' | 'completed' | 'aborted'
export type AnalysisState =
  | 'not_run'
  | 'pending'
  | 'completed'
  | 'unusable'
  | 'failed'
  | 'unavailable'

export interface SignalQuality {
  score: number | null
  level: string
  usable: boolean
  reasons: string[]
  flatline: boolean
  clipping: boolean
  missing_samples: number
}

export interface AnalysisSignal {
  sample_rate_hz: number | null
  sample_count: number
  duration_seconds: number
  chunks: number
  quality: SignalQuality
  filtering_note: string
}

export interface AnalysisMeasurements {
  heart_rate_bpm: number | null
  rr_intervals_ms: number[]
  rr_mean_ms: number | null
  rr_std_ms: number | null
  rmssd_ms: number | null
  pnn50_percent: number | null
  beats_detected: number
  r_peak_seconds: number[]
}

export interface AIResult {
  available: boolean
  reason: string
  model_name: string | null
  model_version: string | null
  classes: string[]
  predicted_class: string | null
  probabilities: Record<string, number> | null
  analyzed_at: string | null
}

export interface AnalysisResult {
  session_id: string
  analysis_version: number
  status: 'completed' | 'unusable' | 'failed'
  analyzed_at: string
  signal: AnalysisSignal
  measurements: AnalysisMeasurements
  ai: AIResult
  findings: string[]
  limitations: string[]
}

export interface SessionAnalysis {
  status: Exclude<AnalysisState, 'not_run'>
  result: AnalysisResult | Record<string, never>
  model_version: string
  analyzed_at: string | null
  error: string
  updated_at: string
}

export interface Session {
  id: string
  patient: number
  patient_name: string
  patient_code: string
  device: string
  device_name: string
  started_by: number | null
  start_time: string
  end_time: string | null
  duration_seconds: number
  status: SessionState
  sample_rate_hz: number | null
  notes: string
  analysis: SessionAnalysis | null
  analysis_status: AnalysisState
  report_count: number
  latest_report_id: string | null
}

export interface ReportMeta {
  id: string
  report_id: string
  session_id: string
  patient: number
  patient_name: string
  patient_code: string
  version: number
  file_size: number
  checksum: string
  generated_at: string
  generated_by: number | null
  download_url: string
  analysis_status: string
}

/** The four scalar sensor names the ingestion contract accepts. */
export type SensorType = 'temperature' | 'spo2' | 'pulse' | 'motion'

export interface Reading {
  reading_id: string
  sensor_type: SensorType
  value: number
  unit: string
  recorded_at: string
}

export interface ReadingsResponse {
  session_id: string
  count: number
  readings: Reading[]
}

export interface DeviceStatus {
  device_id: string
  owner_id: number | null
  last_seen: string | null
  seconds_since_seen: number | null
  online: boolean
  revoked: boolean
}

export interface StatusResponse {
  threshold_seconds: number
  devices: DeviceStatus[]
}

export interface EcgChunkSummary {
  chunk_id: string
  chunk_index: number
  sample_rate_hz: number
  sample_count: number
  start_time: string
  duration_seconds: number
}

export interface EcgChunkList {
  session_id: string
  count: number
  chunks: EcgChunkSummary[]
}

export interface EcgChunk extends EcgChunkSummary {
  session_id: string
  device_id: string
  samples: number[]
}

/** Frames pushed by `WS /ws/sensor` (docs/api-contract.md section 6). */
export type SocketFrame =
  | { event: 'snapshot'; session_id: string; readings: Reading[] }
  | {
      event: 'reading'
      session_id: string
      sensor_type: SensorType
      value: number
      unit: string
      recorded_at: string
    }
  | {
      event: 'ecg_chunk'
      session_id: string
      chunk_index: number
      sample_count: number
      sample_rate_hz: number
      start_time: string
    }
  | { event: 'error'; error: { code: string; message: string } }
  | { event: 'pong' }

export interface TokenPair {
  access: string
  refresh: string
}

export interface Health {
  status: string
  service: string
  analysis?: {
    dsp: string
    inference_available: boolean
    model_name: string | null
    model_version: string | null
    inference_reason: string
  }
}
