import { EcgChart } from '@/shared/charts/EcgChart'
import { Icon } from '@/shared/icons/Icon'
import { EmptyState, Spinner } from '@/shared/ui'
import type { EcgSeries } from '@/shared/lib/ecg'

export function WaveformPanel({
  series,
  chunkCount,
  start,
  size,
  maxStart,
  loading,
  windowLoading,
  onStart,
}: {
  series: EcgSeries
  chunkCount: number
  start: number
  size: number
  maxStart: number
  loading: boolean
  windowLoading: boolean
  onStart: (value: number) => void
}) {
  return (
    <section className="recording-panel">
      <div className="recording-panel__bar">
        <Icon name="activity" size={14} />
        <strong style={{ color: 'var(--text)' }}>ECG Waveform</strong>
        <span className="recording-panel__scale">
          <span>25 mm/s</span>
          <span>10 mm/mV</span>
          {chunkCount > 0 && (
            <span>
              chunks {start}–{Math.min(chunkCount - 1, start + size - 1)} of {chunkCount}
            </span>
          )}
        </span>
      </div>
      <div className="recording-panel__body">
        {loading ? (
          <Spinner label="Loading the recording index…" />
        ) : chunkCount === 0 ? (
          <EmptyState
            icon="pulse"
            title="No ECG waveform stored"
            description="FastAPI has no ECG chunks for this session. Was the simulator run with --ecg?"
          />
        ) : windowLoading && series.sampleCount === 0 ? (
          <Spinner label="Loading samples…" />
        ) : (
          <EcgChart x={series.x} y={series.y} height={250} theme="paper" emptyLabel="This window has no samples." />
        )}
        {chunkCount > 1 && (
          <div className="chunk-nav">
            <button
              type="button"
              className="button button--ghost button--sm"
              onClick={() => onStart(Math.max(0, start - size))}
              disabled={start === 0}
            >
              <Icon name="chevron-left" size={14} />
              Earlier
            </button>
            <input
              type="range"
              className="chunk-nav__range"
              min={0}
              max={maxStart}
              value={start}
              onChange={(event) => onStart(Number(event.target.value))}
              aria-label="Start chunk"
            />
            <button
              type="button"
              className="button button--ghost button--sm"
              onClick={() => onStart(Math.min(maxStart, start + size))}
              disabled={start >= maxStart}
            >
              Later
              <Icon name="chevron-right" size={14} />
            </button>
          </div>
        )}
      </div>
    </section>
  )
}
