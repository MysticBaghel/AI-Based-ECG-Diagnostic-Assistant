import type { Patient } from '@/shared/types'
import { SectionCard } from '@/shared/ui'
import { formatDate, formatDateTime, initials } from '@/shared/lib/format'

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value || '—'}</strong>
    </div>
  )
}

export function PatientInfoCard({ patient }: { patient: Patient }) {
  return (
    <SectionCard title="Patient information" subtitle="Permanent registry record">
      <div className="patient-identity">
        <span className="avatar avatar--xl">{initials(patient.full_name)}</span>
        <div>
          <strong>{patient.full_name}</strong>
          <span className="mono">{patient.patient_id}</span>
        </div>
      </div>
      <div className="kv-list">
        <InfoRow label="Phone" value={patient.phone} />
        <InfoRow label="Email" value={patient.email} />
        <InfoRow label="Date of birth" value={formatDate(patient.date_of_birth)} />
        <InfoRow
          label="Age / sex"
          value={`${patient.age ?? '—'} · ${patient.sex === 'unknown' ? '—' : patient.sex}`}
        />
        <InfoRow label="Last updated" value={formatDateTime(patient.updated_at)} />
      </div>
      {patient.notes && <p className="patient-card__notes">{patient.notes}</p>}
      <p className="muted small">
        The patient does not have a login account. Access is limited to authenticated operators
        of this installation.
      </p>
    </SectionCard>
  )
}
