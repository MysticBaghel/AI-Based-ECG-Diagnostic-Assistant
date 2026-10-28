import { formatDateTime } from '@/shared/lib/format'
import type { AnalysisResult } from '@/shared/types'

export function ModelInfoCard({ analysis }: { analysis: AnalysisResult | null }) {
  const ai = analysis?.ai
  return (
    <section className="analysis-box">
      <h3>Model Information</h3>
      <div className="analysis-box__body">
        <div className="model-list">
          <div>
            <span>Model Version</span>
            <strong>{ai?.model_version ?? 'Not configured'}</strong>
          </div>
          <div>
            <span>Analysis Time</span>
            <strong>{analysis ? formatDateTime(analysis.analyzed_at) : '—'}</strong>
          </div>
          <div>
            <span>Status</span>
            <strong>{analysis ? analysis.status : 'Not run'}</strong>
          </div>
          <div>
            <span>Analysis Version</span>
            <strong>{analysis ? `v${analysis.analysis_version}` : '—'}</strong>
          </div>
        </div>
      </div>
    </section>
  )
}
