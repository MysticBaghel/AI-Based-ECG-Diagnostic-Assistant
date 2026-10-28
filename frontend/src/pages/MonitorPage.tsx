import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { ApiError, api } from '../api/client'
import { HeartbeatBadge } from '../components/DeviceStatusBadge'
import { EcgChart } from '../components/EcgChart'
import { Icon } from '../components/Icon'
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
import { statusFor, useDeviceStatus, useLiveAnalysis, useSession } from '../hooks/useData'
import { useLiveMonitor, type ConnectionState } from '../hooks/useLiveMonitor'
import { useNow } from '../hooks/useNow'
import { elapsedSeconds, formatDateTime, formatDuration, formatRelative } from '../lib/format'

const CONNECTION: Record<ConnectionState, { tone: Tone; label: string }> = {
  connecting: { tone: 'info', label: 'Connecting' },
  live: { tone: 'ok', label: 'Live' },
  reconnecting: { tone: 'warn', label: 'Reconnecting' },
  closed: { tone: 'neutral', label: 'Closed' },
  error: { tone: 'bad', label: 'Socket error' },
}

function ConnectionBadge({ state }: { state: ConnectionState }) {
  const meta = CONNECTION[state]
  return (
    <Badge tone={meta.tone} pulse={state === 'live' || state === 'reconnecting'}>
      {meta.label}
    </Badge>
  )
}

function qualityTone(usable: boolean, level: string): Tone {
  if (!usable) return 'bad'
  if (level === 'good') return 'ok'
  if (level === 'fair') return 'info'
  return 'warn'
}

export function MonitorPage() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const navigate = useNavigate()
  const session = useSession(sessionId)
  const live = useLiveMonitor(sessionId ?? null)
  const status = useDeviceStatus()
  const now = useNow(1000)
  const current = session.data
  const liveAnalysis = useLiveAnalysis(
    sessionId,
    Boolean(sessionId) && current?.status === 'active',
  )
  const [stopping, setStopping] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  if (!sessionId) {
    return <EmptyState title="No recording selected" description="Open a session from the dashboard." />
  }

  if (session.loading) return <Spinner label="Loading session…" />
  if (session.error) return <ErrorBanner message={session.error} onRetry={session.refresh} />
  if (!current) return null

  const heartbeat = statusFor(status.data, current.device)
  const elapsed = elapsedSeconds(current.start_time, current.end_time ?? now.toISOString())
  const lastChunk = live.chunks[live.chunks.length - 1]
  const rate = lastChunk?.sample_rate_hz ?? current.sample_rate_hz
  const lastFrame = live.lastFrameAt
    ? formatRelative(new Date(live.lastFrameAt).toISOString())
    : '—'
  const analysis = liveAnalysis.data
  const quality = analysis?.signal.quality
  const heartRate = analysis?.measurements.heart_rate_bpm ?? null

  async function finishRecording() {
    if (!current) return
    if (
      !window.confirm(
        'Stop this recording? The device will be refused further uploads, and analysis will run on the stored signal.',
      )
    ) {
      return
    }
    setStopping(true)
    setActionError(null)
    try {
      await api.stopSession(current.id)
      try {
        await api.analyze(current.id)
      } catch (caught) {
        setActionError(
          caught instanceof ApiError
            ? `Recording stopped, but analysis failed: ${caught.message}`
            : 'Recording stopped, but analysis could not run.',
        )
      }
      navigate(`/sessions/${current.id}`)
    } catch (caught) {
      setActionError(caught instanceof ApiError ? caught.message : 'Could not stop the recording.')
    } finally {
      setStopping(false)
    }
  }

  return (
    <>
      <div className="monitor-header">
        <div>
          <Link to={`/patients/${current.patient}`} className="back-link">
            <Icon name="chevron-left" size={15} />
            {current.patient_name} · {current.patient_code}
          </Link>
          <PageHeader
            eyebrow="Live ECG"
            title={`${current.patient_name} · ${current.device_name}`}
            description={`Session ${current.id} · started ${formatDateTime(current.start_time)}`}
          />
        </div>
        <div className="monitor-header__badges">
          <ConnectionBadge state={live.connection} />
          <HeartbeatBadge status={heartbeat} />
          <SessionBadge status={current.status} />
        </div>
      </div>

      {actionError && <ErrorBanner message={actionError} />}
      {live.socketError && (
        <ErrorBanner
          message={live.socketError}
          onRetry={() => live.reconnect()}
        />
      )}
      {live.chunkError && <ErrorBanner message={live.chunkError} onRetry={() => live.reconnect()} />}

      <div className="stats stats--four">
        <StatCard
          icon="clock"
          label="Recording time"
          value={formatDuration(elapsed)}
          hint={current.end_time ? `ended ${formatDateTime(current.end_time)}` : 'live'}
        />
        <StatCard
          icon="heart"
          label="Heart rate"
          value={heartRate === null ? '—' : `${heartRate.toFixed(0)} bpm`}
          hint={analysis ? 'live estimate from stored ECG' : 'waiting for a valid signal'}
          tone={heartRate === null ? 'neutral' : 'ok'}
        />
        <StatCard
          icon="activity"
          label="Signal quality"
          value={quality ? `${quality.score?.toFixed(0) ?? '—'} / 100` : '—'}
          hint={quality ? quality.level : 'collecting samples'}
          tone={quality ? qualityTone(quality.usable, quality.level) : 'neutral'}
        />
        <StatCard
          icon="pulse"
          label="ECG samples"
          value={live.series.sampleCount}
          hint={rate ? `${rate} Hz · ${live.chunks.length} chunks` : 'waiting'}
          tone={live.chunks.length > 0 ? 'ok' : 'neutral'}
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
              height={320}
              emptyLabel={
                live.initialLoading
                  ? 'Seeding the waveform from stored chunks…'
                  : 'Waiting for the first ECG chunk. Run the simulator with --ecg or connect the ESP32.'
              }
            />
            <div className="ecg-meta">
              <span>
                <Icon name="activity" size={14} /> {live.chunks.length} chunks
              </span>
              <span>
                <Icon name="clock" size={14} /> {live.series.durationSeconds.toFixed(1)} s in view
              </span>
              <span>
                <Icon name="spark" size={14} /> {live.frames} socket frames
              </span>
            </div>
          </div>
        </section>

        <div className="monitor-side">
          <section className="panel">
            <div className="panel__header">
              <div>
                <h2>Recording controls</h2>
                <p>Status and lifecycle</p>
              </div>
              <SessionBadge status={current.status} />
            </div>
            <div className="panel__body">
              <div className="kv-list">
                <div>
                  <span>Patient</span>
                  <strong>{current.patient_name}</strong>
                </div>
                <div>
                  <span>Patient ID</span>
                  <strong className="mono">{current.patient_code}</strong>
                </div>
                <div>
                  <span>Device</span>
                  <strong>{current.device_name}</strong>
                </div>
                <div>
                  <span>Socket</span>
                  <strong>
                    <ConnectionBadge state={live.connection} />
                  </strong>
                </div>
                <div>
                  <span>Last frame</span>
                  <strong>{lastFrame}</strong>
                </div>
              </div>

              {current.status === 'active' ? (
                <button
                  type="button"
                  className="button button--danger button--block"
                  onClick={() => void finishRecording()}
                  disabled={stopping}
                >
                  <Icon name="stop" size={15} />
                  {stopping ? 'Stopping & analysing…' : 'Stop recording & analyse'}
                </button>
              ) : (
                <Link to={`/sessions/${current.id}`} className="button button--primary button--block">
                  <Icon name="sessions" size={15} />
                  Open analysis & report
                </Link>
              )}

              {live.connection !== 'live' && current.status === 'active' && (
                <button
                  type="button"
                  className="button button--ghost button--block"
                  onClick={() => live.reconnect()}
                >
                  <Icon name="refresh" size={15} />
                  Reconnect
                </button>
              )}
            </div>
          </section>

          <section className="panel">
            <div className="panel__header">
              <div>
                <h2>Signal quality</h2>
                <p>Unpersisted live estimate from stored chunks</p>
              </div>
              {quality && (
                <Badge tone={qualityTone(quality.usable, quality.level)}>
                  {quality.usable ? 'usable' : 'unusable'}
                </Badge>
              )}
            </div>
            <div className="panel__body">
              {!analysis ? (
                <p className="muted small">
                  {current.status === 'active'
                    ? 'Waiting for enough ECG samples to estimate quality.'
                    : 'Recording is not active. Open the analysis for the stored result.'}
                </p>
              ) : (
                <>
                  <div className="quality-bar">
                    <span style={{ width: `${Math.max(0, Math.min(100, quality?.score ?? 0))}%` }} />
                  </div>
                  <div className="kv-list">
                    <div>
                      <span>Score</span>
                      <strong>{quality?.score?.toFixed(1) ?? '—'} / 100</strong>
                    </div>
                    <div>
                      <span>Level</span>
                      <strong>{quality?.level}</strong>
                    </div>
                    <div>
                      <span>Beats detected</span>
                      <strong>{analysis.measurements.beats_detected}</strong>
                    </div>
                    <div>
                      <span>Estimate from</span>
                      <strong>{analysis.signal.duration_seconds.toFixed(1)} s of ECG</strong>
                    </div>
                  </div>
                  {quality?.reasons.length ? (
                    <ul className="reason-list">
                      {quality.reasons.map((reason) => (
                        <li key={reason}>{reason}</li>
                      ))}
                    </ul>
                  ) : null}
                </>
              )}
              <p className="muted small">
                Heart rate and quality here are computed by the backend DSP from stored
                chunks. They are descriptive measurements, not a diagnosis.
              </p>
            </div>
          </section>
        </div>
      </div>

      <div className="dashboard-grid dashboard-grid--narrow">
        <Notice tone="info" icon="pulse">
          <strong>The socket carries metadata.</strong> Each ECG chunk's samples are fetched
          over REST when needed. A late viewer is seeded from the stored chunks, so a reload
          does not lose the waveform.
        </Notice>
        <section className="panel">
          <div className="panel__header">
            <div>
              <h2>Send data to this session</h2>
              <p>The simulator and ESP32 use the same contract</p>
            </div>
          </div>
          <div className="panel__body">
            <p className="small muted">
              Use the device token shown when the device was registered (rotate it in
              Settings if lost):
            </p>
            <pre className="code-block">
              <code>{`python -m simulator --session-id ${current.id} \\
  --device-token <DEVICE_TOKEN> --ecg --duration 60`}</code>
            </pre>
            <p className="small muted">
              Data is refused once the session is stopped. Complete the recording to run
              analysis and generate the PDF report.
            </p>
          </div>
        </section>
      </div>
    </>
  )
}
