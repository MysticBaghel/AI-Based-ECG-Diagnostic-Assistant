import { EcgChart } from '@/shared/charts/EcgChart'
import { Icon } from '@/shared/icons/Icon'
import { formatDuration } from '@/shared/lib/format'
import type { EcgSeries } from '@/shared/lib/ecg'

export function RecordingPanel({
  series,
  chunks,
  frames,
  active,
  elapsed,
  initialLoading,
}: {
  series: EcgSeries
  chunks: number
  frames: number
  active: boolean
  elapsed: number
  initialLoading: boolean
}) {
  return (
    <section className="recording-panel">
      <div className="recording-panel__bar">
        <span className="recording-dot" />
        <strong style={{ color: active ? '#b91c1c' : 'var(--text)' }}>
          {active ? 'Recording' : 'Recording complete'}
        </strong>
        <span>{active ? 'Streaming ECG samples' : 'Stored ECG signal'}</span>
        <span className="recording-panel__scale">
          <span>25 mm/s</span>
          <span>10 mm/mV</span>
          <span className="mono">{formatDuration(elapsed)}</span>
        </span>
      </div>
      <div className="recording-panel__body">
        <EcgChart
          x={series.x}
          y={series.y}
          height={318}
          theme="paper"
          emptyLabel={
            initialLoading
              ? 'Seeding the waveform from stored chunks…'
              : 'Waiting for the first ECG chunk. Use Simulate on the Patients page, run the CLI simulator, or connect the ESP32.'
          }
        />
        <div className="ecg-meta">
          <span>
            <Icon name="activity" size={14} /> {chunks} chunks
          </span>
          <span>
            <Icon name="clock" size={14} /> {series.durationSeconds.toFixed(1)} s in view
          </span>
          <span>
            <Icon name="spark" size={14} /> {frames} socket frames
          </span>
        </div>
      </div>
    </section>
  )
}
