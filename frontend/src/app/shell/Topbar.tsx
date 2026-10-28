import { useNow } from '@/shared/hooks/useNow'
import { Icon } from '@/shared/icons/Icon'
import { formatDate, formatTime } from '@/shared/lib/format'
import { GlobalSearch } from './GlobalSearch'
import { pageTitle } from './nav'
import { Notifications } from './Notifications'
import { UserMenu } from './UserMenu'

export function Topbar({
  pathname,
  sidebarOpen,
  onToggleSidebar,
}: {
  pathname: string
  sidebarOpen: boolean
  onToggleSidebar: () => void
}) {
  const now = useNow(30_000)

  return (
    <header className="topbar">
      <button
        type="button"
        className="icon-button topbar__menu"
        onClick={onToggleSidebar}
        aria-label="Toggle navigation"
      >
        <Icon name={sidebarOpen ? 'close' : 'menu'} size={20} />
      </button>

      <GlobalSearch />
      <span className="topbar__page">{pageTitle(pathname)}</span>

      <div className="topbar__right">
        <span className="topbar__clock">
          <Icon name="clock" size={15} />
          {formatDate(now.toISOString())} · {formatTime(now.toISOString())}
        </span>
        <Notifications />
        <UserMenu />
      </div>
    </header>
  )
}
