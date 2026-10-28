import { Link } from 'react-router-dom'

import type { Session } from '@/shared/types'
import { Icon } from '@/shared/icons/Icon'
import { SectionCard } from '@/shared/ui'
import { AnalysisBadge } from '@/features/sessions/components/SessionList'
import { formatDateTime } from '@/shared/lib/format'

export function LatestRecordingCard({
  latest,
  onStart,
}: {
  latest: Session | undefined
  onStart: () => void
}) {
  return (
    <SectionCard title="Recording" subtitle="Start a new ECG or review the latest">
      <div className="stack">
        {latest ? (
          <div className="latest-session">
            <div>
              <span className="muted small">Most recent</span>
              <strong>{formatDateTime(latest.start_time)}</strong>
              <span className="muted small">
                {latest.device_name} · {latest.status}
              </span>
            </div>
            <div className="button-row">
              <AnalysisBadge status={latest.analysis_status} />
              <Link
                to={latest.status === 'active' ? `/monitor/${latest.id}` : `/sessions/${latest.id}`}
                className="button button--ghost button--sm"
              >
                Open
                <Icon name="chevron-right" size={14} />
              </Link>
            </div>
          </div>
        ) : (
          <p className="muted small">
            No recording yet. Start one with a registered device; the simulator can supply the
            signal if no ESP32 is connected.
          </p>
        )}
        <button type="button" className="button button--primary button--block" onClick={onStart}>
          <Icon name="pulse" size={16} />
          Start a new ECG recording
        </button>
        <p className="muted small">
          A returning patient reuses this record. Never register a duplicate because the phone
          number looks similar — search first.
        </p>
      </div>
    </SectionCard>
  )
}
