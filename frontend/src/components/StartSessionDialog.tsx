import { useState } from 'react'

import { ApiError, api } from '../api/client'
import type { Device, Patient, Session } from '../api/types'
import { Icon } from './Icon'
import { Modal } from './Modal'
import { EmptyState, ErrorBanner } from './ui'

export function StartSessionDialog({
  patient,
  devices,
  onClose,
  onStarted,
}: {
  patient: Patient
  devices: Device[]
  onClose: () => void
  onStarted: (session: Session) => void
}) {
  const available = devices.filter((device) => device.status === 'active')
  const [deviceId, setDeviceId] = useState(available[0]?.id ?? '')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function start() {
    if (!deviceId) return
    setSubmitting(true)
    setError(null)
    try {
      const session = await api.startSession(patient.id, deviceId)
      onStarted(session)
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : 'Could not start the session. Is Django running?',
      )
      setSubmitting(false)
    }
  }

  return (
    <Modal
      title="Start a monitoring session"
      subtitle={`${patient.username} · a device can run one active session at a time`}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="button button--ghost" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="button button--primary"
            onClick={() => void start()}
            disabled={!deviceId || submitting}
          >
            {submitting ? 'Starting…' : 'Start session'}
            {!submitting && <Icon name="play" size={15} />}
          </button>
        </>
      }
    >
      {available.length === 0 ? (
        <EmptyState
          icon="devices"
          title="No available device"
          description="Every registered device is disabled. Create or enable one first."
        />
      ) : (
        <div className="stack">
          <label className="field">
            <span>Device</span>
            <select value={deviceId} onChange={(event) => setDeviceId(event.target.value)}>
              {available.map((device) => (
                <option key={device.id} value={device.id}>
                  {device.name}
                </option>
              ))}
            </select>
            <small>
              The session is registered with FastAPI when it starts, which is what lets
              the device upload for this session.
            </small>
          </label>

          <div className="kv-list">
            <div>
              <span>Patient</span>
              <strong>{patient.username}</strong>
            </div>
            <div>
              <span>Patient ID</span>
              <strong className="mono">{patient.id}</strong>
            </div>
            <div>
              <span>Started by</span>
              <strong>you</strong>
            </div>
          </div>

          {error && <ErrorBanner message={error} />}

          <p className="muted small">
            Once started, open the live monitor. Run the simulator or connect a device
            with the session token to see data arrive.
          </p>
        </div>
      )}
    </Modal>
  )
}
