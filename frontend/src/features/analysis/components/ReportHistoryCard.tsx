import { Icon } from '@/shared/icons/Icon'
import { Spinner } from '@/shared/ui'
import { formatDateTime } from '@/shared/lib/format'
import type { ReportMeta } from '@/shared/types'

export function ReportHistoryCard({
  reports,
  loading,
  onDownload,
}: {
  reports: ReportMeta[]
  loading: boolean
  onDownload: (report: ReportMeta) => void
}) {
  return (
    <section className="panel">
      <div className="panel__header">
        <div>
          <h2>Report history</h2>
          <p>Every PDF is stored with the analysis snapshot it was generated from</p>
        </div>
      </div>
      <div className="panel__body">
        {loading ? (
          <Spinner label="Loading reports…" />
        ) : reports.length === 0 ? (
          <p className="muted small">
            No report has been generated for this session. Use “Download PDF” above to generate
            the first version.
          </p>
        ) : (
          <div className="report-history">
            {reports.map((report) => (
              <div className="report-history__row" key={report.id}>
                <div>
                  <strong>{report.report_id}</strong>{' '}
                  <span className="muted small">
                    v{report.version} · {formatDateTime(report.generated_at)} ·{' '}
                    {(report.file_size / 1024).toFixed(0)} KB
                  </span>
                </div>
                <button
                  type="button"
                  className="button button--ghost button--sm"
                  onClick={() => onDownload(report)}
                >
                  <Icon name="download" size={14} />
                  Download
                </button>
              </div>
            ))}
          </div>
        )}
        <p className="muted small" style={{ marginTop: '0.6rem' }}>
          Measurements are deterministic DSP output; AI output is shown only when a validated
          model produced it. A missing AI result is stated, never invented.
        </p>
      </div>
    </section>
  )
}
