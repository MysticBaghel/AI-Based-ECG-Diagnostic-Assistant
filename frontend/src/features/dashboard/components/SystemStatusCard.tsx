import { Notice, SectionCard } from '@/shared/ui'
import type { Health } from '@/shared/types'

export function SystemStatusCard({
  service,
  deviceCount,
}: {
  service: {
    django: boolean
    fastapi: boolean
    analysis?: Health['analysis']
  } | null
  deviceCount: number
}) {
  const ai = service?.analysis

  return (
    <SectionCard title="System status" subtitle="Backends and analysis capability">
      <div className="kv-list">
        <div>
          <span>Django API</span>
          <strong>{service?.django ? 'up' : 'down'}</strong>
        </div>
        <div>
          <span>FastAPI telemetry</span>
          <strong>{service?.fastapi ? 'up' : 'down'}</strong>
        </div>
        <div>
          <span>Signal processing</span>
          <strong>{ai ? 'deterministic DSP available' : 'waiting for FastAPI'}</strong>
        </div>
        <div>
          <span>AI classifier</span>
          <strong>{ai?.inference_available ? 'validated model loaded' : 'not configured'}</strong>
        </div>
      </div>
      {ai && !ai.inference_available && (
        <Notice tone="warn" icon="alert">
          <strong>AI analysis is unavailable.</strong> {ai.inference_reason} DSP
          measurements are still produced and reports say this explicitly.
        </Notice>
      )}
      {deviceCount === 0 && (
        <Notice tone="info" icon="devices">
          No device is registered yet. Register one in Devices before starting a recording.
        </Notice>
      )}
    </SectionCard>
  )
}
