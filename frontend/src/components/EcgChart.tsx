import { useEffect, useRef, useState } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'

const AXIS_COLOR = '#7f8aa0'
const GRID_COLOR = 'rgba(148, 163, 184, 0.09)'
const FONT = '11px ui-sans-serif, system-ui, sans-serif'

interface EcgChartProps {
  x: number[]
  y: number[]
  height?: number
  color?: string
  emptyLabel?: string
  unit?: string
}

/**
 * A thin uPlot wrapper: one line, a dark grid and no legend.
 *
 * uPlot owns its canvas, so React never re-renders 2 000 points. The component
 * measures its container and hands uPlot a new width instead of relying on a
 * window resize listener, which also handles the sidebar collapsing.
 */
export function EcgChart({
  x,
  y,
  height = 300,
  color = '#2dd4bf',
  emptyLabel = 'Waiting for the first ECG chunk…',
  unit = 'mV',
}: EcgChartProps) {
  const hostRef = useRef<HTMLDivElement>(null)
  const plotRef = useRef<uPlot | null>(null)
  const [width, setWidth] = useState(0)

  useEffect(() => {
    const host = hostRef.current
    if (!host) return

    setWidth(Math.max(10, Math.floor(host.clientWidth)))
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (entry) setWidth(Math.max(10, Math.floor(entry.contentRect.width)))
    })
    observer.observe(host)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    const host = hostRef.current
    if (!host || width < 10) return

    const plot = new uPlot(
      {
        width,
        height,
        padding: [10, 12, 0, 0],
        legend: { show: false },
        cursor: { show: true, drag: { x: true, y: false } },
        scales: {
          x: { time: false },
          y: {
            range: (_u, _min, max) => [-Math.max(1, Math.abs(max) * 0.9), Math.max(1, Math.abs(max) * 1.1)],
          },
        },
        axes: [
          {
            stroke: AXIS_COLOR,
            font: FONT,
            size: 30,
            grid: { stroke: GRID_COLOR, width: 1 },
            ticks: { stroke: 'rgba(148, 163, 184, 0.18)', width: 1, size: 4 },
            label: 'seconds',
            labelSize: 18,
            labelFont: FONT,
          },
          {
            stroke: AXIS_COLOR,
            font: FONT,
            size: 46,
            grid: { stroke: GRID_COLOR, width: 1 },
            ticks: { stroke: 'rgba(148, 163, 184, 0.18)', width: 1, size: 4 },
            label: unit,
            labelSize: 18,
            labelFont: FONT,
            values: (_u, values) => values.map((value) => value.toFixed(1)),
          },
        ],
        series: [
          {},
          {
            label: 'ECG',
            stroke: color,
            width: 1.6,
            fill: `${color}14`,
            points: { show: false },
          },
        ],
      },
      [[], []],
      host,
    )

    plotRef.current = plot
    return () => {
      plot.destroy()
      plotRef.current = null
    }
  }, [width, height, color, unit])

  useEffect(() => {
    plotRef.current?.setData([x, y])
  }, [x, y])

  return (
    <div className="chart" style={{ height }}>
      <div ref={hostRef} className="chart__canvas" />
      {x.length === 0 && (
        <div className="chart__empty">
          <span className="chart__empty-line" />
          {emptyLabel}
        </div>
      )}
    </div>
  )
}
