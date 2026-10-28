import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { ApiError } from '@/shared/api/http'
import { analysisApi } from '@/features/analysis/api'
import { reportsApi } from '@/features/reports/api'
import type { AnalysisResult, ReportMeta } from '@/shared/types'
import { EmptyState, ErrorBanner, Notice, Spinner } from '@/shared/ui'
import { Icon } from '@/shared/icons/Icon'
import {
  useChunkIndex,
  useChunkWindow,
  useReports,
} from '@/features/analysis/hooks/useAnalysisData'
import { usePatient } from '@/features/patients/hooks/usePatients'
import { useSession } from '@/features/sessions/hooks/useSessions'
import { buildEcgSeries } from '@/shared/lib/ecg'
import { AnalysisHeader } from '../components/AnalysisHeader'
import { AnalysisSummaryCard } from '../components/AnalysisSummaryCard'
import { AIResultsCard } from '../components/AIResultsCard'
import { MeasurementsCard } from '../components/MeasurementsCard'
import { ModelInfoCard } from '../components/ModelInfoCard'
import { PatientInfoCard } from '../components/PatientInfoCard'
import { ReportHistoryCard } from '../components/ReportHistoryCard'
import { SessionInfoCard } from '../components/SessionInfoCard'
import { WaveformPanel } from '../components/WaveformPanel'

export function AnalysisPage() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const session = useSession(sessionId)
  const patient = usePatient(session.data?.patient)
  const reports = useReports(sessionId, session.data?.status !== 'active')
  const index = useChunkIndex(sessionId)
  const [start, setStart] = useState(0)
  const [size] = useState(12)
  const [busy, setBusy] = useState<'analyse' | 'report' | 'regenerate' | null>(null)
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
    return (
      <EmptyState
        title="No recording selected"
        description="Open a session from Reports or a patient profile."
      />
    )
  }

  if (session.loading) return <Spinner label="Loading recording…" />
  if (session.error) return <ErrorBanner message={session.error} onRetry={session.refresh} />
  if (!session.data) return null

  const current = session.data
  const analysis =
    current.analysis && 'session_id' in (current.analysis.result as object)
      ? (current.analysis.result as AnalysisResult)
      : null
  const latestReport = reports.data?.[0] ?? null
  const active = current.status === 'active'
  const reportList = reports.data ?? []

  async function runAnalysis() {
    setBusy('analyse')
    setActionError(null)
    try {
      const result = await analysisApi.run(current.id)
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

  async function ensureReport(regenerate: boolean): Promise<ReportMeta> {
    const result = await reportsApi.generate(current.id, regenerate)
    reports.refresh()
    session.refresh()
    return result
  }

  async function downloadLatest() {
    setBusy('report')
    setActionError(null)
    try {
      const report = latestReport ?? (await ensureReport(false))
      await reportsApi.download(report)
    } catch (caught) {
      setActionError(caught instanceof ApiError ? caught.message : 'Could not download the report.')
    } finally {
      setBusy(null)
    }
  }

  async function regenerateReport() {
    setBusy('regenerate')
    setActionError(null)
    try {
      const report = await ensureReport(true)
      await reportsApi.download(report)
    } catch (caught) {
      setActionError(caught instanceof ApiError ? caught.message : 'Could not regenerate the report.')
    } finally {
      setBusy(null)
    }
  }

  async function download(report: ReportMeta) {
    setActionError(null)
    try {
      await reportsApi.download(report)
    } catch (caught) {
      setActionError(caught instanceof ApiError ? caught.message : 'Could not download the report.')
    }
  }

  return (
    <>
      <AnalysisHeader
        session={current}
        busy={busy}
        onDownload={() => void downloadLatest()}
        onRegenerate={() => void regenerateReport()}
      />

      {actionError && <ErrorBanner message={actionError} />}
      {(index.error || window.error) && (
        <ErrorBanner
          message={index.error ?? window.error ?? ''}
          onRetry={() => {
            index.refresh()
            window.refresh()
          }}
        />
      )}
      {active && (
        <Notice tone="warn" icon="alert">
          This recording is still active. Stop it in the{' '}
          <Link to={`/monitor/${current.id}`}>live monitor</Link> before analysing or generating a
          report.
        </Notice>
      )}
      {current.analysis?.error && current.analysis_status === 'failed' && (
        <ErrorBanner
          message={`Analysis failed: ${current.analysis.error}`}
          onRetry={() => void runAnalysis()}
        />
      )}

      <div className="analysis-top">
        <PatientInfoCard session={current} patient={patient.data} />
        <SessionInfoCard session={current} reportCount={reportList.length} />
      </div>

      <WaveformPanel
        series={series}
        chunkCount={chunks.length}
        start={safeStart}
        size={size}
        maxStart={maxStart}
        loading={index.loading}
        windowLoading={window.loading}
        windowError={window.error}
        onRetry={window.refresh}
        onStart={setStart}
      />

      <div className="analysis-bottom">
        <AnalysisSummaryCard
          analysis={analysis}
          active={active}
          busy={busy === 'analyse'}
          onRun={() => void runAnalysis()}
        />
        <MeasurementsCard analysis={analysis} />
        <AIResultsCard analysis={analysis} />
        <ModelInfoCard analysis={analysis} />
      </div>

      <div className="analysis-warning">
        <Icon name="alert" size={16} />
        <span>
          This is an AI-powered screening aid and not a definitive medical diagnosis. Please
          consult a qualified healthcare professional for clinical interpretation. AI
          classification is experimental and unavailable unless a validated model is configured.
        </span>
      </div>

      <ReportHistoryCard
        reports={reportList}
        loading={reports.loading}
        onDownload={(report) => void download(report)}
      />
    </>
  )
}
