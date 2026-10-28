import { useState } from 'react'
import { Link } from 'react-router-dom'

import { usePatients } from '@/features/patients/hooks/usePatients'
import { Badge, ErrorBanner, SectionCard, Spinner } from '@/shared/ui'
import { Icon } from '@/shared/icons/Icon'
import { initials } from '@/shared/lib/format'
import type { Patient, Session } from '@/shared/types'

export function PatientSearchCard({
  active,
  onSelect,
  onRegister,
}: {
  active: Session[]
  onSelect: (patient: Patient) => void
  onRegister: () => void
}) {
  const [query, setQuery] = useState('')
  const patients = usePatients(query, query.trim().length > 0)
  const results = (patients.data ?? []).slice(0, 6)

  return (
    <SectionCard
      title="Start a new recording"
      subtitle="Select an existing patient or register a new one"
    >
      <div className="search-panel">
        <div className="toolbar">
          <label className="search search--grow">
            <Icon name="search" size={16} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Find a patient by name, phone number or patient ID…"
              aria-label="Search patients for a new recording"
            />
          </label>
          <button type="button" className="button button--ghost" onClick={onRegister}>
            <Icon name="plus" size={15} />
            New patient
          </button>
        </div>

        {query.trim() && (
          <div className="search-results">
            {patients.loading ? (
              <Spinner label="Searching…" />
            ) : patients.error ? (
              <ErrorBanner message={patients.error} onRetry={patients.refresh} />
            ) : results.length === 0 ? (
              <div className="search-empty">
                <span>No patient matches “{query}”.</span>
                <button type="button" className="button button--primary button--sm" onClick={onRegister}>
                  Register this patient
                </button>
              </div>
            ) : (
              results.map((patient) => (
                <button
                  type="button"
                  key={patient.id}
                  className="search-result"
                  onClick={() => onSelect(patient)}
                >
                  <span className="avatar avatar--sm">{initials(patient.full_name)}</span>
                  <span className="search-result__identity">
                    <strong>{patient.full_name}</strong>
                    <small>
                      {patient.patient_id} · {patient.phone || 'no phone'} ·{' '}
                      {patient.session_count} session{patient.session_count === 1 ? '' : 's'}
                    </small>
                  </span>
                  <span className="search-result__cta">
                    Start recording
                    <Icon name="chevron-right" size={14} />
                  </span>
                </button>
              ))
            )}
          </div>
        )}

        {active.length > 0 && (
          <div className="active-strip">
            <Badge tone="ok" pulse>
              {active.length} recording{active.length === 1 ? '' : 's'} active
            </Badge>
            <Link to={`/monitor/${active[0].id}`} className="button button--ghost button--sm">
              Open {active[0].patient_name}
              <Icon name="chevron-right" size={14} />
            </Link>
          </div>
        )}
      </div>
    </SectionCard>
  )
}
