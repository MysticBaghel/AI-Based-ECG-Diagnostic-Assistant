import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { ApiError } from '@/shared/api/http'
import { reportsApi } from '@/features/reports/api'
import type { Patient, Session } from '@/shared/types'
import { Icon } from '@/shared/icons/Icon'
import { EmptyState, ErrorBanner, PageHeader, Spinner } from '@/shared/ui'
import { usePatient } from '@/features/patients/hooks/usePatients'
import { useDevices } from '@/features/devices/hooks/useDevices'
import { useSessions } from '@/features/sessions/hooks/useSessions'
import { formatDate } from '@/shared/lib/format'
import { LatestRecordingCard } from '../components/LatestRecordingCard'
import { PatientForm } from '../components/PatientForm'
import { PatientInfoCard } from '../components/PatientInfoCard'
import { PatientStats } from '../components/PatientStats'
import { SessionHistoryCard } from '../components/SessionHistoryCard'
import { StartSessionDialog } from '../components/StartSessionDialog'

export function PatientProfilePage() {
  const { patientId } = useParams<{ patientId: string }>()
  const id = Number(patientId)
  const navigate = useNavigate()
  const patient = usePatient(Number.isFinite(id) ? id : undefined)
  const sessions = useSessions({ patient: id }, Number.isFinite(id))
  const devices = useDevices()
  const [editing, setEditing] = useState(false)
  const [starting, setStarting] = useState(false)
  const [downloadError, setDownloadError] = useState<string | null>(null)
  const [downloading, setDownloading] = useState<string | null>(null)

  if (!Number.isFinite(id)) {
    return <EmptyState title="Patient not selected" description="Open a patient from the registry." />
  }

  if (patient.loading) return <Spinner label="Loading patient…" />
  if (patient.error) return <ErrorBanner message={patient.error} onRetry={patient.refresh} />

  const current = patient.data
  if (!current) return null
  const list = sessions.data ?? []

  async function downloadLatest(session: Session) {
    setDownloading(session.id)
    setDownloadError(null)
    try {
      const report = await reportsApi.latest(session.id)
      await reportsApi.download(report)
    } catch (caught) {
      setDownloadError(
        caught instanceof ApiError ? caught.message : 'Could not download the report.',
      )
    } finally {
      setDownloading(null)
    }
  }

  return (
    <>
      <PageHeader
        eyebrow={
          <>
            <Link to="/patients" className="back-link">
              <Icon name="chevron-left" size={14} />
              Patients
            </Link>
            <span> · permanent ID {current.patient_id}</span>
          </>
        }
        title={current.full_name}
        description={`Registered ${formatDate(current.created_at)} · ${list.length} ECG session${list.length === 1 ? '' : 's'} in history`}
        actions={
          <>
            <button type="button" className="button button--ghost" onClick={() => setEditing(true)}>
              <Icon name="plus" size={15} />
              Edit details
            </button>
            <button type="button" className="button button--primary" onClick={() => setStarting(true)}>
              <Icon name="pulse" size={15} />
              Start new ECG
            </button>
          </>
        }
      />

      {(sessions.error || devices.error || downloadError) && (
        <ErrorBanner
          message={sessions.error ?? devices.error ?? downloadError ?? ''}
          onRetry={() => {
            sessions.refresh()
            devices.refresh()
            setDownloadError(null)
          }}
        />
      )}

      <PatientStats sessions={list} />

      <div className="patient-profile-grid">
        <PatientInfoCard patient={current} />
        <LatestRecordingCard latest={list[0]} onStart={() => setStarting(true)} />
      </div>

      <SessionHistoryCard
        sessions={list}
        loading={sessions.loading}
        downloading={downloading}
        onDownload={(session) => void downloadLatest(session)}
      />

      {editing && (
        <PatientForm
          patient={current}
          onClose={() => setEditing(false)}
          onSaved={(saved: Patient) => {
            setEditing(false)
            patient.refresh()
            sessions.refresh()
            if (saved.id !== current.id) navigate(`/patients/${saved.id}`)
          }}
        />
      )}

      {starting && (
        <StartSessionDialog
          patient={current}
          devices={devices.data ?? []}
          onClose={() => setStarting(false)}
          onStarted={(session) => {
            setStarting(false)
            navigate(`/monitor/${session.id}`)
          }}
        />
      )}
    </>
  )
}
