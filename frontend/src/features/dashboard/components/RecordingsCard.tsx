import { EmptyState, ErrorBanner, SectionCard, Spinner } from '@/shared/ui'
import { Icon } from '@/shared/icons/Icon'
import { SessionTable } from '@/features/sessions/components/SessionList'
import type { Session } from '@/shared/types'

export function RecordingsCard({
  sessions,
  recent,
  loading,
  refreshing,
  error,
  onRefresh,
}: {
  sessions: Session[]
  recent: Session[]
  loading: boolean
  refreshing: boolean
  error: string | null
  onRefresh: () => void
}) {
  return (
    <SectionCard
      title="Recordings"
      subtitle="Newest first. Active sessions open the live monitor; completed ones open analysis and reports."
      actions={
        <button
          type="button"
          className="button button--ghost button--sm"
          onClick={onRefresh}
          disabled={refreshing}
        >
          <Icon name="refresh" size={14} />
          {refreshing ? 'Refreshing…' : 'Refresh'}
        </button>
      }
      flush
    >
      {error && <ErrorBanner message={error} onRetry={onRefresh} />}
      {loading ? (
        <Spinner label="Loading recordings…" />
      ) : sessions.length === 0 ? (
        <EmptyState
          icon="pulse"
          title="No ECG recordings yet"
          description="Find a patient above, start a recording, then run the simulator or connect the ESP32. The waveform and report will appear here."
        />
      ) : (
        <SessionTable sessions={recent} />
      )}
    </SectionCard>
  )
}
