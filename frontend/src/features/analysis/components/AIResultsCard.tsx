import type { AnalysisResult } from '@/shared/types'

export function AIResultsCard({ analysis }: { analysis: AnalysisResult | null }) {
  const ai = analysis?.ai
  return (
    <section className="analysis-box">
      <h3>AI Analysis Results</h3>
      <div className="analysis-box__body">
        {ai?.available ? (
          <div className="ai-probability">
            {Object.entries(ai.probabilities ?? {})
              .sort((a, b) => b[1] - a[1])
              .map(([label, probability]) => (
                <div className="ai-probability__row" key={label}>
                  <span>{label}</span>
                  <span className="ai-probability__track">
                    <span
                      className="ai-probability__fill"
                      style={{ width: `${Math.max(0, Math.min(100, probability * 100))}%` }}
                    />
                  </span>
                  <span className="ai-probability__value">{(probability * 100).toFixed(0)}%</span>
                </div>
              ))}
          </div>
        ) : (
          <div className="ai-unavailable">
            <strong>AI analysis unavailable.</strong>{' '}
            {ai?.reason || 'No validated classification model is configured.'} No prediction or
            probability has been fabricated.
          </div>
        )}
      </div>
    </section>
  )
}
