import { Icon } from '@/shared/icons/Icon'
import { getMLResult } from '@/shared/lib/analysis'
import type { AnalysisResult } from '@/shared/types'

export function AnalysisSummaryCard({
  analysis,
  active,
  busy,
  onRun,
}: {
  analysis: AnalysisResult | null
  active: boolean
  busy: boolean
  onRun: () => void
}) {
  const quality = analysis?.signal.quality
  const ml = getMLResult(analysis)
  const advice = analysis?.advice
  const tone = quality && !quality.usable ? 'warn' : 'ok'
  const title = analysis
    ? quality && !quality.usable
      ? 'Signal quality is insufficient'
      : ml?.available
        ? `ML screening result: ${ml.predicted_label ?? ml.predicted_class ?? 'available'}`
        : 'Signal measurements available'
    : 'Analysis has not run'
  const text = !analysis
    ? 'Run the analysis after stopping the recording to produce measured parameters, a CNN classification and, if configured, AI advice.'
    : quality && !quality.usable
      ? quality.reasons.join(' ')
      : advice?.available
        ? `${advice.headline} ${advice.confidence_note}`.trim()
        : ml?.available
          ? 'The 1-D CNN output is experimental and must be interpreted by a qualified clinician.'
          : 'Deterministic DSP measurements are stored. ML classification is unavailable because no trained model is configured.'

  return (
    <section className="analysis-box">
      <h3>Analysis Summary</h3>
      <div className="analysis-box__body">
        <div className={`analysis-summary${tone === 'warn' ? ' analysis-summary--warn' : ''}`}>
          <Icon name={tone === 'warn' ? 'alert' : 'check'} size={17} />
          <div>
            <strong>{title}</strong>
            <span>{text}</span>
          </div>
        </div>
        {!active && (
          <button
            type="button"
            className="button button--primary button--block"
            style={{ marginTop: '0.6rem' }}
            onClick={onRun}
            disabled={busy}
          >
            {busy ? 'Analysing…' : analysis ? 'Re-run Analysis' : 'Run Analysis'}
          </button>
        )}
      </div>
    </section>
  )
}
