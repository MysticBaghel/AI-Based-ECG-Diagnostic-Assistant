import clsx from 'clsx'

import type { AnalysisResult } from '@/shared/types'
import { Icon } from '@/shared/icons/Icon'
import { formatDuration } from '@/shared/lib/format'

function MonitorMetric({
  icon,
  label,
  value,
  foot,
  pill,
  note,
}: {
  icon: 'heart' | 'activity' | 'clock' | 'sessions'
  label: string
  value: string
  foot?: string
  pill?: { text: string; tone?: 'ok' | 'warn' | 'neutral' }
  note?: string
}) {
  return (
    <div className="metric-card">
      <span className="metric-card__head">
        <Icon name={icon} size={16} />
        {label}
      </span>
      <strong className="metric-card__value">{value}</strong>
      <span className="metric-card__foot">
        {pill && (
          <span
            className={clsx('metric-card__pill', {
              'metric-card__pill--warn': pill.tone === 'warn',
              'metric-card__pill--neutral': pill.tone === 'neutral',
            })}
          >
            {pill.text}
          </span>
        )}
        {(foot || note) && <span className="metric-card__note">{foot ?? note}</span>}
      </span>
    </div>
  )
}

export function MonitorMetrics({
  analysis,
  active,
  elapsed,
}: {
  analysis: AnalysisResult | null
  active: boolean
  elapsed: number
}) {
  const hasSignal = (analysis?.signal.sample_count ?? 0) > 0
  const quality = hasSignal ? analysis?.signal.quality : undefined
  const heartRate = hasSignal ? analysis?.measurements.heart_rate_bpm ?? null : null
  const rrSeconds =
    hasSignal && analysis?.measurements.rr_mean_ms != null
      ? analysis.measurements.rr_mean_ms / 1000
      : null

  const hrPill =
    heartRate == null
      ? { text: 'Waiting', tone: 'neutral' as const }
      : heartRate < 60 || heartRate > 100
        ? { text: 'Outside 60–100', tone: 'warn' as const }
        : { text: 'Normal (60–100)', tone: 'ok' as const }

  return (
    <div className="metric-cards">
      <MonitorMetric
        icon="heart"
        label="Heart Rate"
        value={heartRate == null ? '—' : `${heartRate.toFixed(0)} bpm`}
        pill={hrPill}
      />
      <MonitorMetric
        icon="activity"
        label="Signal Quality"
        value={quality ? quality.level.charAt(0).toUpperCase() + quality.level.slice(1) : '—'}
        pill={{
          text: quality ? (quality.usable ? 'Stable' : 'Unusable') : 'Waiting',
          tone: quality ? (quality.usable ? 'ok' : 'warn') : 'neutral',
        }}
        foot={quality?.score != null ? `${quality.score.toFixed(0)} / 100` : undefined}
      />
      <MonitorMetric
        icon="clock"
        label="RR Interval"
        value={rrSeconds == null ? '—' : `${rrSeconds.toFixed(2)} s`}
        note="from the measured mean RR"
      />
      <MonitorMetric
        icon="sessions"
        label="Recording Duration"
        value={formatDuration(elapsed)}
        foot={active ? 'Recording' : 'Completed'}
      />
    </div>
  )
}
