import { render, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { plots } = vi.hoisted(() => ({
  plots: [] as { data: unknown }[],
}))

vi.mock('uplot', () => {
  class FakeUPlot {
    data: unknown

    constructor(_options: unknown, data: unknown, host: HTMLElement) {
      this.data = data
      plots.push(this)
      void host
    }

    setData(data: unknown) {
      this.data = data
    }

    destroy() {}
  }

  return { default: FakeUPlot }
})

import { EcgChart } from './EcgChart'

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

describe('EcgChart', () => {
  beforeEach(() => {
    plots.length = 0
    vi.stubGlobal('ResizeObserver', ResizeObserverStub)
    // jsdom reports a zero-width layout; the chart waits for a real width.
    Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
      configurable: true,
      get: () => 640,
    })
  })

  it('applies samples that were already present when the plot was created', async () => {
    // The analysis page renders a spinner until the window's chunks arrive, so
    // this component mounts with `x`/`y` populated - the case that used to
    // produce a blank grid.
    render(<EcgChart x={[0, 0.5, 1]} y={[0.1, 0.2, 0.1]} height={250} theme="paper" />)

    await waitFor(() => expect(plots.length).toBeGreaterThan(0))
    const plot = plots[plots.length - 1]
    expect(plot.data).toEqual([
      [0, 0.5, 1],
      [0.1, 0.2, 0.1],
    ])
  })
})
