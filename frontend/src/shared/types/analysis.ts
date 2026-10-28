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
