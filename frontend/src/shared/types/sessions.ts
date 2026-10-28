import type { AnalysisResult, AnalysisState } from './analysis'

export type SessionState = 'active' | 'completed' | 'aborted'

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
