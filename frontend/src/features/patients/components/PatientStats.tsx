import type { Session } from '@/shared/types'
import { StatCard } from '@/shared/ui'
import { formatDateTime } from '@/shared/lib/format'

export function PatientStats({ sessions }: { sessions: Session[] }) {
  return (
    <div className="stats stats--four">
      <StatCard icon="sessions" label="Recordings" value={sessions.length} hint="all time" />
      <StatCard
        icon="activity"
        label="Analysed"
        value={sessions.filter((session) => session.analysis_status === 'completed').length}
        hint="DSP completed"
      />
      <StatCard
        icon="shield"
        label="Reports"
        value={sessions.reduce((sum, session) => sum + session.report_count, 0)}
        hint="stored PDFs"
      />
      <StatCard
        icon="clock"
        label="Latest recording"
        value={sessions[0] ? formatDateTime(sessions[0].start_time) : '—'}
        hint={sessions[0]?.status ?? 'none yet'}
      />
    </div>
  )
}
