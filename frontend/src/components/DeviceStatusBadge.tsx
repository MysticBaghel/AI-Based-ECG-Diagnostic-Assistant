import type { Device, DeviceStatus } from '../api/types'
import { formatRelative } from '../lib/format'
import { Badge } from './ui'

/** A heartbeat badge: FastAPI's `online` flag, not a guess from the UI. */
export function HeartbeatBadge({ status }: { status: DeviceStatus | null }) {
  if (!status) {
    return <Badge tone="neutral">No heartbeat yet</Badge>
  }
  if (status.revoked) {
    return <Badge tone="bad">Revoked</Badge>
  }
  if (status.online) {
    return <Badge tone="ok" pulse>Online</Badge>
  }
  return (
    <Badge tone="warn">
      Offline · {formatRelative(status.last_seen)}
    </Badge>
  )
}

export function DeviceStateBadge({ device }: { device: Device }) {
  if (device.status === 'disabled') return <Badge tone="warn">Disabled</Badge>
  return <Badge tone="info">Registered</Badge>
}
