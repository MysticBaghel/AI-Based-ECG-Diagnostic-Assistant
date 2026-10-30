import { formatDateTime } from '@/shared/lib/format'
import { getMLResult } from '@/shared/lib/analysis'
import type { AnalysisResult } from '@/shared/types'

export function ModelInfoCard({ analysis }: { analysis: AnalysisResult | null }) {
  const ml = getMLResult(analysis)
  const advice = analysis?.advice
  return (
    <section className="analysis-box">
      <h3>Model Information</h3>
      <div className="analysis-box__body">
        <div className="model-list">
          <div>
            <span>Classifier</span>
            <strong>{ml?.architecture ?? 'Not configured'}</strong>
          </div>
          <div>
            <span>Model Version</span>
            <strong>{ml?.model_version ?? 'Not configured'}</strong>
          </div>
          <div>
            <span>Model Device</span>
            <strong>{ml?.device ?? '—'}</strong>
          </div>
          <div>
            <span>Advisor</span>
            <strong>{advice?.provider ?? '—'}</strong>
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
          {ml?.model_sha256 && (
            <div>
              <span>Model Checksum</span>
              <strong title={ml.model_sha256}>{ml.model_sha256.slice(0, 16)}…</strong>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}
