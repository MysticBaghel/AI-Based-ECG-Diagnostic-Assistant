import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@/shared/charts/EcgChart', () => ({
  EcgChart: () => <div data-testid="ecg-chart" />,
}))

import { WaveformPanel } from './WaveformPanel'

const series = { x: [0, 1], y: [0.1, 0.2], durationSeconds: 1, sampleCount: 2 }
const base = {
  series,
  chunkCount: 60,
  start: 8,
  size: 12,
  maxStart: 48,
  onStart: () => {},
}

function button(label: string): HTMLButtonElement {
  return screen.getByText(label).closest('button') as HTMLButtonElement
}

describe('WaveformPanel', () => {
  it('keeps the graph hidden but the player in place while a window loads', () => {
    render(<WaveformPanel {...base} loading={false} windowLoading />)

    expect(screen.getByText('Loading the ECG samples…')).toBeInTheDocument()
    expect(screen.queryByTestId('ecg-chart')).not.toBeInTheDocument()
    // The player stays mounted so the panel does not collapse and the range
    // input does not disappear mid-drag.
    expect(screen.getByLabelText('Start chunk')).toBeInTheDocument()
    expect(button('Earlier')).toBeDisabled()
    expect(button('Later')).toBeDisabled()
  })

  it('shows the trace and enables the player only once every chunk arrived', () => {
    render(<WaveformPanel {...base} loading={false} windowLoading={false} />)

    expect(screen.getByTestId('ecg-chart')).toBeInTheDocument()
    expect(button('Earlier')).toBeEnabled()
    expect(button('Later')).toBeEnabled()
  })

  it('shows the error with a retry instead of a blank chart', () => {
    render(
      <WaveformPanel
        {...base}
        loading={false}
        windowLoading={false}
        windowError="Telemetry request failed."
        onRetry={() => {}}
      />,
    )

    expect(screen.getByText('Telemetry request failed.')).toBeInTheDocument()
    expect(screen.queryByTestId('ecg-chart')).not.toBeInTheDocument()
  })

  it('shows the index spinner before the chunk list exists', () => {
    render(<WaveformPanel {...base} loading windowLoading={false} />)

    expect(screen.getByText(/Loading the recording index/)).toBeInTheDocument()
    expect(screen.queryByTestId('ecg-chart')).not.toBeInTheDocument()
    expect(screen.queryByText('Earlier')).not.toBeInTheDocument()
  })
})
