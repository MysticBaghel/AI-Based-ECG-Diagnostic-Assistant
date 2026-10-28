import { Link } from 'react-router-dom'

import type { ConnectionState } from '../hooks/useLiveMonitor'

export function MonitorFooter({
  connection,
  frames,
  sessionId,
  active,
  analysisHref,
}: {
  connection: ConnectionState
  frames: number
  sessionId: string
  active: boolean
  analysisHref: string
}) {
  const connected = connection === 'live'
  return (
    <div className="monitor-footer">
      <span>
        <span className={`status-dot ${connected ? 'status-dot--ok' : 'status-dot--bad'}`} />
        WebSocket {connected ? 'live' : connection}
      </span>
      <span>{frames} frames</span>
      <span className="mono">Session {sessionId}</span>
      <span className="monitor-footer__right">
        {active ? (
          <span>
            Simulator: add <code>--session-id {sessionId}</code> with the device token.
          </span>
        ) : (
          <Link to={analysisHref}>Open analysis & report</Link>
        )}
      </span>
    </div>
  )
}
