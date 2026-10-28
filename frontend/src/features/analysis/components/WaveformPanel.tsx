import { EcgChart } from '@/shared/charts/EcgChart'
import { Icon } from '@/shared/icons/Icon'
import { EmptyState, ErrorBanner, Spinner } from '@/shared/ui'
import type { EcgSeries } from '@/shared/lib/ecg'

const CHART_HEIGHT = 250

/**
 * The stored-waveform panel and its chunk player.
 *
 * The trace is only drawn once **every** chunk in the selected window has
 * arrived; before that the slot shows a spinner instead. The player stays in
 * place (disabled) the whole time so changing windows cannot collapse the
 * panel and make the page jump around, which is what made "click ahead"
 * feel glitchy.
 */
export function WaveformPanel({
  series,
  chunkCount,
  start,
  size,
  maxStart,
  loading,
  windowLoading,
  windowError = null,
  onStart,
  onRetry,
}: {
  series: EcgSeries
  chunkCount: number
  start: number
  size: number
  maxStart: number
  loading: boolean
  windowLoading: boolean
  windowError?: string | null
  onStart: (value: number) => void
  onRetry?: () => void
}) {
  const ready = !windowLoading && !windowError

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
        ) : (
          <>
            {/* A fixed-height slot: the spinner occupies the chart's place
                instead of replacing it, so the panel never changes size while
                a window loads. */}
            <div
              className="chart-slot"
              style={{
                height: CHART_HEIGHT,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              {!ready ? (
                windowError ? (
                  <ErrorBanner message={windowError} onRetry={onRetry} />
                ) : (
                  <Spinner label="Loading the ECG samples…" />
                )
              ) : (
                <EcgChart
                  x={series.x}
                  y={series.y}
                  height={CHART_HEIGHT}
                  theme="paper"
                  emptyLabel="This window has no samples."
                />
              )}
            </div>

            {chunkCount > 1 && (
              <div className="chunk-nav">
                <button
                  type="button"
                  className="button button--ghost button--sm"
                  onClick={() => onStart(Math.max(0, start - size))}
                  disabled={windowLoading || start === 0}
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
                  disabled={windowLoading || start >= maxStart}
                >
                  Later
                  <Icon name="chevron-right" size={14} />
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  )
}
