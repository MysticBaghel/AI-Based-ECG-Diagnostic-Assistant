import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { ApiError } from '@/shared/api/http'
import { analysisApi } from '@/features/analysis/api'
import { usePatient } from '@/features/patients/hooks/usePatients'
import { useSession } from '@/features/sessions/hooks/useSessions'
import { sessionsApi } from '@/features/sessions/api'
import { ErrorBanner, Spinner } from '@/shared/ui'
import { useNow } from '@/shared/hooks/useNow'
import { elapsedSeconds } from '@/shared/lib/format'
import { MonitorFooter } from '../components/MonitorFooter'
import { MonitorHeader } from '../components/MonitorHeader'
import { MonitorMetrics } from '../components/MonitorMetrics'
import { PatientSelectorBar } from '../components/PatientSelectorBar'
import { RecordingPanel } from '../components/RecordingPanel'
import { useLiveAnalysis } from '../hooks/useLiveAnalysis'
import { useLiveMonitor } from '../hooks/useLiveMonitor'
import { MonitorIndexPage } from './MonitorIndexPage'

export function MonitorPage() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const navigate = useNavigate()
  const session = useSession(sessionId)
  const patient = usePatient(session.data?.patient)
  const live = useLiveMonitor(sessionId ?? null)
  const now = useNow(1000)
  const current = session.data
  const liveAnalysis = useLiveAnalysis(
    sessionId,
    Boolean(sessionId) && current?.status === 'active',
  )
  const [stopping, setStopping] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  if (!sessionId) return <MonitorIndexPage />
  if (session.loading) return <Spinner label="Loading recording…" />
  if (session.error) return <ErrorBanner message={session.error} onRetry={session.refresh} />
  if (!current) return null

  const elapsed = elapsedSeconds(current.start_time, current.end_time ?? now.toISOString())
  const lastChunk = live.chunks[live.chunks.length - 1]
  const rate = lastChunk?.sample_rate_hz ?? current.sample_rate_hz ?? null
  const active = current.status === 'active'
  const analysisHref = `/sessions/${current.id}`

  async function finishRecording() {
    if (!current) return
    if (
      !window.confirm(
        'Stop this recording? The device will be refused further uploads, and analysis will run on the stored signal.',
      )
    ) {
      return
    }
    setStopping(true)
    setActionError(null)
    try {
      await sessionsApi.stop(current.id)
      try {
        await analysisApi.run(current.id)
      } catch (caught) {
        setActionError(
          caught instanceof ApiError
            ? `Recording stopped, but analysis failed: ${caught.message}`
            : 'Recording stopped, but analysis could not run.',
        )
      }
      navigate(analysisHref)
    } catch (caught) {
      setActionError(caught instanceof ApiError ? caught.message : 'Could not stop the recording.')
    } finally {
      setStopping(false)
    }
  }

  return (
    <>
      <MonitorHeader session={current} connection={live.connection} rate={rate} />

      {actionError && <ErrorBanner message={actionError} />}
      {live.socketError && <ErrorBanner message={live.socketError} onRetry={() => live.reconnect()} />}
      {live.chunkError && <ErrorBanner message={live.chunkError} onRetry={() => live.reconnect()} />}
      {liveAnalysis.error && active && (
        <ErrorBanner message={liveAnalysis.error} onRetry={liveAnalysis.refresh} />
      )}

      <PatientSelectorBar
        session={current}
        patient={patient.data}
        active={active}
        stopping={stopping}
        onStop={() => void finishRecording()}
        analysisHref={analysisHref}
      />

      <RecordingPanel
        series={live.series}
        chunks={live.chunks.length}
        frames={live.frames}
        active={active}
        elapsed={elapsed}
        initialLoading={live.initialLoading}
      />

      <MonitorMetrics analysis={liveAnalysis.data} active={active} elapsed={elapsed} />

      <MonitorFooter
        connection={live.connection}
        frames={live.frames}
        sessionId={current.id}
        active={active}
        analysisHref={analysisHref}
      />
    </>
  )
}
