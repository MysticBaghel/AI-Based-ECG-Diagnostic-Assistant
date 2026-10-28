import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { ApiError, api } from '../api/client'
import type { Patient, Session } from '../api/types'
import { Icon } from '../components/Icon'
import { PatientForm } from '../components/PatientForm'
import { AnalysisBadge, SessionTable } from '../components/SessionList'
import { StartSessionDialog } from '../components/StartSessionDialog'
import {
  Badge,
  EmptyState,
  ErrorBanner,
  PageHeader,
  SectionCard,
  Spinner,
  StatCard,
} from '../components/ui'
import { useDevices, usePatient, useSessions } from '../hooks/useData'
import { formatDate, formatDateTime, initials } from '../lib/format'

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value || '—'}</strong>
    </div>
  )
}

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

  const current = patient.data
  const list = sessions.data ?? []

  async function downloadLatest(session: Session) {
    setDownloading(session.id)
    setDownloadError(null)
    try {
      const report = await api.latestReport(session.id)
      await api.downloadReport(report)
    } catch (caught) {
      setDownloadError(
        caught instanceof ApiError ? caught.message : 'Could not download the report.',
      )
    } finally {
      setDownloading(null)
    }
  }

  if (patient.loading) return <Spinner label="Loading patient…" />
  if (patient.error) return <ErrorBanner message={patient.error} onRetry={patient.refresh} />
  if (!current) return null

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

      <div className="stats stats--four">
        <StatCard icon="sessions" label="Recordings" value={list.length} hint="all time" />
        <StatCard
          icon="activity"
          label="Analysed"
          value={list.filter((session) => session.analysis_status === 'completed').length}
          hint="DSP completed"
        />
        <StatCard
          icon="shield"
          label="Reports"
          value={list.reduce((sum, session) => sum + session.report_count, 0)}
          hint="stored PDFs"
        />
        <StatCard
          icon="clock"
          label="Latest recording"
          value={list[0] ? formatDateTime(list[0].start_time) : '—'}
          hint={list[0]?.status ?? 'none yet'}
        />
      </div>

      <div className="patient-profile-grid">
        <SectionCard title="Patient information" subtitle="Permanent registry record">
          <div className="patient-identity">
            <span className="avatar avatar--xl">{initials(current.full_name)}</span>
            <div>
              <strong>{current.full_name}</strong>
              <span className="mono">{current.patient_id}</span>
            </div>
          </div>
          <div className="kv-list">
            <InfoRow label="Phone" value={current.phone} />
            <InfoRow label="Email" value={current.email} />
            <InfoRow label="Date of birth" value={formatDate(current.date_of_birth)} />
            <InfoRow
              label="Age / sex"
              value={`${current.age ?? '—'} · ${current.sex === 'unknown' ? '—' : current.sex}`}
            />
            <InfoRow label="Last updated" value={formatDateTime(current.updated_at)} />
          </div>
          {current.notes && <p className="patient-card__notes">{current.notes}</p>}
          <p className="muted small">
            The patient does not have a login account. Access is limited to authenticated
            operators of this installation.
          </p>
        </SectionCard>

        <SectionCard title="Recording" subtitle="Start a new ECG or review the latest">
          <div className="stack">
            {list[0] ? (
              <div className="latest-session">
                <div>
                  <span className="muted small">Most recent</span>
                  <strong>{formatDateTime(list[0].start_time)}</strong>
                  <span className="muted small">
                    {list[0].device_name} · {list[0].status}
                  </span>
                </div>
                <div className="button-row">
                  <AnalysisBadge status={list[0].analysis_status} />
                  <Link
                    to={
                      list[0].status === 'active'
                        ? `/monitor/${list[0].id}`
                        : `/sessions/${list[0].id}`
                    }
                    className="button button--ghost button--sm"
                  >
                    Open
                    <Icon name="chevron-right" size={14} />
                  </Link>
                </div>
              </div>
            ) : (
              <p className="muted small">
                No recording yet. Start one with a registered device; the simulator can
                supply the signal if no ESP32 is connected.
              </p>
            )}
            <button
              type="button"
              className="button button--primary button--block"
              onClick={() => setStarting(true)}
            >
              <Icon name="pulse" size={16} />
              Start a new ECG recording
            </button>
            <p className="muted small">
              A returning patient reuses this record. Never register a duplicate because the
              phone number looks similar — search first.
            </p>
          </div>
        </SectionCard>
      </div>

      <SectionCard
        title="ECG history"
        subtitle="Every session, its analysis state and its reports"
        actions={<Badge tone="info" dot={false}>{list.length} sessions</Badge>}
        flush
      >
        {sessions.loading ? (
          <Spinner label="Loading session history…" />
        ) : list.length === 0 ? (
          <EmptyState
            icon="pulse"
            title="No ECG sessions yet"
            description="Start the first recording for this patient. It will appear here with its waveform, analysis and PDF report."
          />
        ) : (
          <>
            <SessionTable sessions={list} />
            <div className="report-downloads">
              <span className="muted small">Download an existing report:</span>
              {list
                .filter((session) => session.report_count > 0)
                .map((session) => (
                  <button
                    type="button"
                    key={session.id}
                    className="button button--ghost button--sm"
                    onClick={() => void downloadLatest(session)}
                    disabled={downloading === session.id}
                  >
                    <Icon name="copy" size={14} />
                    {downloading === session.id
                      ? 'Preparing…'
                      : `${formatDateTime(session.start_time)} · PDF`}
                  </button>
                ))}
            </div>
          </>
        )}
      </SectionCard>

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
