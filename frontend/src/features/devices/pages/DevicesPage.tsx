import { useState, type FormEvent } from 'react'

import { ApiError } from '@/shared/api/http'
import { devicesApi } from '@/features/devices/api'
import type { Device } from '@/shared/types'
import { HeartbeatBadge } from '@/features/devices/components/DeviceStatusBadge'
import { Icon } from '@/shared/icons/Icon'
import { TokenDialog } from '@/features/devices/components/TokenDialog'
import {
  Badge,
  EmptyState,
  ErrorBanner,
  Notice,
  PageHeader,
  SectionCard,
  Spinner,
  StatCard,
} from '@/shared/ui'
import { useDevices, useDeviceStatus } from '@/features/devices/hooks/useDevices'
import { usePatients } from '@/features/patients/hooks/usePatients'
import { formatDateTime, formatRelative } from '@/shared/lib/format'

interface IssuedToken {
  device: Device
  token: string
  title: string
}

export function DevicesPage() {
  const devices = useDevices()
  const patients = usePatients('')
  const status = useDeviceStatus()
  const [name, setName] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [rotating, setRotating] = useState<string | null>(null)
  const [issued, setIssued] = useState<IssuedToken | null>(null)

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
      const device = await devicesApi.create(name.trim())
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
      const result = await devicesApi.rotateToken(device.id)
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
      await devicesApi.setStatus(device.id, device.status === 'active' ? 'disabled' : 'active')
      devices.refresh()
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not change the device state.')
    }
  }

  async function assign(device: Device, value: string) {
    setError(null)
    try {
      await devicesApi.assignPatient(device.id, value ? Number(value) : null)
      devices.refresh()
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : 'Could not assign the device.')
    }
  }

  return (
    <>
      <PageHeader
        title="Devices"
        description="ESP32 + AD8232 units and simulator devices registered for ECG recordings"
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

      <div className="stats stats--three">
        <StatCard icon="devices" label="Registered" value={list.length} hint="device records" />
        <StatCard icon="wifi" label="Online now" value={online} hint="heartbeat within threshold" tone={online > 0 ? 'ok' : 'warn'} />
        <StatCard icon="shield" label="Tokens" value="Shown once" hint="rotate if lost" />
      </div>

      <SectionCard title="Register a device" subtitle="The token is returned once and never stored">
        <form className="inline-form" onSubmit={(event) => void registerDevice(event)}>
          <label className="field field--inline">
            <span className="sr-only">Device name</span>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="e.g. ESP32-01 · AD8232"
              maxLength={100}
              required
            />
          </label>
          <button type="submit" className="button button--primary" disabled={creating}>
            <Icon name="plus" size={16} />
            {creating ? 'Registering…' : 'Register device'}
          </button>
        </form>
        <Notice tone="info" icon="devices">
          A device may be shared across the clinic or dedicated to one patient. The
          simulator uses the same token and ingestion contract as the ESP32.
        </Notice>
      </SectionCard>

      {devices.loading ? (
        <Spinner label="Loading devices…" />
      ) : list.length === 0 ? (
        <EmptyState
          icon="devices"
          title="No devices registered"
          description="Register an ESP32 + AD8232 unit or use a simulator device. The token is needed to upload ECG chunks."
        />
      ) : (
        <section className="panel">
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
                        <div className="device-name">
                          <strong>{device.name}</strong>
                          <span className="mono">{device.id}</span>
                        </div>
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
                        <Badge tone={device.status === 'active' ? 'info' : 'warn'}>{device.status}</Badge>
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
                        <div className="button-row" style={{ justifyContent: 'flex-end' }}>
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
        </section>
      )}

      <p className="muted small">
        A heartbeat is only reported after <code>POST /sensor/connect</code>; a newly
        registered device reads “No heartbeat yet”.
      </p>

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
