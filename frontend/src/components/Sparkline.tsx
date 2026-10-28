import { useId, useMemo } from 'react'

export function Sparkline({
  values,
  color = '#2dd4bf',
  width = 140,
  height = 38,
}: {
  values: number[]
  color?: string
  width?: number
  height?: number
}) {
  const gradientId = useId()

  const { line, area } = useMemo(() => {
    if (values.length < 2) return { line: '', area: '' }

    const min = Math.min(...values)
    const max = Math.max(...values)
    const span = max - min || 1
    const stepX = width / (values.length - 1)

    const points = values.map((value, index) => {
      const x = index * stepX
      const y = height - 3 - ((value - min) / span) * (height - 6)
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })

    return {
      line: `M ${points.join(' L ')}`,
      area: `M 0,${height} L ${points.join(' L ')} L ${width},${height} Z`,
    }
  }, [values, width, height])

  return (
    <svg
      className="sparkline"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="Recent trend"
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.28" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      {area && <path d={area} fill={`url(#${gradientId})`} />}
      {line && (
        <path
          d={line}
          fill="none"
          stroke={color}
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      )}
    </svg>
  )
}
