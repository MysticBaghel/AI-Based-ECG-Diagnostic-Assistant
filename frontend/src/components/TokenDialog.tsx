import type { Device } from '../api/types'
import { Icon } from './Icon'
import { Modal } from './Modal'
import { CopyButton, Notice } from './ui'

/**
 * A device token is issued exactly once and never stored, so this dialog is the
 * only chance to copy it. It says so instead of pretending it can be looked up
 * again later.
 */
export function TokenDialog({
  device,
  token,
  title = 'Device token',
  onClose,
}: {
  device: Device
  token: string
  title?: string
  onClose: () => void
}) {
  return (
    <Modal
      title={title}
      subtitle={`${device.name} · shown once`}
      onClose={onClose}
      footer={
        <button type="button" className="button button--primary" onClick={onClose}>
          I saved the token
        </button>
      }
    >
      <div className="stack">
        <Notice tone="warn" icon="alert">
          <strong>This token is not stored anywhere.</strong> If it is lost, rotate it from
          the device list. The simulator reads it from <code>.smoke/mint.txt</code> or the{' '}
          <code>DEVICE_TOKEN</code> environment variable.
        </Notice>

        <div className="token-box">
          <code>{token}</code>
          <CopyButton value={token} label="Copy token" />
        </div>

        <div className="kv-list">
          <div>
            <span>Device ID</span>
            <strong className="mono">{device.id}</strong>
          </div>
          <div>
            <span>Owner</span>
            <strong>{device.owner_username || device.owner}</strong>
          </div>
        </div>

        <p className="muted small">
          <Icon name="shield" size={14} /> Treat a device token like a password. It can
          upload telemetry for this device until it expires, unless the device is revoked
          in FastAPI.
        </p>
      </div>
    </Modal>
  )
}
