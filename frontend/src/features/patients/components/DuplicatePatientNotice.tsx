import type { Patient } from '@/shared/types'
import { Notice } from '@/shared/ui'

export function DuplicatePatientNotice({ duplicates }: { duplicates: Patient[] }) {
  if (duplicates.length === 0) return null
  return (
    <Notice tone="warn" icon="alert">
      <strong>A patient with this phone number already exists.</strong>
      <div className="duplicate-list">
        {duplicates.map((match) => (
          <div key={match.id} className="duplicate-row">
            <span>
              <strong>{match.full_name}</strong> · {match.patient_id}
            </span>
            <span className="muted small">
              {match.phone || 'no phone'} · {match.session_count} session
              {match.session_count === 1 ? '' : 's'}
            </span>
          </div>
        ))}
      </div>
      <span className="small">
        Open the existing profile instead if this is the same person. If it is a different
        person who shares the number, confirm below.
      </span>
    </Notice>
  )
}
