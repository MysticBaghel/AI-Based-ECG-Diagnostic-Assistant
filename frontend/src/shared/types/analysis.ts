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

/** The 1-D CNN classification stored by the analysis API. */
export interface MLResult {
  available: boolean
  reason: string
  model_name: string | null
  model_version: string | null
  model_sha256: string | null
  architecture: string
  device: string | null
  classes: string[]
  class_labels: Record<string, string>
  predicted_class: string | null
  predicted_label: string | null
  confidence: number | null
  probabilities: Record<string, number> | null
  window_count: number
  window_seconds: number
  signal_duration_seconds: number
  analyzed_at: string | null
}

export type AdviceRisk = 'low' | 'moderate' | 'high' | 'unknown'

/** The AI advisory (deterministic template now, external API later). */
export interface AdviceResult {
  available: boolean
  reason: string
  provider: string
  provider_model: string | null
  prompt_version: string
  generated_at: string | null
  case: string
  risk_level: AdviceRisk
  headline: string
  summary: string
  recommendations: string[]
  red_flags: string[]
  confidence_note: string
  disclaimer: string
  input: Record<string, unknown>
  latency_ms?: number | null
}

/**
 * Pre-CNN analysis payload. Kept optional so an analysis stored before the
 * integration still renders instead of crashing the page.
 */
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
  /** Always present from the current API; optional for legacy stored payloads. */
  ml?: MLResult
  advice?: AdviceResult
  ai?: AIResult
  findings: string[]
  limitations: string[]
}
