import { SectionCard } from '@/shared/ui'

export function SimulatorStepsCard() {
  return (
    <SectionCard title="Simulator workflow" subtitle="No physical hardware required">
      <ol className="steps">
        <li>
          <span className="steps__number">1</span>
          <div>
            <strong>Register a device</strong>
            <p>Devices issues a token once; copy it for the simulator.</p>
          </div>
        </li>
        <li>
          <span className="steps__number">2</span>
          <div>
            <strong>Start a recording</strong>
            <p>Django creates the session and pushes it to FastAPI.</p>
          </div>
        </li>
        <li>
          <span className="steps__number">3</span>
          <div>
            <strong>Run the simulator, then analyse</strong>
            <p>
              <code>python -m simulator --session-id … --device-token … --ecg</code>
            </p>
          </div>
        </li>
      </ol>
    </SectionCard>
  )
}
