import type { AnalysisResult, MLResult } from '@/shared/types'

/**
 * Return the ML result for an analysis, including payloads stored before the
 * 1-D CNN integration (which used an `ai` block with fewer fields).
 */
export function getMLResult(analysis: AnalysisResult | null | undefined): MLResult | null {
  if (!analysis) return null
  if (analysis.ml) return analysis.ml
  const legacy = analysis.ai
  if (!legacy) return null
  return {
    available: legacy.available,
    reason: legacy.reason,
    model_name: legacy.model_name,
    model_version: legacy.model_version,
    model_sha256: null,
    architecture: 'legacy classifier',
    device: null,
    classes: legacy.classes,
    class_labels: Object.fromEntries(legacy.classes.map((code) => [code, code])),
    predicted_class: legacy.predicted_class,
    predicted_label: legacy.predicted_class,
    confidence: legacy.predicted_class
      ? (legacy.probabilities?.[legacy.predicted_class] ?? null)
      : null,
    probabilities: legacy.probabilities,
    window_count: 0,
    window_seconds: 0,
    signal_duration_seconds: 0,
    analyzed_at: legacy.analyzed_at,
  }
}
