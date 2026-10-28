import { SectionCard } from '@/shared/ui'
import { formatRelative } from '@/shared/lib/format'
import type { Device, StatusResponse } from '@/shared/types'

export function DeviceHeartbeatCard({
  status,
  devices,
}: {
  status: StatusResponse | null
  devices: Device[]
}) {
  return (
    <SectionCard title="Device heartbeat" subtitle="Last connection reported by FastAPI">
      {status?.devices.length ? (
        <div className="kv-list">
          {status.devices.slice(0, 5).map((device) => {
            const registered = devices.find((item) => item.id === device.device_id)
            return (
              <div key={device.device_id}>
                <span>{registered?.name ?? device.device_id.slice(0, 8)}</span>
                <strong>
                  {device.revoked
                    ? 'revoked'
                    : device.online
                      ? 'online'
                      : `offline · ${formatRelative(device.last_seen)}`}
                </strong>
              </div>
            )
          })}
        </div>
      ) : (
        <p className="muted small">
          No heartbeat yet. A device appears after its first <code>/sensor/connect</code>.
        </p>
      )}
    </SectionCard>
  )
}
