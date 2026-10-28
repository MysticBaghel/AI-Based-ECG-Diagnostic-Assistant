import type { Session } from '@/shared/types'
import { Icon } from '@/shared/icons/Icon'
import { Badge, EmptyState, SectionCard, Spinner } from '@/shared/ui'
import { SessionTable } from '@/features/sessions/components/SessionList'
import { formatDateTime } from '@/shared/lib/format'

export function SessionHistoryCard({
  sessions,
  loading,
  downloading,
  onDownload,
}: {
  sessions: Session[]
  loading: boolean
  downloading: string | null
  onDownload: (session: Session) => void
}) {
  const withReports = sessions.filter((session) => session.report_count > 0)

  return (
    <SectionCard
      title="ECG history"
      subtitle="Every session, its analysis state and its reports"
      actions={<Badge tone="info" dot={false}>{sessions.length} sessions</Badge>}
      flush
    >
      {loading ? (
        <Spinner label="Loading session history…" />
      ) : sessions.length === 0 ? (
        <EmptyState
          icon="pulse"
          title="No ECG sessions yet"
          description="Start the first recording for this patient. It will appear here with its waveform, analysis and PDF report."
        />
      ) : (
        <>
          <SessionTable sessions={sessions} />
          <div className="report-downloads">
            <span className="muted small">Download an existing report:</span>
            {withReports.map((session) => (
              <button
                type="button"
                key={session.id}
                className="button button--ghost button--sm"
                onClick={() => onDownload(session)}
                disabled={downloading === session.id}
              >
                <Icon name="copy" size={14} />
                {downloading === session.id
                  ? 'Preparing…'
                  : `${formatDateTime(session.start_time)} · PDF`}
              </button>
            ))}
          </div>
        </>
      )}
    </SectionCard>
  )
}
