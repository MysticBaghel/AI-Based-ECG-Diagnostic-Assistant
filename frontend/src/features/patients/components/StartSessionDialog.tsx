import { useState } from 'react'

import { ApiError } from '@/shared/api/http'
import { sessionsApi } from '@/features/sessions/api'
import type { Device, Patient, Session } from '@/shared/types'
import { Icon } from '@/shared/icons/Icon'
import { Modal } from '@/shared/ui/Modal'
import { EmptyState, ErrorBanner } from '@/shared/ui'

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
  const activeDevices = devices.filter((device) => device.status === 'active')
  const available = activeDevices.filter(
    (device) =>
      device.assigned_patient === null || device.assigned_patient === patient.id,
  )
  const [deviceId, setDeviceId] = useState(available[0]?.id ?? '')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function start() {
    if (!deviceId) return
    setSubmitting(true)
    setError(null)
    try {
      const session = await sessionsApi.start(patient.id, deviceId)
      onStarted(session)
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : 'Could not start the recording. Is the backend running?',
      )
      setSubmitting(false)
    }
  }

  return (
    <Modal
      title="Start a new ECG recording"
      subtitle={`${patient.full_name} · ${patient.patient_id}`}
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
            {submitting ? 'Starting…' : 'Start recording'}
            {!submitting && <Icon name="play" size={15} />}
          </button>
        </>
      }
    >
      {available.length === 0 ? (
        <EmptyState
          icon="devices"
          title={activeDevices.length === 0 ? 'No active device' : 'No device for this patient'}
          description={
            activeDevices.length === 0
              ? 'Every registered device is disabled or none exists. Register one in Settings first.'
              : 'The active devices are dedicated to other patients. Unassign one in Settings, or register a shared device.'
          }
        />
      ) : (
        <div className="stack">
          <label className="field">
            <span>Device</span>
            <select value={deviceId} onChange={(event) => setDeviceId(event.target.value)}>
              {available.map((device) => (
                <option key={device.id} value={device.id}>
                  {device.name}
                  {device.assigned_patient === patient.id ? ' · dedicated' : ''}
                </option>
              ))}
            </select>
            <small>
              A device runs one active recording at a time. Starting the session registers
              it with the telemetry service so the simulator or ESP32 can upload.
            </small>
          </label>

          <div className="kv-list">
            <div>
              <span>Patient</span>
              <strong>{patient.full_name}</strong>
            </div>
            <div>
              <span>Patient ID</span>
              <strong className="mono">{patient.patient_id}</strong>
            </div>
            <div>
              <span>Starts as</span>
              <strong>active recording</strong>
            </div>
          </div>

          {error && <ErrorBanner message={error} />}

          <p className="muted small">
            After starting, the live monitor opens. Run the simulator or connect the ESP32
            with this session's device token. The recording is saved under this patient.
          </p>
        </div>
      )}
    </Modal>
  )
}
