import { SectionCard } from '@/shared/ui'

export function SimulatorStepsCard() {
  return (
    <SectionCard title="Simulator workflow" subtitle="No physical hardware required">
      <ol className="steps">
        <li>
          <span className="steps__number">1</span>
          <div>
            <strong>Open Patients, choose Simulate</strong>
            <p>The server registers a demo patient and starts a recording for it.</p>
          </div>
        </li>
        <li>
          <span className="steps__number">2</span>
          <div>
            <strong>Upload an ECG CSV</strong>
            <p>One voltage column, or time and voltage. Any rate from 100–2000 Hz; the server keeps it.</p>
          </div>
        </li>
        <li>
          <span className="steps__number">3</span>
          <div>
            <strong>Watch the live graph, then analyse</strong>
            <p>
              The file streams in one second at a time. Stop the recording to measure and report.
            </p>
          </div>
        </li>
      </ol>
      <p className="small muted">
        The CLI simulator still works for generated scenarios:{' '}
        <code>python -m simulator --session-id … --device-token … --ecg</code>
      </p>
    </SectionCard>
  )
}
