import { InfoCard } from '@/shared/ui/InfoCard'
import type { Patient, Session } from '@/shared/types'

export function PatientInfoCard({
  session,
  patient,
}: {
  session: Session
  patient: Patient | null
}) {
  return (
    <InfoCard
      title="Patient Information"
      items={[
        { label: 'Patient ID', value: session.patient_code },
        { label: 'Name', value: session.patient_name },
        {
          label: 'Age / Gender',
          value: patient
            ? `${patient.age ?? '—'} / ${patient.sex === 'unknown' ? '—' : patient.sex}`
            : '—',
        },
        { label: 'Phone', value: patient?.phone || '—' },
      ]}
    />
  )
}
