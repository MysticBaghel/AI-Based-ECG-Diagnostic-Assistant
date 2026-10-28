import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { AnalysisResult } from '@/shared/types'
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
} satisfies Omit<AnalysisResult, 'ai'>

describe('AIResultsCard', () => {
  it('states unavailability instead of inventing a prediction', () => {
    render(
      <AIResultsCard
        analysis={{
          ...base,
          ai: {
            available: false,
            reason: 'No model configured.',
            model_name: null,
            model_version: null,
            classes: [],
            predicted_class: null,
            probabilities: null,
            analyzed_at: null,
          },
        }}
      />,
    )

    expect(screen.getByText(/AI analysis unavailable/i)).toBeInTheDocument()
    expect(screen.getByText(/No model configured/i)).toBeInTheDocument()
    expect(screen.queryByText(/%/)).not.toBeInTheDocument()
  })

  it('renders real probabilities when available', () => {
    render(
      <AIResultsCard
        analysis={{
          ...base,
          ai: {
            available: true,
            reason: '',
            model_name: 'demo',
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
