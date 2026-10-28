import { InfoCard } from '@/shared/ui/InfoCard'
import { formatDateTime, formatDuration } from '@/shared/lib/format'
import type { Session } from '@/shared/types'

export function SessionInfoCard({
  session,
  reportCount,
}: {
  session: Session
  reportCount: number
}) {
  return (
    <InfoCard
      title="Session Details"
      items={[
        { label: 'Session ID', value: session.id },
        { label: 'Date', value: formatDateTime(session.start_time) },
        { label: 'Device', value: session.device_name },
        { label: 'Duration', value: formatDuration(session.duration_seconds) },
        {
          label: 'Sampling Rate',
          value: session.sample_rate_hz ? `${session.sample_rate_hz} Hz` : '—',
        },
        { label: 'Report Versions', value: String(reportCount) },
      ]}
    />
  )
}
