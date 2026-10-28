import { PageHeader, SessionBadge } from '@/shared/ui'
import { Icon } from '@/shared/icons/Icon'
import type { Session } from '@/shared/types'

export function AnalysisHeader({
  session,
  busy,
  onDownload,
  onRegenerate,
}: {
  session: Session
  busy: 'analyse' | 'report' | 'regenerate' | null
  onDownload: () => void
  onRegenerate: () => void
}) {
  const active = session.status === 'active'
  return (
    <div className="monitor-header">
      <PageHeader
        title="ECG Analysis & Report"
        description="View AI analysis results and download report"
      />
      <div className="monitor-header__badges">
        <SessionBadge status={session.status} />
        <button
          type="button"
          className="button button--primary"
          onClick={onDownload}
          disabled={active || busy !== null}
        >
          <Icon name="download" size={15} />
          {busy === 'report' ? 'Preparing…' : 'Download PDF'}
        </button>
        <button
          type="button"
          className="button button--ghost"
          onClick={onRegenerate}
          disabled={active || busy !== null}
        >
          <Icon name="refresh" size={15} />
          {busy === 'regenerate' ? 'Regenerating…' : 'Regenerate Report'}
        </button>
      </div>
    </div>
  )
}
