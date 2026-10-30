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
  const analysis = service?.analysis

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
          <strong>{analysis ? 'deterministic DSP available' : 'waiting for FastAPI'}</strong>
        </div>
        <div>
          <span>ML classifier</span>
          <strong>{analysis?.inference_available ? 'trained CNN loaded' : 'not configured'}</strong>
        </div>
        <div>
          <span>AI advisor</span>
          <strong>{analysis?.advisor_available ? analysis.advisor_provider : 'unavailable'}</strong>
        </div>
      </div>
      {analysis && !analysis.inference_available && (
        <Notice tone="warn" icon="alert">
          <strong>ML classification is unavailable.</strong> {analysis.inference_reason} DSP
          measurements are still produced and reports say this explicitly.
        </Notice>
      )}
      {analysis && !analysis.advisor_available && (
        <Notice tone="warn" icon="alert">
          <strong>AI advice is unavailable.</strong> {analysis.advisor_reason}
        </Notice>
      )}
      {analysis?.advisor_provider === 'template' && (
        <Notice tone="info" icon="alert">
          AI advice is currently produced by the built-in deterministic template. Set
          <code> AI_ADVISOR_PROVIDER=api </code> and the API URL/key/model to connect the real AI
          provider; the stored request is already packaged for it.
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
