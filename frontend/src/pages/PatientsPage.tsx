import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import type { Patient, Session } from '../api/types'
import { useAuth } from '../auth/useAuth'
import { Icon } from '../components/Icon'
import { StartSessionDialog } from '../components/StartSessionDialog'
import {
  Badge,
  EmptyState,
  ErrorBanner,
  PageHeader,
  SessionBadge,
  Spinner,
} from '../components/ui'
import { useDevices, usePatients, useSessions } from '../hooks/useData'
import { formatDate, initials } from '../lib/format'

function PatientCard({
  patient,
  sessions,
  canManage,
  onStart,
}: {
  patient: Patient
  sessions: Session[]
  canManage: boolean
  onStart: (patient: Patient) => void
}) {
  const active = sessions.find((session) => session.status === 'active')
  const latest = sessions[0]

  return (
    <article className="patient-card">
      <div className="patient-card__top">
        <span className="avatar avatar--lg">{initials(patient.username)}</span>
        <div className="patient-card__identity">
          <strong>{patient.username}</strong>
          <span>{patient.email || 'no email on file'}</span>
        </div>
        {active ? <Badge tone="ok" pulse>In session</Badge> : <Badge tone="neutral">Idle</Badge>}
      </div>

      <dl className="patient-card__meta">
        <div>
          <dt>Date of birth</dt>
          <dd>{formatDate(patient.date_of_birth)}</dd>
        </div>
        <div>
          <dt>Sessions</dt>
          <dd>{sessions.length}</dd>
        </div>
        <div>
          <dt>Patient ID</dt>
          <dd className="mono">{patient.id}</dd>
        </div>
      </dl>

      {patient.notes && <p className="patient-card__notes">{patient.notes}</p>}

      <div className="patient-card__footer">
        {active ? (
          <Link to={`/live/${active.id}`} className="button button--primary button--sm">
            <Icon name="play" size={14} />
            Watch live
          </Link>
        ) : latest ? (
          <Link to={`/sessions/${latest.id}`} className="button button--ghost button--sm">
            <Icon name="sessions" size={14} />
            Latest recording
          </Link>
        ) : (
          <span className="muted small">No sessions yet</span>
        )}

        {canManage && (
          <button
            type="button"
            className="button button--ghost button--sm"
            onClick={() => onStart(patient)}
          >
            <Icon name="plus" size={14} />
            Start session
          </button>
        )}
      </div>
    </article>
  )
}

export function PatientsPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const patients = usePatients()
  const sessions = useSessions()
  const devices = useDevices(user?.role !== 'patient')
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<Patient | null>(null)

  const canManage = user?.role === 'doctor' || user?.role === 'admin'

  const byPatient = useMemo(() => {
    const map = new Map<number, Session[]>()
    for (const session of sessions.data ?? []) {
      const list = map.get(session.patient) ?? []
      list.push(session)
      map.set(session.patient, list)
    }
    return map
  }, [sessions.data])

  const filtered = useMemo(() => {
    const list = patients.data ?? []
    const needle = query.trim().toLowerCase()
    if (!needle) return list
    return list.filter((patient) =>
      [patient.username, patient.email, patient.notes]
        .join(' ')
        .toLowerCase()
        .includes(needle),
    )
  }, [patients.data, query])

  const isPatient = user?.role === 'patient'

  return (
    <>
      <PageHeader
        eyebrow={isPatient ? 'Your record' : 'Care team'}
        title={isPatient ? 'My profile' : 'Patients'}
        description={
          isPatient
            ? 'The identity and profile Django holds for you, plus the sessions your care team has run.'
            : 'Everyone you are allowed to see. Start a session on a patient and a device, then open the live monitor.'
        }
        actions={
          !isPatient && (
            <Link to="/devices" className="button button--ghost">
              <Icon name="devices" size={16} />
              Manage devices
            </Link>
          )
        }
      />

      {(patients.error || sessions.error || devices.error) && (
        <ErrorBanner
          message={patients.error ?? sessions.error ?? devices.error ?? ''}
          onRetry={() => {
            patients.refresh()
            sessions.refresh()
            devices.refresh()
          }}
        />
      )}

      {!isPatient && (
        <div className="toolbar">
          <label className="search">
            <Icon name="search" size={16} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search by name, email or note…"
              aria-label="Search patients"
            />
          </label>
          <span className="toolbar__hint">
            {filtered.length} of {patients.data?.length ?? 0} patients
          </span>
        </div>
      )}

      {patients.loading ? (
        <Spinner label="Loading patients…" />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon="users"
          title={query ? 'No patient matches' : 'No patients visible'}
          description={
            query
              ? 'Try a different name, email or note.'
              : isPatient
                ? 'Your account has no patient profile yet.'
                : 'A doctor sees only patients assigned to them. An admin can assign patients in Django Admin.'
          }
          action={
            isPatient ? undefined : (
              <Link to="/devices" className="button button--ghost">
                Register a device
              </Link>
            )
          }
        />
      ) : (
        <div className="patient-grid">
          {filtered.map((patient) => (
            <PatientCard
              key={patient.id}
              patient={patient}
              sessions={byPatient.get(patient.id) ?? []}
              canManage={canManage}
              onStart={setSelected}
            />
          ))}
        </div>
      )}

      {!isPatient && (
        <div className="hint-row">
          <Icon name="alert" size={15} />
          <span>
            Sessions cannot be started for a disabled device, a device another doctor owns,
            or a patient you are not assigned to. The server enforces all three.
          </span>
        </div>
      )}

      {selected && (
        <StartSessionDialog
          patient={selected}
          devices={devices.data ?? []}
          onClose={() => setSelected(null)}
          onStarted={(session) => {
            setSelected(null)
            navigate(`/live/${session.id}`)
          }}
        />
      )}

      {sessions.data && sessions.data[0] && (
        <p className="muted small">
          Latest session: <SessionBadge status={sessions.data[0].status} />{' '}
          {sessions.data[0].patient_name} · {sessions.data[0].device_name}
        </p>
      )}
    </>
  )
}
