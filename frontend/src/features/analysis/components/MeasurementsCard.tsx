import { Icon } from '@/shared/icons/Icon'
import type { AnalysisResult } from '@/shared/types'

export function MeasurementsCard({ analysis }: { analysis: AnalysisResult | null }) {
  const measurements = analysis?.measurements
  const quality = analysis?.signal.quality

  return (
    <section className="analysis-box">
      <h3>Measured Parameters</h3>
      <div className="analysis-box__body">
        <div className="mini-metrics">
          <div className="mini-metric">
            <Icon name="heart" size={14} />
            Heart Rate
            <strong>
              {measurements?.heart_rate_bpm != null
                ? `${measurements.heart_rate_bpm.toFixed(0)} bpm`
                : '—'}
            </strong>
          </div>
          <div className="mini-metric">
            <Icon name="clock" size={14} />
            RR Interval
            <strong>
              {measurements?.rr_mean_ms != null
                ? `${(measurements.rr_mean_ms / 1000).toFixed(2)} s`
                : '—'}
            </strong>
          </div>
          <div className="mini-metric">
            <Icon name="activity" size={14} />
            Signal Quality
            <strong>
              {quality
                ? `${quality.level.charAt(0).toUpperCase() + quality.level.slice(1)}${quality.score != null ? ` · ${quality.score.toFixed(0)}` : ''}`
                : '—'}
            </strong>
          </div>
          <div className="mini-metric">
            <Icon name="sessions" size={14} />
            Beats
            <strong>{measurements?.beats_detected ?? '—'}</strong>
          </div>
        </div>
      </div>
    </section>
  )
}
