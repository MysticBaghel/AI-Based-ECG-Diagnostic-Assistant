import type { EcgChunk } from '@/shared/types'

export interface EcgSeries {
  x: number[]
  y: number[]
  durationSeconds: number
  sampleCount: number
}

/**
 * Turn stored chunks into the two arrays uPlot wants.
 *
 * x is seconds relative to either the first sample (history view) or the end of
 * the requested window (live view). Chunk `start_time` is used rather than a
 * running counter so a dropped chunk appears as a real gap instead of silently
 * squashing the waveform.
 */
export function buildEcgSeries(
  chunks: EcgChunk[],
  options: { maxSeconds?: number } = {},
): EcgSeries {
  const ordered = [...chunks].sort((a, b) => a.chunk_index - b.chunk_index)
  if (ordered.length === 0) {
    return { x: [], y: [], durationSeconds: 0, sampleCount: 0 }
  }

  const starts = ordered.map((chunk) => Date.parse(chunk.start_time))
  const ends = starts.map(
    (start, index) =>
      start + (ordered[index].sample_count / ordered[index].sample_rate_hz) * 1000,
  )
  const endMs = Math.max(...ends)
  const originMs =
    options.maxSeconds !== undefined
      ? endMs - options.maxSeconds * 1000
      : Math.min(...starts)

  const x: number[] = []
  const y: number[] = []

  ordered.forEach((chunk, index) => {
    const start = starts[index]
    if (Number.isNaN(start)) return
    const step = 1000 / chunk.sample_rate_hz

    chunk.samples.forEach((sample, sampleIndex) => {
      const seconds = (start + sampleIndex * step - originMs) / 1000
      if (seconds >= 0) {
        x.push(Number(seconds.toFixed(4)))
        y.push(sample)
      }
    })
  })

  return {
    x,
    y,
    durationSeconds: (endMs - originMs) / 1000,
    sampleCount: y.length,
  }
}

/** Best-effort BPM is Phase 5 work; this only reports the observed rate. */
export function describeRate(chunks: EcgChunk[]): number | null {
  if (chunks.length === 0) return null
  const counts = new Map<number, number>()
  for (const chunk of chunks) {
    counts.set(chunk.sample_rate_hz, (counts.get(chunk.sample_rate_hz) ?? 0) + 1)
  }
  let best: number | null = null
  let bestCount = 0
  for (const [rate, count] of counts) {
    if (count > bestCount) {
      best = rate
      bestCount = count
    }
  }
  return best
}
