import { describe, expect, it } from 'vitest'

import { buildEcgSeries } from './ecg'

describe('buildEcgSeries', () => {
  it('orders chunks and preserves gaps from start times', () => {
    const series = buildEcgSeries([
      {
        chunk_id: 'b',
        chunk_index: 1,
        sample_rate_hz: 2,
        sample_count: 2,
        start_time: '2026-10-28T10:00:02Z',
        duration_seconds: 1,
        session_id: 'session',
        device_id: 'device',
        samples: [2, 3],
      },
      {
        chunk_id: 'a',
        chunk_index: 0,
        sample_rate_hz: 2,
        sample_count: 2,
        start_time: '2026-10-28T10:00:00Z',
        duration_seconds: 1,
        session_id: 'session',
        device_id: 'device',
        samples: [0, 1],
      },
    ])

    expect(series.y).toEqual([0, 1, 2, 3])
    expect(series.sampleCount).toBe(4)
    expect(series.durationSeconds).toBe(3)
    expect(series.x[2]).toBeGreaterThan(1.9)
  })
})
