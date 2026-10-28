import { Link } from 'react-router-dom'

import type { Session } from '../api/types'
import { useNow } from '../hooks/useNow'
import { elapsedSeconds, formatDateTime, formatDuration } from '../lib/format'
import { Icon } from './Icon'
import { SessionBadge } from './ui'

export function SessionTable({ sessions }: { sessions: Session[] }) {
  const now = useNow(1000)

  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>Patient</th>
            <th>Device</th>
            <th>Started</th>
            <th>Duration</th>
            <th>Status</th>
            <th aria-label="Open" />
          </tr>
        </thead>
        <tbody>
          {sessions.map((session) => {
            const active = session.status === 'active'
            const duration = elapsedSeconds(session.start_time, session.end_time)
            // `now` is referenced so the duration re-renders every second.
            void now
            return (
              <tr key={session.id}>
                <td>
                  <div className="table__primary">{session.patient_name}</div>
                  <div className="table__secondary mono">{session.id.slice(0, 8)}</div>
                </td>
                <td>{session.device_name}</td>
                <td>{formatDateTime(session.start_time)}</td>
                <td>
                  {formatDuration(duration)}
                  {active && <span className="table__live">live</span>}
                </td>
                <td>
                  <SessionBadge status={session.status} />
                </td>
                <td className="table__action">
                  <Link
                    to={active ? `/live/${session.id}` : `/sessions/${session.id}`}
                    className="button button--ghost button--sm"
                  >
                    {active ? 'Watch live' : 'Recording'}
                    <Icon name="chevron-right" size={14} />
                  </Link>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export function SessionCards({ sessions }: { sessions: Session[] }) {
  const now = useNow(1000)

  return (
    <div className="session-cards">
      {sessions.map((session) => {
        const active = session.status === 'active'
        const duration = elapsedSeconds(session.start_time, session.end_time)
        void now
        return (
          <Link
            key={session.id}
            to={active ? `/live/${session.id}` : `/sessions/${session.id}`}
            className={`session-card${active ? ' session-card--active' : ''}`}
          >
            <div className="session-card__top">
              <span className="avatar avatar--sm">{session.patient_name.slice(0, 2)}</span>
              <span>
                <strong>{session.patient_name}</strong>
                <small>{session.device_name}</small>
              </span>
              <SessionBadge status={session.status} />
            </div>
            <div className="session-card__meta">
              <span>
                <Icon name="clock" size={14} />
                {formatDuration(duration)}
              </span>
              <span>{formatDateTime(session.start_time)}</span>
            </div>
            <span className="session-card__cta">
              {active ? 'Watch live' : 'Open recording'}
              <Icon name="chevron-right" size={15} />
            </span>
          </Link>
        )
      })}
    </div>
  )
}
