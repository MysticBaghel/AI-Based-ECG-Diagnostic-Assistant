import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { AdviceResult, AnalysisResult, MLResult } from '@/shared/types'
import { AIResultsCard } from './AIResultsCard'

const base = {
  session_id: 's',
  analysis_version: 1,
  status: 'completed',
  analyzed_at: '2026-10-28T10:00:00Z',
  signal: {
    sample_rate_hz: 200,
    sample_count: 100,
    duration_seconds: 10,
    chunks: 1,
    quality: {
      score: 80,
      level: 'good',
      usable: true,
      reasons: [],
      flatline: false,
      clipping: false,
      missing_samples: 0,
    },
    filtering_note: '',
  },
  measurements: {
    heart_rate_bpm: 72,
    rr_intervals_ms: [],
    rr_mean_ms: 833,
    rr_std_ms: 0,
    rmssd_ms: 0,
    pnn50_percent: 0,
    beats_detected: 2,
    r_peak_seconds: [],
  },
  findings: [],
  limitations: [],
} satisfies Omit<AnalysisResult, 'ml' | 'advice' | 'ai'>

const unavailableMl: MLResult = {
  available: false,
  reason: 'No trained ECG model is configured.',
  model_name: null,
  model_version: null,
  model_sha256: null,
  architecture: 'ECGNet-1DCNN',
  device: null,
  classes: [],
  class_labels: {},
  predicted_class: null,
  predicted_label: null,
  confidence: null,
  probabilities: null,
  window_count: 0,
  window_seconds: 0,
  signal_duration_seconds: 0,
  analyzed_at: null,
}

const unavailableAdvice: AdviceResult = {
  available: false,
  reason: 'No advisory provider produced a response.',
  provider: 'template',
  provider_model: null,
  prompt_version: 'ecg-advisor-v1',
  generated_at: null,
  case: 'unavailable',
  risk_level: 'unknown',
  headline: '',
  summary: '',
  recommendations: [],
  red_flags: [],
  confidence_note: '',
  disclaimer: 'Automated screening aid, not a medical diagnosis.',
  input: {},
}

const availableMl: MLResult = {
  ...unavailableMl,
  available: true,
  reason: '',
  model_name: 'demo-cnn',
  model_version: '0.1.0',
  model_sha256: 'abc123',
  device: 'cpu',
  classes: ['N', 'A', 'O', '~'],
  class_labels: {
    N: 'Normal rhythm',
    A: 'Atrial fibrillation pattern',
    O: 'Other rhythm',
    '~': 'Noisy / unreadable',
  },
  predicted_class: 'N',
  predicted_label: 'Normal rhythm',
  confidence: 0.82,
  probabilities: { N: 0.82, A: 0.1, O: 0.05, '~': 0.03 },
  window_count: 1,
  window_seconds: 30,
  signal_duration_seconds: 10,
  analyzed_at: '2026-10-28T10:00:00Z',
}

const availableAdvice: AdviceResult = {
  ...unavailableAdvice,
  available: true,
  reason: '',
  case: 'N',
  risk_level: 'low',
  headline: 'Normal rhythm pattern suggested',
  summary: 'The classifier found a predominantly normal rhythm pattern.',
  recommendations: ['Correlate this result with the patient symptoms.'],
  red_flags: ['Chest pain, pressure or tightness.'],
  confidence_note: 'Model confidence is not clinical certainty.',
  generated_at: '2026-10-28T10:00:00Z',
}

describe('AIResultsCard', () => {
  it('states unavailability instead of inventing a prediction', () => {
    render(
      <AIResultsCard
        analysis={{
          ...base,
          ml: unavailableMl,
          advice: unavailableAdvice,
        }}
      />,
    )

    expect(screen.getByText(/ML classification unavailable/i)).toBeInTheDocument()
    expect(screen.getByText(/No trained ECG model is configured/i)).toBeInTheDocument()
    expect(screen.getByText(/AI advice unavailable/i)).toBeInTheDocument()
    expect(screen.queryByText(/%/)).not.toBeInTheDocument()
  })

  it('renders the advisory and the real class probabilities when available', () => {
    render(
      <AIResultsCard
        analysis={{
          ...base,
          ml: availableMl,
          advice: availableAdvice,
        }}
      />,
    )

    expect(screen.getByText('Normal rhythm pattern suggested')).toBeInTheDocument()
    expect(screen.getByText(/predominantly normal rhythm pattern/i)).toBeInTheDocument()
    expect(
      screen.getByText(/Correlate this result with the patient symptoms/i),
    ).toBeInTheDocument()
    expect(screen.getByText(/Chest pain, pressure or tightness/i)).toBeInTheDocument()
    expect(screen.getByText('82%')).toBeInTheDocument()
    expect(screen.getByText('10%')).toBeInTheDocument()
    expect(screen.getByText(/demo-cnn v0\.1\.0/)).toBeInTheDocument()
  })

  it('still renders a pre-CNN analysis through the legacy ai block', () => {
    render(
      <AIResultsCard
        analysis={{
          ...base,
          ai: {
            available: true,
            reason: '',
            model_name: 'legacy',
            model_version: '1',
            classes: ['Normal', 'AFib'],
            predicted_class: 'Normal',
            probabilities: { Normal: 0.82, AFib: 0.18 },
            analyzed_at: '2026-10-28T10:00:00Z',
          },
        }}
      />,
    )

    expect(screen.getByText('82%')).toBeInTheDocument()
    expect(screen.getByText('18%')).toBeInTheDocument()
  })
})
