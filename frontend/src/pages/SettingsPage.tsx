import { useState, type FormEvent } from 'react'

import {
  ApiError,
  api,
  defaultTelemetryBase,
  setTelemetryBase,
  telemetry,
  telemetryBase,
} from '../api/client'
import type { Device } from '../api/types'
import { HeartbeatBadge } from '../components/DeviceStatusBadge'
import { Icon } from '../components/Icon'
import { TokenDialog } from '../components/TokenDialog'
import {
  Badge,
  EmptyState,
  ErrorBanner,
  Notice,
  PageHeader,
  SectionCard,
  Spinner,
  StatCard,
} from '../components/ui'
import { useDevices, useDeviceStatus, usePatients } from '../hooks/useData'
import { useResource } from '../hooks/useResource'
import { formatDateTime, formatRelative } from '../lib/format'

interface IssuedToken {
  device: Device
  token: string
  title: string
}

export function SettingsPage() {
  const devices = useDevices()
  const patients = usePatients('')
  const status = useDeviceStatus()
  const health = useResource(
    'settings-health',
    async () => {
      const [django, fastapi] = await Promise.allSettled([api.health(), telemetry.health()])
      return {
        django: django.status === 'fulfilled' ? django.value : null,
        fastapi: fastapi.status === 'fulfilled' ? fastapi.value : null,
      }
    },
    { pollMs: 30_000 },
  )

  const [name, setName] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [issued, setIssued] = useState<IssuedToken | null>(null)
  const [rotating, setRotating] = useState<string | null>(null)
  const [baseUrl, setBaseUrl] = useState(telemetryBase())

  const list = devices.data ?? []
  const patientList = patients.data ?? []
  const online = list.filter((device) =>
    status.data?.devices.find((row) => row.device_id === device.id && row.online),
  ).length

  async function registerDevice(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!name.trim()) return
    setCreating(true)
    setError(null)
    try {
      const device = await api.createDevice(name.trim())
      setName('')
      devices.refresh()
      setIssued({ device, token: device.device_token, title: 'Device token' })
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not register the device.')
    } finally {
      setCreating(false)
    }
  }

  async function rotate(device: Device) {
    setRotating(device.id)
    setError(null)
    try {
      const result = await api.rotateDeviceToken(device.id)
      setIssued({ device, token: result.device_token, title: 'New device token' })
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not rotate the token.')
    } finally {
      setRotating(null)
    }
  }

  async function setStatus(device: Device) {
    setError(null)
    try {
      await api.setDeviceStatus(device.id, device.status === 'active' ? 'disabled' : 'active')
      devices.refresh()
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not change the device state.')
    }
  }

  async function assign(device: Device, value: string) {
    setError(null)
    try {
      await api.assignDevicePatient(device.id, value ? Number(value) : null)
      devices.refresh()
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not assign the device.')
    }
  }

  function saveBaseUrl(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setTelemetryBase(baseUrl)
    window.location.reload()
  }

  function resetBaseUrl() {
    setTelemetryBase(null)
    setBaseUrl(defaultTelemetryBase())
    window.location.reload()
  }

  return (
    <>
      <PageHeader
        eyebrow="Configuration"
        title="Settings"
        description="Backend connections, the device pool and the analysis capabilities of this installation."
      />

      {error && <ErrorBanner message={error} />}
      {(devices.error || status.error || patients.error) && (
        <ErrorBanner
          message={devices.error ?? status.error ?? patients.error ?? ''}
          onRetry={() => {
            devices.refresh()
            status.refresh()
            patients.refresh()
          }}
        />
      )}

      <div className="stats stats--four">
        <StatCard icon="dashboard" label="Django API" value={health.data?.django?.status ?? 'down'} hint="identity & business data" tone={health.data?.django ? 'ok' : 'bad'} />
        <StatCard icon="activity" label="FastAPI" value={health.data?.fastapi?.status ?? 'down'} hint="telemetry & DSP" tone={health.data?.fastapi ? 'ok' : 'bad'} />
        <StatCard
          icon="spark"
          label="AI model"
          value={health.data?.fastapi?.analysis?.inference_available ? 'ready' : 'not configured'}
          hint={health.data?.fastapi?.analysis?.model_name ?? 'add a validated model'}
          tone={health.data?.fastapi?.analysis?.inference_available ? 'ok' : 'warn'}
        />
        <StatCard icon="wifi" label="Devices online" value={online} hint={`${list.length} registered`} tone={online > 0 ? 'ok' : 'neutral'} />
      </div>

      <div className="dashboard-grid dashboard-grid--narrow">
        <SectionCard title="API connections" subtitle="The browser talks to Django and FastAPI">
          <form className="form" onSubmit={saveBaseUrl}>
            <label className="field">
              <span>Telemetry API base URL</span>
              <input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} placeholder="/telemetry" />
              <small>
                Default: <code>{defaultTelemetryBase()}</code>. In development this is the
                Vite proxy. Changing it reloads the application.
              </small>
            </label>
            <div className="button-row">
              <button type="submit" className="button button--primary button--sm">
                Save & reload
              </button>
              <button type="button" className="button button--ghost button--sm" onClick={resetBaseUrl}>
                Reset to default
              </button>
            </div>
          </form>
          <div className="kv-list">
            <div>
              <span>Django API</span>
              <strong className="mono">{import.meta.env.VITE_API_BASE_URL ?? '/api'}</strong>
            </div>
            <div>
              <span>FastAPI telemetry</span>
              <strong className="mono">{telemetryBase()}</strong>
            </div>
            <div>
              <span>Model status</span>
              <strong>{health.data?.fastapi?.analysis?.inference_reason || (health.data?.fastapi?.analysis?.inference_available ? 'validated model loaded' : 'not checked')}</strong>
            </div>
          </div>
          <Notice tone="warn" icon="alert">
            <strong>No model is bundled.</strong> DSP measurements are always available. AI
            classification is only shown when a validated model file is configured on FastAPI;
            otherwise every screen and every report says it is unavailable.
          </Notice>
        </SectionCard>

        <SectionCard title="Register a device" subtitle="ESP32 + AD8232, or the simulator">
          <form className="inline-form" onSubmit={(event) => void registerDevice(event)}>
            <label className="field field--inline">
              <span className="sr-only">Device name</span>
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="e.g. ESP32 · AD8232 · room 2"
                maxLength={100}
                required
              />
            </label>
            <button type="submit" className="button button--primary" disabled={creating}>
              <Icon name="plus" size={16} />
              {creating ? 'Registering…' : 'Register device'}
            </button>
          </form>
          <p className="muted small">
            The device token is returned once and never stored. It is the credential the
            simulator or ESP32 uses to upload ECG chunks.
          </p>
          <pre className="code-block">
            <code>{`python -m simulator --session-id <SESSION_ID> \\
  --device-token <DEVICE_TOKEN> --ecg --duration 60`}</code>
          </pre>
        </SectionCard>
      </div>

      <SectionCard
        title="Devices"
        subtitle="Registration, patient dedication and heartbeat"
        actions={<Badge tone="info" dot={false}>{list.length} devices</Badge>}
      >
        {devices.loading ? (
          <Spinner label="Loading devices…" />
        ) : list.length === 0 ? (
          <EmptyState
            icon="devices"
            title="No devices registered"
            description="Register a device above. The simulator can then upload ECG for an active session."
          />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Device</th>
                  <th>Dedicated patient</th>
                  <th>Status</th>
                  <th>Heartbeat</th>
                  <th>Last seen</th>
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {list.map((device) => {
                  const heartbeat = status.data?.devices.find((row) => row.device_id === device.id) ?? null
                  return (
                    <tr key={device.id}>
                      <td>
                        <div className="table__primary">{device.name}</div>
                        <div className="table__secondary mono">{device.id}</div>
                      </td>
                      <td>
                        <select
                          className="select-inline"
                          value={device.assigned_patient ?? ''}
                          onChange={(event) => void assign(device, event.target.value)}
                          aria-label={`Patient for ${device.name}`}
                        >
                          <option value="">Shared / unassigned</option>
                          {patientList.map((patient) => (
                            <option key={patient.id} value={patient.id}>
                              {patient.full_name} · {patient.patient_id}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <Badge tone={device.status === 'active' ? 'info' : 'warn'}>
                          {device.status}
                        </Badge>
                      </td>
                      <td>
                        <HeartbeatBadge status={heartbeat} />
                      </td>
                      <td>
                        <span className="table__secondary">
                          {heartbeat?.last_seen
                            ? `${formatRelative(heartbeat.last_seen)} · ${formatDateTime(heartbeat.last_seen)}`
                            : 'never'}
                        </span>
                      </td>
                      <td className="table__action">
                        <div className="button-row">
                          <button
                            type="button"
                            className="button button--ghost button--sm"
                            onClick={() => void rotate(device)}
                            disabled={rotating === device.id || device.status === 'disabled'}
                          >
                            <Icon name="refresh" size={14} />
                            {rotating === device.id ? 'Rotating…' : 'Token'}
                          </button>
                          <button
                            type="button"
                            className="button button--ghost button--sm"
                            onClick={() => void setStatus(device)}
                          >
                            {device.status === 'active' ? 'Disable' : 'Enable'}
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      <SectionCard title="Limitations of this installation" subtitle="Read before relying on any output">
        <ul className="finding-list">
          <li>Screening aid, not a standalone medical diagnosis.</li>
          <li>AI classification is experimental and unavailable unless a validated model is configured.</li>
          <li>Simulator ECG is synthetic or replayed research data; a successful simulator run does not prove diagnostic accuracy.</li>
          <li>Django Admin remains available for technical account and database administration, but is not the operator interface.</li>
        </ul>
      </SectionCard>

      {issued && (
        <TokenDialog
          device={issued.device}
          token={issued.token}
          title={issued.title}
          onClose={() => setIssued(null)}
        />
      )}
    </>
  )
}
