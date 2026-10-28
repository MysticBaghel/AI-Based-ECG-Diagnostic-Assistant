import { Link } from 'react-router-dom'

import { useAuth } from '../auth/useAuth'
import { Icon } from '../components/Icon'
import { SessionCards, SessionTable } from '../components/SessionList'
import {
  Badge,
  EmptyState,
  ErrorBanner,
  PageHeader,
  SectionCard,
  Spinner,
  StatCard,
} from '../components/ui'
import { useDeviceStatus, useDevices, usePatients, useSessions } from '../hooks/useData'

function ProviderDashboard() {
  const patients = usePatients()
  const devices = useDevices()
  const sessions = useSessions()
  const status = useDeviceStatus()

  const allSessions = sessions.data ?? []
  const active = allSessions.filter((session) => session.status === 'active')
  const online = (status.data?.devices ?? []).filter((device) => device.online).length
  const loading = patients.loading && devices.loading && sessions.loading

  return (
    <>
      <PageHeader
        eyebrow="Phase 4 · screening dashboard"
        title="Monitoring overview"
        description="Start a session, watch the live waveform, then find the recording in history. Every number here is telemetry, not a diagnosis."
        actions={
          <Link to="/patients" className="button button--primary">
            <Icon name="plus" size={16} />
            Start a session
          </Link>
        }
      />

      {(patients.error || devices.error || sessions.error) && (
        <ErrorBanner
          message={patients.error ?? devices.error ?? sessions.error ?? ''}
          onRetry={() => {
            patients.refresh()
            devices.refresh()
            sessions.refresh()
          }}
        />
      )}

      {loading ? (
        <Spinner label="Loading the monitoring overview…" />
      ) : (
        <>
          <div className="stats">
            <StatCard
              icon="sessions"
              label="Active sessions"
              value={active.length}
              hint={`${allSessions.length} total`}
              tone={active.length > 0 ? 'ok' : 'neutral'}
            />
            <StatCard
              icon="users"
              label="Patients in view"
              value={patients.data?.length ?? 0}
              hint="role-scoped"
            />
            <StatCard
              icon="devices"
              label="Devices"
              value={devices.data?.length ?? 0}
              hint="registered in Django"
            />
            <StatCard
              icon="wifi"
              label="Devices online"
              value={online}
              hint={`heartbeat ≤ ${status.data?.threshold_seconds ?? 120}s`}
              tone={online > 0 ? 'ok' : 'warn'}
            />
          </div>

          <div className="dashboard-grid">
            <SectionCard
              title="Live now"
              subtitle="Sessions currently accepting telemetry"
              actions={
                <Link to="/live" className="button button--ghost button--sm">
                  All live views
                  <Icon name="chevron-right" size={14} />
                </Link>
              }
              flush
            >
              {active.length === 0 ? (
                <EmptyState
                  icon="pulse"
                  title="No active session"
                  description={
                    <>
                      Start a session for a patient, then run the simulator to send
                      synthetic ECG and vitals. A session must be active before the device
                      may upload.
                    </>
                  }
                  action={
                    <Link to="/patients" className="button button--primary">
                      Choose a patient
                    </Link>
                  }
                />
              ) : (
                <SessionTable sessions={active} />
              )}
            </SectionCard>

            <SectionCard title="How the demo flows" subtitle="Three steps, no hardware">
              <ol className="steps">
                <li>
                  <span className="steps__number">1</span>
                  <div>
                    <strong>Start a session</strong>
                    <p>Django creates it and pushes it to FastAPI's session registry.</p>
                  </div>
                </li>
                <li>
                  <span className="steps__number">2</span>
                  <div>
                    <strong>Run the simulator</strong>
                    <p>
                      <code>python -m simulator --duration 60 --ecg</code> posts four
                      vitals and 200 Hz ECG chunks with a device token.
                    </p>
                  </div>
                </li>
                <li>
                  <span className="steps__number">3</span>
                  <div>
                    <strong>Watch, then revisit</strong>
                    <p>
                      The live monitor follows <code>/ws/sensor</code>; history reads the
                      stored chunks back over REST.
                    </p>
                  </div>
                </li>
              </ol>
            </SectionCard>
          </div>

          <SectionCard
            title="Recent sessions"
            subtitle="Newest first, scoped to the patients you may see"
            actions={
              <Link to="/sessions" className="button button--ghost button--sm">
                Session history
                <Icon name="chevron-right" size={14} />
              </Link>
            }
            flush
          >
            {allSessions.length === 0 ? (
              <EmptyState
                icon="sessions"
                title="No sessions yet"
                description="Once you start a monitoring session it appears here, with a link to its recording."
              />
            ) : (
              <SessionTable sessions={allSessions.slice(0, 6)} />
            )}
          </SectionCard>
        </>
      )}
    </>
  )
}

function PatientDashboard() {
  const { user } = useAuth()
  const patients = usePatients()
  const sessions = useSessions()
  const status = useDeviceStatus()

  const allSessions = sessions.data ?? []
  const active = allSessions.filter((session) => session.status === 'active')
  const online = (status.data?.devices ?? []).filter((device) => device.online).length
  const profile = patients.data?.find((patient) => patient.user === user?.id)

  return (
    <>
      <PageHeader
        eyebrow="Phase 4 · screening dashboard"
        title={`Hello, ${user?.username ?? 'there'}`}
        description="Your monitoring sessions, live vitals and past recordings. This is a screening aid, not a medical diagnosis."
      />

      {(patients.error || sessions.error) && (
        <ErrorBanner
          message={patients.error ?? sessions.error ?? ''}
          onRetry={() => {
            patients.refresh()
            sessions.refresh()
          }}
        />
      )}

      <div className="stats">
        <StatCard
          icon="sessions"
          label="Your active sessions"
          value={active.length}
          hint={`${allSessions.length} total`}
          tone={active.length > 0 ? 'ok' : 'neutral'}
        />
        <StatCard
          icon="devices"
          label="Devices online"
          value={online}
          hint="on your sessions"
          tone={online > 0 ? 'ok' : 'warn'}
        />
        <StatCard
          icon="shield"
          label="Access"
          value="Read-only"
          hint="patients cannot start or stop sessions"
        />
      </div>

      <div className="dashboard-grid">
        <SectionCard
          title="Live now"
          subtitle="A session your care team started"
          flush
        >
          {active.length === 0 ? (
            <EmptyState
              icon="pulse"
              title="Nothing is streaming right now"
              description="When your care team starts a session and the device connects, it will appear here."
            />
          ) : (
            <SessionCards sessions={active} />
          )}
        </SectionCard>

        <SectionCard title="Your profile" subtitle="Identity from Django">
          {profile ? (
            <div className="kv-list">
              <div>
                <span>Name</span>
                <strong>{profile.username}</strong>
              </div>
              <div>
                <span>Email</span>
                <strong>{profile.email || '—'}</strong>
              </div>
              <div>
                <span>Date of birth</span>
                <strong>{profile.date_of_birth ?? '—'}</strong>
              </div>
              <div>
                <span>Notes</span>
                <strong>{profile.notes || '—'}</strong>
              </div>
            </div>
          ) : (
            <Spinner label="Loading profile…" />
          )}
        </SectionCard>
      </div>

      <SectionCard
        title="Your session history"
        subtitle="Open a completed session to view its waveform"
        actions={
          <Badge tone="info" dot={false}>
            {allSessions.length} sessions
          </Badge>
        }
        flush
      >
        {allSessions.length === 0 ? (
          <EmptyState
            icon="sessions"
            title="No sessions yet"
            description="Your care team starts sessions on your behalf."
          />
        ) : (
          <SessionTable sessions={allSessions.slice(0, 8)} />
        )}
      </SectionCard>
    </>
  )
}

export function DashboardPage() {
  const { user } = useAuth()
  return user?.role === 'patient' ? <PatientDashboard /> : <ProviderDashboard />
}
