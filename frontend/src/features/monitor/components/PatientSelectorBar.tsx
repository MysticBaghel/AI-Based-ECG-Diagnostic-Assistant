import { Link } from 'react-router-dom'

import type { Patient, Session } from '@/shared/types'
import { Icon } from '@/shared/icons/Icon'

export function PatientSelectorBar({
  session,
  patient,
  active,
  stopping,
  onStop,
  analysisHref,
}: {
  session: Session
  patient: Patient | null
  active: boolean
  stopping: boolean
  onStop: () => void
  analysisHref: string
}) {
  return (
    <div className="monitor-toolbar">
      <span className="monitor-toolbar__label">Patient</span>
      <Link to={`/patients/${session.patient}`} className="monitor-toolbar__patient">
        <span className="avatar avatar--sm">
          {session.patient_name.slice(0, 2).toUpperCase()}
        </span>
        <strong>{session.patient_code}</strong>
        <span>|</span>
        <span>{session.patient_name}</span>
        {patient?.age != null && (
          <>
            <span>|</span>
            <span>{patient.age} yrs</span>
          </>
        )}
        {patient?.phone && (
          <>
            <span>|</span>
            <span>{patient.phone}</span>
          </>
        )}
        <Icon name="chevron-down" size={14} />
      </Link>
      <div className="monitor-toolbar__actions">
        <Link to="/patients" className="button button--primary">
          <Icon name="plus" size={15} />
          New Patient
        </Link>
        {active ? (
          <>
            <button
              type="button"
              className="button button--danger"
              onClick={onStop}
              disabled={stopping}
            >
              <Icon name="stop" size={15} />
              {stopping ? 'Stopping…' : 'Stop Recording'}
            </button>
            <button
              type="button"
              className="button button--ghost button--icon-only"
              title="Pause is not supported by the device ingestion contract."
              disabled
              aria-label="Pause recording (not supported)"
            >
              <Icon name="pause" size={16} />
            </button>
          </>
        ) : (
          <Link to={analysisHref} className="button button--primary">
            <Icon name="file-text" size={15} />
            Open Analysis
          </Link>
        )}
      </div>
    </div>
  )
}
