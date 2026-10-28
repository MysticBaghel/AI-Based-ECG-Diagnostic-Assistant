import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { ApiError } from '@/shared/api/http'
import { reportsApi } from '@/features/reports/api'
import type { ReportMeta } from '@/shared/types'
import { Icon } from '@/shared/icons/Icon'
import { EmptyState, ErrorBanner, PageHeader, Spinner, StatCard } from '@/shared/ui'
import { useResource } from '@/shared/api/useResource'
import { formatDateTime } from '@/shared/lib/format'

export function ReportsPage() {
  const navigate = useNavigate()
  const reports = useResource('all-reports', () => reportsApi.all(), { pollMs: 30_000 })
  const [query, setQuery] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [downloading, setDownloading] = useState<string | null>(null)

  const list = useMemo(() => reports.data ?? [], [reports.data])
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return list
    return list.filter((report) =>
      [report.report_id, report.patient_name, report.patient_code, report.session_id]
        .join(' ')
        .toLowerCase()
        .includes(needle),
    )
  }, [list, query])

  const patients = new Set(list.map((report) => report.patient)).size

  async function download(report: ReportMeta) {
    setDownloading(report.id)
    setError(null)
    try {
      await reportsApi.download(report)
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not download the report.')
    } finally {
      setDownloading(null)
    }
  }

  return (
    <>
      <PageHeader
        title="Reports"
        description="Generated ECG screening reports, stored with their original analysis"
        actions={
          <Link to="/patients" className="button button--primary">
            <Icon name="users" size={15} />
            Patients
          </Link>
        }
      />

      {(reports.error || error) && (
        <ErrorBanner
          message={reports.error ?? error ?? ''}
          onRetry={() => {
            reports.refresh()
            setError(null)
          }}
        />
      )}

      <div className="stats stats--three">
        <StatCard icon="file-text" label="Reports" value={list.length} hint="all versions" />
        <StatCard icon="users" label="Patients with reports" value={patients} hint="in the registry" />
        <StatCard
          icon="clock"
          label="Latest report"
          value={list[0] ? formatDateTime(list[0].generated_at) : '—'}
          hint={list[0]?.report_id ?? 'none yet'}
        />
      </div>

      <div className="table-toolbar">
        <label className="table-search" style={{ flex: 1, maxWidth: 380 }}>
          <Icon name="search" size={15} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search report ID, patient or session..."
            aria-label="Search reports"
          />
        </label>
        <span className="table-toolbar__spacer" />
        <button
          type="button"
          className="button button--ghost button--sm"
          onClick={reports.refresh}
          disabled={reports.refreshing}
        >
          <Icon name="refresh" size={14} />
          {reports.refreshing ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {reports.loading ? (
        <Spinner label="Loading reports…" />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon="file-text"
          title={query ? 'No report matches' : 'No reports generated'}
          description={
            query
              ? 'Try a report ID, patient name or session ID.'
              : 'Open a completed recording, run the analysis and generate the PDF report. It will appear here with its patient and session.'
          }
          action={
            <Link to="/patients" className="button button--primary">
              Open a patient
            </Link>
          }
        />
      ) : (
        <section className="panel" style={{ overflow: 'hidden' }}>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Report ID</th>
                  <th>Patient</th>
                  <th>Session</th>
                  <th>Version</th>
                  <th>Generated</th>
                  <th>Size</th>
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {filtered.map((report) => (
                  <tr key={report.id}>
                    <td>
                      <span className="mono">{report.report_id}</span>
                    </td>
                    <td>
                      <Link to={`/patients/${report.patient}`} className="table__primary">
                        {report.patient_name}
                      </Link>
                      <div className="table__secondary">{report.patient_code}</div>
                    </td>
                    <td>
                      <Link to={`/sessions/${report.session_id}`} className="mono table__secondary">
                        {report.session_id.slice(0, 8)}…
                      </Link>
                    </td>
                    <td>v{report.version}</td>
                    <td>{formatDateTime(report.generated_at)}</td>
                    <td>{(report.file_size / 1024).toFixed(0)} KB</td>
                    <td className="table__action">
                      <div className="button-row" style={{ justifyContent: 'flex-end' }}>
                        <button
                          type="button"
                          className="button button--ghost button--sm"
                          onClick={() => void download(report)}
                          disabled={downloading === report.id}
                        >
                          <Icon name="download" size={14} />
                          {downloading === report.id ? 'Preparing…' : 'PDF'}
                        </button>
                        <button
                          type="button"
                          className="button button--ghost button--sm"
                          onClick={() => navigate(`/sessions/${report.session_id}`)}
                        >
                          Open
                          <Icon name="chevron-right" size={13} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="table-footer">
            <span>{filtered.length} report{filtered.length === 1 ? '' : 's'}</span>
          </div>
        </section>
      )}

      <p className="muted small">
        <Icon name="shield" size={13} /> Reports are screening aids, not standalone medical
        diagnoses. Downloads require an authenticated operator.
      </p>
    </>
  )
}
