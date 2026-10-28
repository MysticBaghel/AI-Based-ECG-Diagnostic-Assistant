import { useState, type FormEvent } from 'react'

import { ApiError, api } from '../api/client'
import type { Device } from '../api/types'
import { useAuth } from '../auth/useAuth'
import { DeviceStateBadge, HeartbeatBadge } from '../components/DeviceStatusBadge'
import { Icon } from '../components/Icon'
import { TokenDialog } from '../components/TokenDialog'
import {
  CopyButton,
  EmptyState,
  ErrorBanner,
  Notice,
  PageHeader,
  Spinner,
  StatCard,
} from '../components/ui'
import { statusFor, useDeviceStatus, useDevices } from '../hooks/useData'
import { formatDateTime, formatRelative } from '../lib/format'

interface IssuedToken {
  device: Device
  token: string
  title: string
}

export function DevicesPage() {
  const { user } = useAuth()
  const devices = useDevices()
  const status = useDeviceStatus()
  const [name, setName] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [rotating, setRotating] = useState<string | null>(null)
  const [issued, setIssued] = useState<IssuedToken | null>(null)

  const list = devices.data ?? []
  const online = list.filter((device) => statusFor(status.data, device.id)?.online).length

  async function createDevice(event: FormEvent<HTMLFormElement>) {
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
    if (!window.confirm(`Rotate the token for "${device.name}"? The old token keeps working until it expires, but the new one replaces it for the simulator.`)) {
      return
    }
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

  return (
    <>
      <PageHeader
        eyebrow="Devices"
        title="Registered devices"
        description="A device is a UUID in Django and a heartbeat row in FastAPI. The token is the only thing it uses to upload."
      />

      {error && <ErrorBanner message={error} />}
      {(devices.error || status.error) && (
        <ErrorBanner
          message={devices.error ?? status.error ?? ''}
          onRetry={() => {
            devices.refresh()
            status.refresh()
          }}
        />
      )}

      <div className="stats stats--three">
        <StatCard icon="devices" label="Registered" value={list.length} hint="owned by you" />
        <StatCard
          icon="wifi"
          label="Online now"
          value={online}
          hint={`heartbeat ≤ ${status.data?.threshold_seconds ?? 120}s`}
          tone={online > 0 ? 'ok' : 'warn'}
        />
        <StatCard
          icon="shield"
          label="Token handling"
          value="Shown once"
          hint="rotate to replace"
        />
      </div>

      <div className="dashboard-grid dashboard-grid--narrow">
        <section className="panel">
          <div className="panel__header">
            <div>
              <h2>Register a device</h2>
              <p>The token is returned once and never stored.</p>
            </div>
          </div>
          <div className="panel__body">
            <form className="inline-form" onSubmit={(event) => void createDevice(event)}>
              <label className="field field--inline">
                <span className="sr-only">Device name</span>
                <input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="e.g. Ward 3 · Holter 01"
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
              {user?.role === 'admin'
                ? 'As an admin you may register a device, but the owner is always the caller. Use a doctor account to create one for a doctor.'
                : 'You own every device you register. Only you (or an admin) can rotate its token.'}
            </p>
          </div>
        </section>

        <section className="panel">
          <div className="panel__header">
            <div>
              <h2>Heartbeats</h2>
              <p>How online/offline is decided</p>
            </div>
          </div>
          <div className="panel__body">
            <p className="small muted">
              FastAPI stamps <code>last_seen</code> on every <code>/sensor/connect</code>.
              A device is online while that timestamp is inside the threshold; it is not a
              guess based on the last reading.
            </p>
            <Notice tone="info" icon="alert">
              Revocation is a FastAPI-owned list. Disabling a device in Django does not write
              that list yet (Phase 7); the badge reports what FastAPI knows.
            </Notice>
          </div>
        </section>
      </div>

      {devices.loading ? (
        <Spinner label="Loading devices…" />
      ) : list.length === 0 ? (
        <EmptyState
          icon="devices"
          title="No devices yet"
          description="Register a device above. The simulator needs its device token to upload."
        />
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Device</th>
                {user?.role === 'admin' && <th>Owner</th>}
                <th>Registration</th>
                <th>Heartbeat</th>
                <th>Last seen</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {list.map((device) => {
                const heartbeat = statusFor(status.data, device.id)
                return (
                  <tr key={device.id}>
                    <td>
                      <div className="table__primary">{device.name}</div>
                      <div className="table__secondary mono">{device.id}</div>
                    </td>
                    {user?.role === 'admin' && (
                      <td>{device.owner_username || device.owner}</td>
                    )}
                    <td>
                      <div className="table__stack">
                        <DeviceStateBadge device={device} />
                        <span className="table__secondary">
                          {formatDateTime(device.created_at)}
                        </span>
                      </div>
                    </td>
                    <td>
                      <HeartbeatBadge status={heartbeat} />
                    </td>
                    <td>
                      <span className="table__secondary">
                        {heartbeat?.last_seen
                          ? `${formatRelative(heartbeat.last_seen)} · ${formatDateTime(
                              heartbeat.last_seen,
                            )}`
                          : 'never'}
                      </span>
                    </td>
                    <td className="table__action">
                      <div className="button-row">
                        <CopyButton value={device.id} label="Copy ID" />
                        <button
                          type="button"
                          className="button button--ghost button--sm"
                          onClick={() => void rotate(device)}
                          disabled={rotating === device.id || device.status === 'disabled'}
                          title={
                            device.status === 'disabled'
                              ? 'A disabled device cannot receive a token.'
                              : 'Rotate the device token'
                          }
                        >
                          <Icon name="refresh" size={14} />
                          {rotating === device.id ? 'Rotating…' : 'Rotate token'}
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
