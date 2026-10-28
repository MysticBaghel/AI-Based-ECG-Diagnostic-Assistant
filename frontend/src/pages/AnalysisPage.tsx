import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { ApiError, api } from '../api/client'
import type { AnalysisResult, ReportMeta } from '../api/types'
import { EcgChart } from '../components/EcgChart'
import { Icon } from '../components/Icon'
import {
  Badge,
  EmptyState,
  ErrorBanner,
  Notice,
  PageHeader,
  SectionCard,
  SessionBadge,
  Spinner,
  StatCard,
} from '../components/ui'
import {
  useChunkIndex,
  useChunkWindow,
  useReports,
  useSession,
} from '../hooks/useData'
import { buildEcgSeries } from '../lib/ecg'
import { formatDateTime, formatDuration, formatNumber } from '../lib/format'

function Metric({
  label,
  value,
  hint,
}: {
  label: string
  value: string
  hint?: string
}) {
  return (
    <div className="metric">
      <span className="metric__label">{label}</span>
      <strong className="metric__value">{value}</strong>
      {hint && <span className="metric__hint">{hint}</span>}
    </div>
  )
}

function ProbabilityBars({ probabilities }: { probabilities: Record<string, number> }) {
  return (
    <div className="probability-list">
      {Object.entries(probabilities)
        .sort((a, b) => b[1] - a[1])
        .map(([label, probability]) => (
          <div className="probability" key={label}>
            <span className="probability__label">{label}</span>
            <span className="probability__track">
              <span
                className="probability__fill"
                style={{ width: `${Math.max(0, Math.min(100, probability * 100))}%` }}
              />
            </span>
            <span className="probability__value">{(probability * 100).toFixed(1)}%</span>
          </div>
        ))}
    </div>
  )
}

export function AnalysisPage() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const session = useSession(sessionId)
  const reports = useReports(sessionId, session.data?.status !== 'active')
  const index = useChunkIndex(sessionId)
  const [start, setStart] = useState(0)
  const [size, setSize] = useState(12)
  const [busy, setBusy] = useState<'analyse' | 'report' | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  const chunks = index.data?.chunks ?? []
  const maxStart = Math.max(0, chunks.length - size)
  const safeStart = Math.min(start, maxStart)
  const selected = chunks.slice(safeStart, safeStart + size)
  const window = useChunkWindow(
    sessionId,
    selected.map((chunk) => chunk.chunk_index),
  )
  const series = useMemo(() => buildEcgSeries(window.data ?? []), [window.data])

  if (!sessionId) {
    return <EmptyState title="No recording selected" description="Open a session from the dashboard." />
  }

  if (session.loading) return <Spinner label="Loading recording…" />
  if (session.error) return <ErrorBanner message={session.error} onRetry={session.refresh} />
  if (!session.data) return null

  const current = session.data
  const analysis =
    current.analysis && 'session_id' in (current.analysis.result as object)
      ? (current.analysis.result as AnalysisResult)
      : null
  const quality = analysis?.signal.quality
  const measurements = analysis?.measurements
  const ai = analysis?.ai
  const latestReport = reports.data?.[0] ?? null

  async function runAnalysis() {
    setBusy('analyse')
    setActionError(null)
    try {
      const result = await api.analyze(current.id)
      if (result.status === 'failed') {
        setActionError(result.error || 'Analysis failed. The compute service may be down.')
      }
      session.refresh()
      reports.refresh()
    } catch (caught) {
      setActionError(caught instanceof ApiError ? caught.message : 'Could not run the analysis.')
    } finally {
      setBusy(null)
    }
  }

  async function generateReport(regenerate = false) {
    setBusy('report')
    setActionError(null)
    try {
      if (!analysis) {
        const result = await api.analyze(current.id)
        if (result.status === 'failed') {
          throw new ApiError(result.error || 'Analysis failed.')
        }
      }
      const report = await api.generateReport(current.id, regenerate)
      reports.refresh()
      session.refresh()
      await api.downloadReport(report)
    } catch (caught) {
      setActionError(
        caught instanceof ApiError ? caught.message : 'Could not generate the report.',
      )
    } finally {
      setBusy(null)
    }
  }

  async function download(report: ReportMeta) {
    setActionError(null)
    try {
      await api.downloadReport(report)
    } catch (caught) {
      setActionError(caught instanceof ApiError ? caught.message : 'Could not download the report.')
    }
  }

  return (
    <>
      <div className="monitor-header">
        <div>
          <Link to={`/patients/${current.patient}`} className="back-link">
            <Icon name="chevron-left" size={15} />
            {current.patient_name} · {current.patient_code}
          </Link>
          <PageHeader
            eyebrow="Analysis & report"
            title={`${current.patient_name} · ${current.device_name}`}
            description={`${formatDateTime(current.start_time)} · ${formatDuration(current.duration_seconds)} · session ${current.id}`}
          />
        </div>
        <div className="monitor-header__badges">
          <SessionBadge status={current.status} />
          {current.status === 'active' ? (
            <Link to={`/monitor/${current.id}`} className="button button--primary button--sm">
              <Icon name="pulse" size={14} />
              Back to live monitor
            </Link>
          ) : (
            <button
              type="button"
              className="button button--ghost button--sm"
              onClick={() => void runAnalysis()}
              disabled={busy !== null}
            >
              <Icon name="refresh" size={14} />
              {busy === 'analyse' ? 'Analysing…' : analysis ? 'Re-run analysis' : 'Run analysis'}
            </button>
          )}
          {current.status !== 'active' && (
            <button
              type="button"
              className="button button--primary button--sm"
              onClick={() => void generateReport(false)}
              disabled={busy !== null}
            >
              <Icon name="shield" size={14} />
              {busy === 'report' ? 'Generating…' : latestReport ? 'Get latest PDF' : 'Generate PDF report'}
            </button>
          )}
        </div>
      </div>

      {actionError && <ErrorBanner message={actionError} />}
      {current.status === 'active' && (
        <Notice tone="warn" icon="alert">
          This recording is still active. Stop it in the live monitor before analysis or
          report generation.
        </Notice>
      )}
      {current.analysis?.error && current.analysis_status === 'failed' && (
        <ErrorBanner
          message={`Analysis failed: ${current.analysis.error}`}
          onRetry={() => void runAnalysis()}
        />
      )}
      {(index.error || window.error) && (
        <ErrorBanner
          message={index.error ?? window.error ?? ''}
          onRetry={() => {
            index.refresh()
            window.refresh()
          }}
        />
      )}

      <div className="stats stats--four">
        <StatCard
          icon="heart"
          label="Heart rate"
          value={
            measurements?.heart_rate_bpm != null
              ? `${measurements.heart_rate_bpm.toFixed(0)} bpm`
              : '—'
          }
          hint={quality?.usable ? 'measured from ECG' : 'withheld when unusable'}
          tone={measurements?.heart_rate_bpm != null ? 'ok' : 'neutral'}
        />
        <StatCard
          icon="activity"
          label="Signal quality"
          value={quality ? `${quality.score?.toFixed(0) ?? '—'} / 100` : '—'}
          hint={quality?.level ?? 'analysis not run'}
          tone={
            quality ? (quality.usable ? (quality.level === 'good' ? 'ok' : 'info') : 'bad') : 'neutral'
          }
        />
        <StatCard
          icon="pulse"
          label="Beats detected"
          value={measurements?.beats_detected ?? '—'}
          hint={analysis ? `${analysis.signal.duration_seconds.toFixed(1)} s analysed` : ''}
        />
        <StatCard
          icon="sessions"
          label="Reports"
          value={reports.data?.length ?? 0}
          hint={latestReport ? `latest ${latestReport.report_id}` : 'none yet'}
          tone={(reports.data?.length ?? 0) > 0 ? 'ok' : 'neutral'}
        />
      </div>

      <section className="panel panel--ecg">
        <div className="panel__header">
          <div>
            <h2>Recorded waveform</h2>
            <p>
              {series.sampleCount} samples · {series.durationSeconds.toFixed(1)} s in view ·{' '}
              {chunks.length} stored chunks
            </p>
          </div>
          <div className="panel__actions">
            <label className="field field--compact">
              <span>Window</span>
              <select
                value={size}
                onChange={(event) => {
                  setSize(Number(event.target.value))
                  setStart(0)
                }}
              >
                {[6, 12, 24].map((value) => (
                  <option key={value} value={value}>
                    {value} chunks
                  </option>
                ))}
              </select>
            </label>
          </div>
        </div>
        <div className="panel__body">
          {index.loading ? (
            <Spinner label="Loading the recording index…" />
          ) : chunks.length === 0 ? (
            <EmptyState
              icon="pulse"
              title="No ECG waveform stored"
              description="FastAPI has no ECG chunks for this session. Was the simulator run with --ecg?"
            />
          ) : (
            <>
              {window.loading && series.sampleCount === 0 ? (
                <Spinner label="Loading samples…" />
              ) : (
                <EcgChart
                  x={series.x}
                  y={series.y}
                  height={330}
                  emptyLabel="This window has no samples."
                />
              )}
              <div className="chunk-nav">
                <button
                  type="button"
                  className="button button--ghost button--sm"
                  onClick={() => setStart(Math.max(0, safeStart - size))}
                  disabled={safeStart === 0}
                >
                  <Icon name="chevron-left" size={14} />
                  Earlier
                </button>
                <input
                  type="range"
                  className="chunk-nav__range"
                  min={0}
                  max={maxStart}
                  value={safeStart}
                  onChange={(event) => setStart(Number(event.target.value))}
                  aria-label="Start chunk"
                />
                <button
                  type="button"
                  className="button button--ghost button--sm"
                  onClick={() => setStart(Math.min(maxStart, safeStart + size))}
                  disabled={safeStart >= maxStart}
                >
                  Later
                  <Icon name="chevron-right" size={14} />
                </button>
                <span className="chunk-nav__label">
                  chunks {safeStart}–{Math.min(chunks.length - 1, safeStart + size - 1)} of{' '}
                  {chunks.length}
                </span>
              </div>
            </>
          )}
        </div>
      </section>

      {!analysis ? (
        <Notice tone="info" icon="spark">
          <strong>Analysis has not run for this recording.</strong>{' '}
          {current.status === 'active'
            ? 'Stop the recording first.'
            : 'Run the analysis to produce signal measurements and, if a validated model is configured, an AI screening result.'}
        </Notice>
      ) : (
        <div className="analysis-grid">
          <SectionCard
            title="Measured parameters"
            subtitle="Deterministic signal processing — not a diagnosis"
          >
            {quality?.usable ? (
              <div className="metric-grid">
                <Metric
                  label="Heart rate"
                  value={`${formatNumber(measurements?.heart_rate_bpm ?? null, 0)} bpm`}
                  hint="from median RR interval"
                />
                <Metric
                  label="Mean RR"
                  value={`${formatNumber(measurements?.rr_mean_ms ?? null, 0)} ms`}
                  hint={`${measurements?.rr_intervals_ms.length ?? 0} intervals`}
                />
                <Metric
                  label="RR standard deviation"
                  value={`${formatNumber(measurements?.rr_std_ms ?? null, 0)} ms`}
                  hint="variability"
                />
                <Metric
                  label="RMSSD"
                  value={`${formatNumber(measurements?.rmssd_ms ?? null, 0)} ms`}
                  hint="successive differences"
                />
                <Metric
                  label="pNN50"
                  value={`${formatNumber(measurements?.pnn50_percent ?? null, 1)} %`}
                  hint="intervals > 50 ms apart"
                />
                <Metric
                  label="Beats detected"
                  value={String(measurements?.beats_detected ?? '—')}
                  hint={`${analysis.signal.duration_seconds.toFixed(1)} s analysed`}
                />
              </div>
            ) : (
              <Notice tone="warn" icon="alert">
                <strong>Measurements withheld.</strong> The signal did not meet the quality
                threshold, so no heart rate or RR values are reported.
              </Notice>
            )}

            <div className="quality-detail">
              <div className="quality-bar">
                <span style={{ width: `${Math.max(0, Math.min(100, quality?.score ?? 0))}%` }} />
              </div>
              <span className="muted small">
                Signal quality {quality?.score?.toFixed(1) ?? '—'} / 100 · {quality?.level ?? 'unknown'} ·{' '}
                {analysis.signal.sample_rate_hz ?? '—'} Hz · {analysis.signal.filtering_note}
              </span>
              {quality?.reasons.length ? (
                <ul className="reason-list">
                  {quality.reasons.map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              ) : null}
            </div>
          </SectionCard>

          <SectionCard title="AI-assisted classification" subtitle="Experimental screening only">
            {ai?.available ? (
              <>
                <div className="prediction">
                  <span className="muted small">Model suggestion</span>
                  <strong>{ai.predicted_class}</strong>
                  <Badge tone="warn" dot={false}>
                    experimental
                  </Badge>
                </div>
                {ai.probabilities && <ProbabilityBars probabilities={ai.probabilities} />}
                <div className="kv-list">
                  <div>
                    <span>Model</span>
                    <strong>{ai.model_name ?? '—'}</strong>
                  </div>
                  <div>
                    <span>Version</span>
                    <strong>{ai.model_version ?? '—'}</strong>
                  </div>
                  <div>
                    <span>Analysed at</span>
                    <strong>{formatDateTime(ai.analyzed_at)}</strong>
                  </div>
                  <div>
                    <span>Classes</span>
                    <strong>{ai.classes.join(', ') || '—'}</strong>
                  </div>
                </div>
                <Notice tone="warn" icon="alert">
                  A model probability is not a diagnosis. The classifier is an experimental
                  screening aid and requires qualified clinical interpretation.
                </Notice>
              </>
            ) : (
              <Notice tone="warn" icon="alert">
                <strong>AI analysis is unavailable.</strong>{' '}
                {ai?.reason || 'No validated classification model is configured.'} No
                prediction or probability has been fabricated. The DSP measurements above are
                still real measurements of this recording.
              </Notice>
            )}
          </SectionCard>
        </div>
      )}

      {analysis && (
        <div className="analysis-grid">
          <SectionCard title="Findings and cautious guidance" subtitle="Generated from stored results">
            <ul className="finding-list">
              {analysis.findings.map((finding) => (
                <li key={finding}>{finding}</li>
              ))}
            </ul>
          </SectionCard>
          <SectionCard title="Limitations" subtitle="Read before using this report">
            <ul className="finding-list">
              {analysis.limitations.map((limitation) => (
                <li key={limitation}>{limitation}</li>
              ))}
            </ul>
          </SectionCard>
        </div>
      )}

      <SectionCard
        title="PDF reports"
        subtitle="Generated from the stored analysis and waveform; downloads require sign-in"
        actions={
          current.status !== 'active' ? (
            <button
              type="button"
              className="button button--primary button--sm"
              onClick={() => void generateReport(Boolean(latestReport))}
              disabled={busy !== null}
            >
              <Icon name="shield" size={14} />
              {busy === 'report'
                ? 'Generating…'
                : latestReport
                  ? 'Regenerate PDF'
                  : 'Generate PDF'}
            </button>
          ) : null
        }
      >
        {reports.loading ? (
          <Spinner label="Loading reports…" />
        ) : (reports.data?.length ?? 0) === 0 ? (
          <p className="muted small">
            No report has been generated. A report includes the patient and session details,
            the waveform, signal quality, measurements, the AI result (or an explicit
            unavailable notice), and limitations.
          </p>
        ) : (
          <div className="report-list">
            {reports.data?.map((report) => (
              <div className="report-row" key={report.id}>
                <div>
                  <strong>{report.report_id}</strong>
                  <span className="muted small">
                    version {report.version} · {formatDateTime(report.generated_at)} ·{' '}
                    {(report.file_size / 1024).toFixed(0)} KB
                  </span>
                </div>
                <button
                  type="button"
                  className="button button--ghost button--sm"
                  onClick={() => void download(report)}
                >
                  <Icon name="copy" size={14} />
                  Download PDF
                </button>
              </div>
            ))}
          </div>
        )}
        <p className="muted small">
          The PDF is stored with its exact analysis snapshot. It is a screening aid, not a
          standalone medical diagnosis.
        </p>
      </SectionCard>
    </>
  )
}
