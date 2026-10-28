import { Icon } from '@/shared/icons/Icon'
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
  const ai = analysis?.ai
  const tone = quality && !quality.usable ? 'warn' : 'ok'
  const title = analysis
    ? quality && !quality.usable
      ? 'Signal quality is insufficient'
      : ai?.available
        ? `AI screening result: ${ai.predicted_class ?? 'available'}`
        : 'Signal measurements available'
    : 'Analysis has not run'
  const text = !analysis
    ? 'Run the analysis after stopping the recording to produce measured parameters and, if configured, an AI result.'
    : quality && !quality.usable
      ? quality.reasons.join(' ')
      : ai?.available
        ? 'The classifier output is experimental and must be interpreted by a qualified clinician.'
        : 'Deterministic DSP measurements are stored. AI classification is unavailable because no validated model is configured.'

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
        {!analysis && !active && (
          <button
            type="button"
            className="button button--primary button--block"
            style={{ marginTop: '0.6rem' }}
            onClick={onRun}
            disabled={busy}
          >
            {busy ? 'Analysing…' : 'Run Analysis'}
          </button>
        )}
      </div>
    </section>
  )
}
