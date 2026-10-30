import { getMLResult } from '@/shared/lib/analysis'
import { formatDateTime } from '@/shared/lib/format'
import type { AdviceRisk, AnalysisResult } from '@/shared/types'

const RISK_LABEL: Record<AdviceRisk, string> = {
  low: 'Low concern',
  moderate: 'Clinical review',
  high: 'Urgent review',
  unknown: 'Not determined',
}

export function AIResultsCard({ analysis }: { analysis: AnalysisResult | null }) {
  const ml = getMLResult(analysis)
  const advice = analysis?.advice
  const recommendations = advice?.recommendations ?? []
  const redFlags = advice?.red_flags ?? []
  const probabilities = Object.entries(ml?.probabilities ?? {}).sort((a, b) => b[1] - a[1])

  return (
    <section className="analysis-box">
      <h3>AI Analysis &amp; Advice</h3>
      <div className="analysis-box__body">
        {advice?.available ? (
          <div className={`ai-advice ai-advice--${advice.risk_level}`}>
            <div className="ai-advice__head">
              <span className={`ai-risk ai-risk--${advice.risk_level}`}>
                {RISK_LABEL[advice.risk_level] ?? RISK_LABEL.unknown}
              </span>
              <strong>{advice.headline}</strong>
            </div>
            <p className="ai-advice__summary">{advice.summary}</p>

            {recommendations.length > 0 && (
              <>
                <span className="ai-advice__label">Cautious next steps</span>
                <ul className="ai-advice__list">
                  {recommendations.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </>
            )}

            {redFlags.length > 0 && (
              <div className="ai-advice__flags">
                <span className="ai-advice__label">Seek urgent care for</span>
                <ul className="ai-advice__list">
                  {redFlags.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            )}

            {advice.confidence_note && (
              <p className="ai-advice__note">{advice.confidence_note}</p>
            )}
            <p className="ai-advice__meta">
              {advice.provider} · prompt {advice.prompt_version} ·{' '}
              {formatDateTime(advice.generated_at)}
            </p>
          </div>
        ) : (
          <div className="ai-unavailable">
            <strong>AI advice unavailable.</strong>{' '}
            {advice?.reason || 'No advisory provider produced a response for this recording.'}
          </div>
        )}

        <div className="ai-ml">
          <div className="ai-ml__head">
            <span className="ai-ml__title">Classifier detail</span>
            {ml?.available && (
              <span className="ai-ml__badge">
                {ml.predicted_class}
                {ml.predicted_label ? ` · ${ml.predicted_label}` : ''}
              </span>
            )}
          </div>

          {ml?.available ? (
            <>
              <div className="ai-probability">
                {probabilities.map(([code, probability]) => (
                  <div className="ai-probability__row" key={code}>
                    <span
                      className="ai-probability__label"
                      title={ml.class_labels[code] ?? code}
                    >
                      {code}
                    </span>
                    <span className="ai-probability__track">
                      <span
                        className="ai-probability__fill"
                        style={{ width: `${Math.max(0, Math.min(100, probability * 100))}%` }}
                      />
                    </span>
                    <span className="ai-probability__value">
                      {(probability * 100).toFixed(0)}%
                    </span>
                  </div>
                ))}
              </div>
              <p className="ai-ml__meta">
                {ml.predicted_label ?? 'Classified'} ·{' '}
                {ml.confidence !== null ? `${(ml.confidence * 100).toFixed(0)}% confidence` : 'confidence n/a'} ·{' '}
                {ml.window_count} window{ml.window_count === 1 ? '' : 's'} ·{' '}
                {ml.model_name ?? ml.architecture}
                {ml.model_version ? ` v${ml.model_version}` : ''} ·{' '}
                {formatDateTime(ml.analyzed_at)}
              </p>
            </>
          ) : (
            <div className="ai-unavailable">
              <strong>ML classification unavailable.</strong>{' '}
              {ml?.reason || 'No trained ECG classification model is configured.'} No class or
              probability has been fabricated.
            </div>
          )}
        </div>

        <p className="ai-card__disclaimer">
          {advice?.disclaimer ||
            'Automated screening aid, not a medical diagnosis. A qualified clinician must interpret the recording.'}
        </p>
      </div>
    </section>
  )
}
