import type { CSSProperties } from 'react'

import type { Reading, SensorType } from '../api/types'
import {
  formatNumber,
  formatRelative,
  formatTime,
  SENSOR_META,
} from '../lib/format'
import { Icon, type IconName } from './Icon'
import { Sparkline } from './Sparkline'

const SENSOR_ICON: Record<SensorType, IconName> = {
  pulse: 'heart',
  spo2: 'droplet',
  temperature: 'thermometer',
  motion: 'activity',
}

export function VitalCard({
  sensor,
  reading,
  history,
  live,
}: {
  sensor: SensorType
  reading: Reading | undefined
  history: Reading[]
  live: boolean
}) {
  const meta = SENSOR_META[sensor]
  const values = history.map((item) => item.value)

  return (
    <article
      className={`vital${reading ? '' : ' vital--empty'}`}
      style={{ '--vital-accent': meta.accent } as CSSProperties}
    >
      <header className="vital__header">
        <span className="vital__icon">
          <Icon name={SENSOR_ICON[sensor]} size={18} />
        </span>
        <span className="vital__label">{meta.label}</span>
        {live && <span className="vital__live" title="streaming" />}
      </header>

      <div className="vital__value">
        <strong>{reading ? formatNumber(reading.value, meta.digits) : '—'}</strong>
        <span className="vital__unit">{reading?.unit ?? meta.unit}</span>
      </div>

      <div className="vital__spark">
        <Sparkline values={values} color={meta.accent} width={150} height={36} />
      </div>

      <footer className="vital__footer">
        {reading ? (
          <>
            <span>{formatTime(reading.recorded_at)}</span>
            <span>{formatRelative(reading.recorded_at)}</span>
          </>
        ) : (
          <span>Waiting for the first reading</span>
        )}
      </footer>
    </article>
  )
}
