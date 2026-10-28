import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { ApiError, api, telemetry } from '../api/client'
import type { EcgChunk, Reading, SensorType } from '../api/types'
import { useAuth } from '../auth/useAuth'
import { HeartbeatBadge } from '../components/DeviceStatusBadge'
import { EcgChart } from '../components/EcgChart'
import { Icon } from '../components/Icon'
import { Sparkline } from '../components/Sparkline'
import {
  Badge,
  EmptyState,
  ErrorBanner,
  Notice,
  PageHeader,
  SectionCard,
  SessionBadge,
  Spinner,
  StatCard,
} from '../components/ui'
import {
  statusFor,
  useChunkIndex,
  useDeviceStatus,
  useReadings,
  useSession,
} from '../hooks/useData'
import { useResource } from '../hooks/useResource'
import { buildEcgSeries } from '../lib/ecg'
import {
  elapsedSeconds,
  formatDateTime,
  formatDuration,
  formatNumber,
  SENSOR_META,
  SENSOR_ORDER,
} from '../lib/format'

const WINDOW_SIZES = [6, 12, 24]

interface SensorSummary {
  sensor: SensorType
  latest: Reading | null
  min: number
  max: number
  average: number
  count: number
  values: number[]
}

function summarise(readings: Reading[]): SensorSummary[] {
  return SENSOR_ORDER.map((sensor) => {
    const list = readings.filter((reading) => reading.sensor_type === sensor)
    const values = list.map((reading) => reading.value)
    const min = values.length ? Math.min(...values) : 0
    const max = values.length ? Math.max(...values) : 0
    const average = values.length
      ? values.reduce((sum, value) => sum + value, 0) / values.length
      : 0
    return {
      sensor,
      latest: list[0] ?? null,
      min,
      max,
      average,
      count: values.length,
      values: [...values].reverse(),
    }
  })
}

function RecordingView({ sessionId }: { sessionId: string }) {
  const { user } = useAuth()
  const session = useSession(sessionId)
  const readings = useReadings(sessionId, 500)
  const index = useChunkIndex(sessionId)
  const status = useDeviceStatus()
  const [start, setStart] = useState(0)
  const [size, setSize] = useState(12)
  const [stopping, setStopping] = useState(false)
  const [stopError, setStopError] = useState<string | null>(null)

  const chunks = index.data?.chunks ?? []
  const maxStart = Math.max(0, chunks.length - size)
  const safeStart = Math.min(start, maxStart)
  const selected = chunks.slice(safeStart, safeStart + size)
  const selectedKey = selected.map((chunk) => chunk.chunk_index).join(',')

  const windowData = useResource<EcgChunk[]>(
    `chunk-window:${sessionId}:${selectedKey}`,
    () =>
      selected.length === 0
        ? Promise.resolve([])
        : Promise.all(
            selected.map((chunk) => telemetry.chunk(sessionId, chunk.chunk_index)),
          ),
    { enabled: selected.length > 0 },
  )

  const series = useMemo(
    () => buildEcgSeries(windowData.data ?? []),
    [windowData.data],
  )
  const summaries = useMemo(
    () => summarise(readings.data?.readings ?? []),
    [readings.data],
  )

  const current = session.data
  const canManage = user?.role === 'doctor' || user?.role === 'admin'
  const heartbeat = current ? statusFor(status.data, current.device) : null
  const duration = current
    ? elapsedSeconds(current.start_time, current.end_time ?? new Date().toISOString())
    : 0

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
      index.refresh()
    } catch (caught) {
      setStopError(caught instanceof ApiError ? caught.message : 'Could not stop the session.')
    } finally {
      setStopping(false)
    }
  }

  if (session.loading) return <Spinner label="Loading session…" />
  if (session.error) return <ErrorBanner message={session.error} onRetry={session.refresh} />
  if (!current) return null

  return (
    <>
      <div className="monitor-header">
        <div>
          <Link to="/sessions" className="back-link">
            <Icon name="chevron-left" size={15} />
            All sessions
          </Link>
          <PageHeader
            eyebrow="Session recording"
            title={`${current.patient_name} · ${current.device_name}`}
            description={`${formatDateTime(current.start_time)} · ${formatDuration(duration)} · ${current.id}`}
          />
        </div>
        <div className="monitor-header__badges">
          <SessionBadge status={current.status} />
          <HeartbeatBadge status={heartbeat} />
          {current.status === 'active' && (
            <Link to={`/live/${current.id}`} className="button button--primary button--sm">
              <Icon name="pulse" size={14} />
              Watch live
            </Link>
          )}
        </div>
      </div>

      {stopError && <ErrorBanner message={stopError} />}
      {(readings.error || index.error) && (
        <ErrorBanner
          message={readings.error ?? index.error ?? ''}
          onRetry={() => {
            readings.refresh()
            index.refresh()
          }}
        />
      )}

      <div className="stats stats--four">
        <StatCard
          icon="pulse"
          label="ECG chunks"
          value={chunks.length}
          hint={
            chunks[0]
              ? `${chunks[0].sample_rate_hz} Hz · ${chunks[0].sample_count} samples/chunk`
              : 'none stored'
          }
          tone={chunks.length > 0 ? 'ok' : 'warn'}
        />
        <StatCard
          icon="clock"
          label="Session duration"
          value={formatDuration(duration)}
          hint={current.end_time ? `ended ${formatDateTime(current.end_time)}` : 'still active'}
        />
        <StatCard
          icon="activity"
          label="Scalar readings"
          value={readings.data?.count ?? 0}
          hint="latest 500"
        />
        <StatCard
          icon="wifi"
          label="Device"
          value={<HeartbeatBadge status={heartbeat} />}
          hint={heartbeat?.last_seen ? formatDateTime(heartbeat.last_seen) : 'never seen'}
        />
      </div>

      {chunks.length === 0 ? (
        <EmptyState
          icon="pulse"
          title="No ECG stored for this session"
          description={
            current.status === 'active'
              ? 'The session is active but no chunk has arrived yet. Open the live monitor or run the simulator with --ecg.'
              : 'This session has scalar readings but no ECG chunks. The simulator only uploads ECG when started with --ecg.'
          }
          action={
            current.status === 'active' ? (
              <Link to={`/live/${current.id}`} className="button button--primary">
                Open live monitor
              </Link>
            ) : undefined
          }
        />
      ) : (
        <section className="panel panel--ecg">
          <div className="panel__header">
            <div>
              <h2>Waveform viewer</h2>
              <p>
                {series.sampleCount} samples · {series.durationSeconds.toFixed(1)} s in view
                · {selected.length} chunks
              </p>
            </div>
            <div className="panel__actions">
              <label className="field field--compact">
                <span>Window</span>
                <select
                  value={size}
                  onChange={(event) => {
                    setSize(Number(event.target.value))
                    setStart(0)
                  }}
                >
                  {WINDOW_SIZES.map((value) => (
                    <option key={value} value={value}>
                      {value} chunks
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </div>
          <div className="panel__body">
            {windowData.error ? (
              <ErrorBanner message={windowData.error} onRetry={windowData.refresh} />
            ) : windowData.loading && series.sampleCount === 0 ? (
              <Spinner label="Loading chunk samples…" />
            ) : (
              <EcgChart
                x={series.x}
                y={series.y}
                height={340}
                emptyLabel="This window has no samples."
              />
            )}

            <div className="chunk-nav">
              <button
                type="button"
                className="button button--ghost button--sm"
                onClick={() => setStart((value) => Math.max(0, value - size))}
                disabled={safeStart === 0}
              >
                <Icon name="chevron-left" size={14} />
                Earlier
              </button>

              <input
                type="range"
                className="chunk-nav__range"
                min={0}
                max={maxStart}
                value={safeStart}
                onChange={(event) => setStart(Number(event.target.value))}
                aria-label="Start chunk"
              />

              <button
                type="button"
                className="button button--ghost button--sm"
                onClick={() => setStart((value) => Math.min(maxStart, value + size))}
                disabled={safeStart >= maxStart}
              >
                Later
                <Icon name="chevron-right" size={14} />
              </button>

              <span className="chunk-nav__label">
                chunks {safeStart}–{Math.min(chunks.length - 1, safeStart + size - 1)} of{' '}
                {chunks.length}
              </span>
            </div>
          </div>
        </section>
      )}

      <div className="monitor-grid monitor-grid--recording">
        <SectionCard
          title="Vital summary"
          subtitle="Derived from the stored scalar readings; not a clinical interpretation"
          flush
        >
          <div className="table-wrap">
            <table className="table table--compact">
              <thead>
                <tr>
                  <th>Signal</th>
                  <th>Latest</th>
                  <th>Min</th>
                  <th>Max</th>
                  <th>Average</th>
                  <th>Trend</th>
                  <th>Samples</th>
                </tr>
              </thead>
              <tbody>
                {summaries.map((summary) => {
                  const meta = SENSOR_META[summary.sensor]
                  return (
                    <tr key={summary.sensor}>
                      <td>
                        <span className="table__primary">{meta.label}</span>
                        <span className="table__secondary">{meta.unit}</span>
                      </td>
                      <td>
                        {summary.latest
                          ? formatNumber(summary.latest.value, meta.digits)
                          : '—'}
                      </td>
                      <td>{summary.count ? formatNumber(summary.min, meta.digits) : '—'}</td>
                      <td>{summary.count ? formatNumber(summary.max, meta.digits) : '—'}</td>
                      <td>
                        {summary.count ? formatNumber(summary.average, meta.digits) : '—'}
                      </td>
                      <td>
                        <Sparkline
                          values={summary.values}
                          color={meta.accent}
                          width={110}
                          height={30}
                        />
                      </td>
                      <td>{summary.count}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {readings.data && readings.data.count >= 500 && (
            <p className="panel__note">
              Showing the newest 500 readings. Export and pagination are Phase 6/7 work.
            </p>
          )}
        </SectionCard>

        <div className="monitor-side">
          <section className="panel">
            <div className="panel__header">
              <div>
                <h2>Session</h2>
                <p>Lifecycle</p>
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
                  <span>Device</span>
                  <strong>{current.device_name}</strong>
                </div>
                <div>
                  <span>Started</span>
                  <strong>{formatDateTime(current.start_time)}</strong>
                </div>
                <div>
                  <span>Ended</span>
                  <strong>{current.end_time ? formatDateTime(current.end_time) : '—'}</strong>
                </div>
              </div>

              {canManage && current.status === 'active' && (
                <button
                  type="button"
                  className="button button--danger button--block"
                  onClick={() => void stopSession()}
                  disabled={stopping}
                >
                  <Icon name="stop" size={15} />
                  {stopping ? 'Stopping…' : 'Stop session'}
                </button>
              )}
            </div>
          </section>

          <Notice tone="warn" icon="alert">
            <strong>Screening aid, not a medical diagnosis.</strong> The summary is arithmetic
            over stored readings. It does not detect arrhythmia, and a flat line or a spike
            here is not a finding.
          </Notice>

          <section className="panel">
            <div className="panel__header">
              <div>
                <h2>Chunk index</h2>
                <p>What the recording is made of</p>
              </div>
              <Badge tone="info" dot={false}>
                {chunks.length}
              </Badge>
            </div>
            <div className="panel__body">
              {chunks.length === 0 ? (
                <p className="muted small">No chunks.</p>
              ) : (
                <div className="chunk-list">
                  {chunks.slice(-8).map((chunk) => (
                    <button
                      type="button"
                      key={chunk.chunk_index}
                      className="chunk-list__item"
                      onClick={() => {
                        const target = Math.min(
                          Math.max(0, chunk.chunk_index),
                          Math.max(0, chunks.length - size),
                        )
                        setStart(target)
                      }}
                    >
                      <span>#{chunk.chunk_index}</span>
                      <span>{chunk.sample_count} samples</span>
                      <span>{formatDateTime(chunk.start_time)}</span>
                    </button>
                  ))}
                </div>
              )}
              <p className="muted small">
                Index metadata comes from <code>GET /sessions/…/ecg</code>; samples are
                fetched one chunk at a time.
              </p>
            </div>
          </section>
        </div>
      </div>
    </>
  )
}

export function RecordingPage() {
  const { sessionId } = useParams<{ sessionId: string }>()
  if (!sessionId) return <EmptyState title="No session selected" description="Open a session from history." />
  return <RecordingView key={sessionId} sessionId={sessionId} />
}
