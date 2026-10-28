import { Link, useNavigate } from 'react-router-dom'

import { useSessions } from '@/features/sessions/hooks/useSessions'
import { EmptyState, ErrorBanner, PageHeader, SessionBadge } from '@/shared/ui'
import { Icon } from '@/shared/icons/Icon'
import { formatDateTime } from '@/shared/lib/format'

export function MonitorIndexPage() {
  const navigate = useNavigate()
  const sessions = useSessions()
  const active = (sessions.data ?? []).filter((session) => session.status === 'active')
  const completed = (sessions.data ?? [])
    .filter((session) => session.status !== 'active')
    .slice(0, 6)

  return (
    <>
      <PageHeader
        title="ECG Monitor"
        description="Select an active recording or start a new one from a patient profile."
        actions={
          <Link to="/patients" className="button button--primary">
            <Icon name="plus" size={16} />
            New Patient
          </Link>
        }
      />
      {sessions.error && <ErrorBanner message={sessions.error} onRetry={sessions.refresh} />}
      {active.length === 0 ? (
        <EmptyState
          icon="activity"
          title="No active recording"
          description="Start a recording from a patient profile. The live monitor opens automatically and the simulator or ESP32 can stream into it."
          action={
            <Link to="/patients" className="button button--primary">
              Choose a patient
            </Link>
          }
        />
      ) : (
        <div className="session-cards">
          {active.map((session) => (
            <button
              key={session.id}
              type="button"
              className="session-card session-card--active"
              onClick={() => navigate(`/monitor/${session.id}`)}
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
                <span>{formatDateTime(session.start_time)}</span>
                <span>Open live monitor</span>
              </div>
            </button>
          ))}
        </div>
      )}
      {completed.length > 0 && (
        <section className="panel">
          <div className="panel__header">
            <div>
              <h2>Recent recordings</h2>
              <p>Open a completed recording for analysis and reports</p>
            </div>
          </div>
          <div className="panel__body">
            <div className="session-cards" style={{ padding: 0 }}>
              {completed.map((session) => (
                <Link key={session.id} to={`/sessions/${session.id}`} className="session-card">
                  <div className="session-card__top">
                    <span className="avatar avatar--sm">
                      {session.patient_name.slice(0, 2).toUpperCase()}
                    </span>
                    <span>
                      <strong>{session.patient_name}</strong>
                      <small>{formatDateTime(session.start_time)}</small>
                    </span>
                  </div>
                  <span className="session-card__cta">
                    Open analysis
                    <Icon name="chevron-right" size={14} />
                  </span>
                </Link>
              ))}
            </div>
          </div>
        </section>
      )}
    </>
  )
}
