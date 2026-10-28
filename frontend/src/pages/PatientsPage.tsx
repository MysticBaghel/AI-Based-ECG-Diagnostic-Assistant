import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import type { Patient } from '../api/types'
import { Icon } from '../components/Icon'
import { PatientForm } from '../components/PatientForm'
import {
  Badge,
  EmptyState,
  ErrorBanner,
  PageHeader,
  Spinner,
  StatCard,
} from '../components/ui'
import { usePatients } from '../hooks/useData'
import { formatDate, initials } from '../lib/format'

function PatientCard({ patient }: { patient: Patient }) {
  return (
    <article className="patient-card">
      <div className="patient-card__top">
        <span className="avatar avatar--lg">{initials(patient.full_name)}</span>
        <div className="patient-card__identity">
          <strong>{patient.full_name}</strong>
          <span className="mono">{patient.patient_id}</span>
        </div>
        <Badge tone={patient.session_count > 0 ? 'ok' : 'neutral'} dot={false}>
          {patient.session_count} session{patient.session_count === 1 ? '' : 's'}
        </Badge>
      </div>

      <dl className="patient-card__meta">
        <div>
          <dt>Phone</dt>
          <dd>{patient.phone || '—'}</dd>
        </div>
        <div>
          <dt>Date of birth</dt>
          <dd>{formatDate(patient.date_of_birth)}</dd>
        </div>
        <div>
          <dt>Age / sex</dt>
          <dd>
            {patient.age ?? '—'} · {patient.sex === 'unknown' ? '—' : patient.sex}
          </dd>
        </div>
      </dl>

      {patient.notes && <p className="patient-card__notes">{patient.notes}</p>}

      <div className="patient-card__footer">
        <Link to={`/patients/${patient.id}`} className="button button--primary button--sm">
          <Icon name="sessions" size={14} />
          Open profile & history
        </Link>
      </div>
    </article>
  )
}

export function PatientsPage() {
  const [query, setQuery] = useState('')
  const [registering, setRegistering] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const patients = usePatients(query)
  const list = useMemo(() => patients.data ?? [], [patients.data])
  const withSessions = useMemo(
    () => list.filter((patient) => patient.session_count > 0).length,
    [list],
  )

  return (
    <>
      <PageHeader
        eyebrow="Patient registry"
        title="Patients"
        description="Search by name, phone number or permanent patient ID. Every ECG recording and report is attached to one of these records."
        actions={
          <button type="button" className="button button--primary" onClick={() => setRegistering(true)}>
            <Icon name="plus" size={16} />
            Register patient
          </button>
        }
      />

      {patients.error && (
        <ErrorBanner message={patients.error} onRetry={patients.refresh} />
      )}

      <div className="stats stats--three">
        <StatCard icon="users" label="Patients" value={list.length} hint="in this view" />
        <StatCard
          icon="sessions"
          label="With ECG history"
          value={withSessions}
          hint="at least one recording"
        />
        <StatCard
          icon="shield"
          label="Patient ID"
          value="Permanent"
          hint="generated once, never reused"
        />
      </div>

      <div className="toolbar toolbar--wrap">
        <label className="search search--grow">
          <Icon name="search" size={16} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search name, phone number or patient ID…"
            aria-label="Search patients"
          />
        </label>
        <button
          type="button"
          className="button button--ghost button--sm"
          onClick={patients.refresh}
          disabled={patients.refreshing}
        >
          <Icon name="refresh" size={14} />
          {patients.refreshing ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {notice && (
        <div className="banner banner--ok">
          <Icon name="check" size={17} />
          <div className="banner__body">{notice}</div>
        </div>
      )}

      {patients.loading ? (
        <Spinner label="Loading patients…" />
      ) : list.length === 0 ? (
        <EmptyState
          icon="users"
          title={query ? 'No patient matches' : 'No patients registered'}
          description={
            query
              ? 'Search by full name, phone number or patient ID, or register the patient as new.'
              : 'Register the first patient. The application generates a permanent patient ID; no login account is needed for the patient.'
          }
          action={
            <button type="button" className="button button--primary" onClick={() => setRegistering(true)}>
              Register a patient
            </button>
          }
        />
      ) : (
        <div className="patient-grid">
          {list.map((patient) => (
            <PatientCard key={patient.id} patient={patient} />
          ))}
        </div>
      )}

      {registering && (
        <PatientForm
          onClose={() => setRegistering(false)}
          onSaved={(patient) => {
            setRegistering(false)
            setNotice(
              `${patient.full_name} registered as ${patient.patient_id}. Open the profile to start a recording.`,
            )
            patients.refresh()
          }}
        />
      )}
    </>
  )
}
