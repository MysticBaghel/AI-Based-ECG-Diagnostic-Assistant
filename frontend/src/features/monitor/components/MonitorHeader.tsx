import { PageHeader } from '@/shared/ui'
import { Icon } from '@/shared/icons/Icon'
import type { Session } from '@/shared/types'
import type { ConnectionState } from '../hooks/useLiveMonitor'

export function MonitorHeader({
  session,
  connection,
  rate,
}: {
  session: Session
  connection: ConnectionState
  rate: number | null
}) {
  const connected = connection === 'live'

  return (
    <div className="monitor-header">
      <PageHeader title="Live ECG Monitor" description="Real-time ECG signal from connected device" />
      <div className="monitor-header__badges">
        <span className="status-chip status-chip--neutral">
          <span className={`status-dot ${connected ? 'status-dot--ok' : 'status-dot--bad'}`} />
          {session.device_name}
        </span>
        <span className={`status-chip${connected ? '' : ' status-chip--bad'}`}>
          {connected ? 'Connected' : connection === 'connecting' ? 'Connecting' : 'Reconnecting'}
        </span>
        {rate && (
          <span className="status-chip status-chip--neutral">
            <Icon name="clock" size={12} />
            {rate} Hz
          </span>
        )}
      </div>
    </div>
  )
}
