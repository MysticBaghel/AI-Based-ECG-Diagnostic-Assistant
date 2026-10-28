import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { ApiError, api } from '../api/client'
import type { Session } from '../api/types'
import { useAuth } from '../auth/useAuth'
import { HeartbeatBadge } from '../components/DeviceStatusBadge'
import { EcgChart } from '../components/EcgChart'
import { Icon } from '../components/Icon'
import { SessionCards } from '../components/SessionList'
import {
  Badge,
  EmptyState,
  ErrorBanner,
  Notice,
  PageHeader,
  SessionBadge,
  Spinner,
  StatCard,
  type Tone,
} from '../components/ui'
import { statusFor, useDeviceStatus, useSession, useSessions } from '../hooks/useData'
import { useLiveMonitor, type ConnectionState } from '../hooks/useLiveMonitor'
import { useNow } from '../hooks/useNow'
import {
  elapsedSeconds,
  formatDateTime,
  formatDuration,
  formatRelative,
  SENSOR_ORDER,
} from '../lib/format'
import { VitalCard } from '../components/VitalCard'

const CONNECTION: Record<ConnectionState, { tone: Tone; label: string }> = {
  connecting: { tone: 'info', label: 'Connecting' },
  live: { tone: 'ok', label: 'Live' },
  reconnecting: { tone: 'warn', label: 'Reconnecting' },
  closed: { tone: 'neutral', label: 'Closed' },
  error: { tone: 'bad', label: 'Socket error' },
}

function LiveIndex() {
  const sessions = useSessions()
  const active = (sessions.data ?? []).filter((session) => session.status === 'active')
  const { user } = useAuth()
  const canManage = user?.role === 'doctor' || user?.role === 'admin'

  return (
    <>
      <PageHeader
        eyebrow="Live"
        title="Live monitor"
        description="Pick an active session to follow its WebSocket. The socket carries readings and ECG chunk announcements; each chunk's samples are fetched over REST."
        actions={
          canManage && (
            <Link to="/patients" className="button button--primary">
              <Icon name="plus" size={16} />
              Start a session
            </Link>
          )
        }
      />

      {sessions.error && (
        <ErrorBanner message={sessions.error} onRetry={sessions.refresh} />
      )}

      {sessions.loading ? (
        <Spinner label="Looking for active sessions…" />
      ) : active.length === 0 ? (
        <EmptyState
          icon="pulse"
          title="No active session to watch"
          description={
            canManage
              ? 'Start a session for a patient and a device. Then connect the device or run the simulator with that session id.'
              : 'Your care team has not started a session yet.'
          }
          action={
            canManage ? (
              <Link to="/patients" className="button button--primary">
                Choose a patient
              </Link>
            ) : undefined
          }
        />
      ) : (
        <SessionCards sessions={active} />
      )}

      <div className="dashboard-grid dashboard-grid--narrow">
        <Notice tone="info" icon="pulse">
          <strong>The socket is a viewer, not a recorder.</strong> If you open the monitor late
          you still get the last 20 scalar readings in a snapshot, and the waveform is seeded
          from the stored chunks. Reloading does not lose the session.
        </Notice>
        <Notice tone="warn" icon="alert">
          <strong>Screening aid, not a medical diagnosis.</strong> A waveform on this screen
          is raw telemetry. Phase 5 adds deterministic DSP and an ML inference slot.
        </Notice>
      </div>
    </>
  )
}

function ConnectionBadge({ state }: { state: ConnectionState }) {
  const meta = CONNECTION[state]
  return (
    <Badge tone={meta.tone} pulse={state === 'live' || state === 'reconnecting'}>
      {meta.label}
    </Badge>
  )
}

function SessionPanel({
  session,
  onStop,
  stopping,
  canStop,
}: {
  session: Session
  onStop: () => void
  stopping: boolean
  canStop: boolean
}) {
  return (
    <section className="panel">
      <div className="panel__header">
        <div>
          <h2>Session</h2>
          <p>Identity and lifecycle</p>
        </div>
        <SessionBadge status={session.status} />
      </div>
      <div className="panel__body">
        <div className="kv-list">
          <div>
            <span>Patient</span>
            <strong>{session.patient_name}</strong>
          </div>
          <div>
            <span>Device</span>
            <strong>{session.device_name}</strong>
          </div>
          <div>
            <span>Started</span>
            <strong>{formatDateTime(session.start_time)}</strong>
          </div>
          <div>
            <span>Session ID</span>
            <strong className="mono">{session.id}</strong>
          </div>
        </div>

        {canStop && session.status === 'active' && (
          <button
            type="button"
            className="button button--danger button--block"
            onClick={onStop}
            disabled={stopping}
          >
            <Icon name="stop" size={15} />
            {stopping ? 'Stopping…' : 'Stop session'}
          </button>
        )}

        {session.status !== 'active' && (
          <Link to={`/sessions/${session.id}`} className="button button--ghost button--block">
            <Icon name="sessions" size={15} />
            Open stored recording
          </Link>
        )}
      </div>
    </section>
  )
}

function Monitor({ sessionId }: { sessionId: string }) {
  const { user } = useAuth()
  const session = useSession(sessionId)
  const live = useLiveMonitor(sessionId)
  const status = useDeviceStatus()
  const now = useNow(1000)
  const [stopError, setStopError] = useState<string | null>(null)
  const [stopping, setStopping] = useState(false)

  const canManage = user?.role === 'doctor' || user?.role === 'admin'
  const current = session.data
  const heartbeat = current ? statusFor(status.data, current.device) : null
  const elapsed = current
    ? elapsedSeconds(current.start_time, current.end_time ?? now.toISOString())
    : 0
  const lastChunk = live.chunks[live.chunks.length - 1]
  const rate = lastChunk?.sample_rate_hz ?? null
  const lastFrame = live.lastFrameAt ? formatRelative(new Date(live.lastFrameAt).toISOString()) : '—'

  async function stopSession() {
    if (!current) return
    if (!window.confirm('Stop this session? The device will be refused further uploads.')) {
      return
    }
    setStopping(true)
    setStopError(null)
    try {
      await api.stopSession(current.id)
      session.refresh()
    } catch (caught) {
      setStopError(caught instanceof ApiError ? caught.message : 'Could not stop the session.')
    } finally {
      setStopping(false)
    }
  }

  if (session.loading) return <Spinner label="Loading session…" />
  if (session.error) {
    return <ErrorBanner message={session.error} onRetry={session.refresh} />
  }
  if (!current) return null

  return (
    <>
      <div className="monitor-header">
        <div>
          <Link to="/live" className="back-link">
            <Icon name="chevron-left" size={15} />
            All live sessions
          </Link>
          <PageHeader
            eyebrow="Live telemetry"
            title={`${current.patient_name} · ${current.device_name}`}
            description={`Session ${current.id}`}
          />
        </div>
        <div className="monitor-header__badges">
          <ConnectionBadge state={live.connection} />
          <HeartbeatBadge status={heartbeat} />
          <SessionBadge status={current.status} />
        </div>
      </div>

      {stopError && <ErrorBanner message={stopError} />}
      {live.socketError && (
        <ErrorBanner
          message={live.socketError}
          onRetry={() => {
            live.reconnect()
          }}
        />
      )}
      {live.chunkError && (
        <ErrorBanner message={live.chunkError} onRetry={() => live.reconnect()} />
      )}

      <div className="stats stats--four">
        <StatCard
          icon="clock"
          label="Session time"
          value={formatDuration(elapsed)}
          hint={formatDateTime(current.start_time)}
        />
        <StatCard
          icon="pulse"
          label="ECG chunks"
          value={live.chunks.length}
          hint={rate ? `${rate} Hz · ${live.series.sampleCount} samples in view` : 'waiting'}
          tone={live.chunks.length > 0 ? 'ok' : 'neutral'}
        />
        <StatCard
          icon="activity"
          label="Readings seen"
          value={live.readings.count}
          hint={`${live.frames} socket frames`}
        />
        <StatCard
          icon="wifi"
          label="Last frame"
          value={lastFrame}
          hint={
            live.lastFrameAt
              ? new Date(live.lastFrameAt).toLocaleTimeString()
              : 'no frame yet'
          }
          tone={live.connection === 'live' ? 'ok' : 'warn'}
        />
      </div>

      <div className="monitor-grid">
        <section className="panel panel--ecg">
          <div className="panel__header">
            <div>
              <h2>ECG waveform</h2>
              <p>Single lead · rolling 12 second window · millivolts</p>
            </div>
            <div className="panel__actions">
              <Badge tone="info" dot={false}>
                {live.series.sampleCount} samples
              </Badge>
            </div>
          </div>
          <div className="panel__body">
            <EcgChart
              x={live.series.x}
              y={live.series.y}
              height={310}
              emptyLabel={
                live.initialLoading
                  ? 'Seeding the waveform from stored chunks…'
                  : 'Waiting for the first ECG chunk. Run the simulator with --ecg.'
              }
            />
            <div className="ecg-meta">
              <span>
                <Icon name="activity" size={14} /> {live.chunks.length} chunks
              </span>
              <span>
                <Icon name="clock" size={14} /> {live.series.durationSeconds.toFixed(1)} s in
                view
              </span>
              <span>
                <Icon name="spark" size={14} /> BPM analysis arrives in Phase 5
              </span>
            </div>
          </div>
        </section>

        <div className="monitor-side">
          <SessionPanel
            session={current}
            onStop={() => void stopSession()}
            stopping={stopping}
            canStop={canManage}
          />

          <section className="panel">
            <div className="panel__header">
              <div>
                <h2>Connection</h2>
                <p>WebSocket /ws/sensor</p>
              </div>
            </div>
            <div className="panel__body">
              <div className="kv-list">
                <div>
                  <span>State</span>
                  <strong>
                    <ConnectionBadge state={live.connection} />
                  </strong>
                </div>
                <div>
                  <span>Frames</span>
                  <strong>{live.frames}</strong>
                </div>
                <div>
                  <span>Last frame</span>
                  <strong>{lastFrame}</strong>
                </div>
                <div>
                  <span>Viewers' token</span>
                  <strong>user access · query string</strong>
                </div>
              </div>
              {live.connection !== 'live' && (
                <button
                  type="button"
                  className="button button--ghost button--block"
                  onClick={() => live.reconnect()}
                >
                  <Icon name="refresh" size={15} />
                  Reconnect now
                </button>
              )}
            </div>
          </section>
        </div>
      </div>

      <section className="vitals-grid" aria-label="Latest vital signs">
        {SENSOR_ORDER.map((sensor) => (
          <VitalCard
            key={sensor}
            sensor={sensor}
            reading={live.readings.latest[sensor]}
            history={live.readings.history[sensor] ?? []}
            live={live.connection === 'live'}
          />
        ))}
      </section>

      <div className="dashboard-grid dashboard-grid--narrow">
        <Notice tone="info" icon="spark">
          <strong>No beat detection on this screen.</strong> The chart draws the samples the
          device stored. Phase 5 adds the 50 Hz notch, 0.5–40 Hz band-pass, R-peak detection
          and a signal-quality check behind a stable interface.
        </Notice>
        <section className="panel">
          <div className="panel__header">
            <div>
              <h2>Send data to this session</h2>
              <p>The simulator uses the same contract as the ESP32</p>
            </div>
          </div>
          <div className="panel__body">
            <p className="small muted">
              Use the device token saved when the device was registered (rotate it on the
              Devices page if it is lost):
            </p>
            <pre className="code-block">
              <code>{`python -m simulator --session-id ${current.id} \\
  --device-token <DEVICE_TOKEN> --ecg --duration 60`}</code>
            </pre>
            <p className="small muted">
              Or let the simulator mint its own session with{' '}
              <code>backend/django/scripts/mint_new_run.py</code>; it will appear in this
              dashboard's session list.
            </p>
          </div>
        </section>
      </div>
    </>
  )
}

export function LivePage() {
  const { sessionId } = useParams<{ sessionId: string }>()
  return sessionId ? <Monitor key={sessionId} sessionId={sessionId} /> : <LiveIndex />
}
