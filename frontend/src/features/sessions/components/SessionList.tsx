import { Link } from 'react-router-dom'

import type { AnalysisState, Session } from '@/shared/types'
import { useNow } from '@/shared/hooks/useNow'
import { elapsedSeconds, formatDateTime, formatDuration } from '@/shared/lib/format'
import { Icon } from '@/shared/icons/Icon'
import { Badge, SessionBadge, type Tone } from '@/shared/ui'

const ANALYSIS_META: Record<AnalysisState, { tone: Tone; label: string }> = {
  not_run: { tone: 'neutral', label: 'not run' },
  pending: { tone: 'info', label: 'pending' },
  completed: { tone: 'ok', label: 'analysis ready' },
  unusable: { tone: 'warn', label: 'signal unusable' },
  failed: { tone: 'bad', label: 'analysis failed' },
  unavailable: { tone: 'warn', label: 'unavailable' },
}

export function AnalysisBadge({ status }: { status: AnalysisState }) {
  const meta = ANALYSIS_META[status] ?? ANALYSIS_META.not_run
  return (
    <Badge tone={meta.tone} dot={false}>
      {meta.label}
    </Badge>
  )
}

export function SessionTable({ sessions }: { sessions: Session[] }) {
  const now = useNow(1000)

  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>Patient</th>
            <th>Started</th>
            <th>Duration</th>
            <th>Recording</th>
            <th>Analysis</th>
            <th>Report</th>
            <th aria-label="Open" />
          </tr>
        </thead>
        <tbody>
          {sessions.map((session) => {
            const active = session.status === 'active'
            const duration = elapsedSeconds(session.start_time, session.end_time)
            void now
            return (
              <tr key={session.id}>
                <td>
                  <div className="table__primary">{session.patient_name}</div>
                  <div className="table__secondary mono">
                    {session.patient_code} · {session.device_name}
                  </div>
                </td>
                <td>{formatDateTime(session.start_time)}</td>
                <td>
                  {formatDuration(duration)}
                  {active && <span className="table__live">live</span>}
                </td>
                <td>
                  <SessionBadge status={session.status} />
                </td>
                <td>
                  <AnalysisBadge status={session.analysis_status} />
                </td>
                <td>
                  {session.report_count > 0 ? (
                    <Badge tone="ok" dot={false}>
                      {session.report_count} PDF
                    </Badge>
                  ) : (
                    <span className="muted small">—</span>
                  )}
                </td>
                <td className="table__action">
                  <Link
                    to={active ? `/monitor/${session.id}` : `/sessions/${session.id}`}
                    className="button button--ghost button--sm"
                  >
                    {active ? 'Open monitor' : 'Open analysis'}
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
  return (
    <div className="session-cards">
      {sessions.map((session) => {
        const active = session.status === 'active'
        return (
          <Link
            key={session.id}
            to={active ? `/monitor/${session.id}` : `/sessions/${session.id}`}
            className={`session-card${active ? ' session-card--active' : ''}`}
          >
            <div className="session-card__top">
              <span className="avatar avatar--sm">
                {session.patient_name.slice(0, 2).toUpperCase()}
              </span>
              <span>
                <strong>{session.patient_name}</strong>
                <small>
                  {session.patient_code} · {session.device_name}
                </small>
              </span>
              <SessionBadge status={session.status} />
            </div>
            <div className="session-card__meta">
              <span>
                <Icon name="clock" size={14} />
                {formatDateTime(session.start_time)}
              </span>
              <span>{session.analysis_status.replace('_', ' ')}</span>
            </div>
            <span className="session-card__cta">
              {active ? 'Open live monitor' : 'Open analysis & report'}
              <Icon name="chevron-right" size={15} />
            </span>
          </Link>
        )
      })}
    </div>
  )
}
