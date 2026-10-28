import { Link } from 'react-router-dom'

import type { Patient, Session } from '@/shared/types'
import { Icon } from '@/shared/icons/Icon'
import { RowMenu } from '@/shared/ui/RowMenu'
import { formatDate } from '@/shared/lib/format'

export function PatientTable({
  rows,
  latest,
  onStart,
  onOpenSession,
}: {
  rows: Patient[]
  latest: Map<number, Session>
  onStart: (patient: Patient) => void
  onOpenSession: (session: Session) => void
}) {
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>Patient ID</th>
            <th>Name</th>
            <th>Phone</th>
            <th>Age</th>
            <th>Gender</th>
            <th>Last ECG</th>
            <th>Records</th>
            <th aria-label="Actions" />
          </tr>
        </thead>
        <tbody>
          {rows.map((patient) => {
            const last = latest.get(patient.id)
            return (
              <tr key={patient.id}>
                <td>
                  <span className="mono">{patient.patient_id}</span>
                </td>
                <td>
                  <Link to={`/patients/${patient.id}`} className="table__primary">
                    {patient.full_name}
                  </Link>
                </td>
                <td>{patient.phone || '—'}</td>
                <td>{patient.age ?? '—'}</td>
                <td>
                  {patient.sex === 'unknown'
                    ? '—'
                    : patient.sex.charAt(0).toUpperCase() + patient.sex.slice(1)}
                </td>
                <td>{last ? formatDate(last.start_time) : '—'}</td>
                <td>{patient.session_count}</td>
                <td className="table__action">
                  <RowMenu label={`Actions for ${patient.full_name}`}>
                    <Link to={`/patients/${patient.id}`}>
                      <Icon name="user" size={14} />
                      View profile
                    </Link>
                    <button type="button" onClick={() => onStart(patient)}>
                      <Icon name="pulse" size={14} />
                      Start ECG
                    </button>
                    {patient.session_count > 0 && (
                      <button type="button" onClick={() => last && onOpenSession(last)}>
                        <Icon name="activity" size={14} />
                        Open last ECG
                      </button>
                    )}
                  </RowMenu>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
