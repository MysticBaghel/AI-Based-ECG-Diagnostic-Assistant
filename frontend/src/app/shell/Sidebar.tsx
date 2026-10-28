import { NavLink } from 'react-router-dom'

import { Icon } from '@/shared/icons/Icon'
import { NAV, isNavActive } from './nav'

export function Sidebar({
  pathname,
  open,
  onNavigate,
}: {
  pathname: string
  open: boolean
  onNavigate: () => void
}) {
  return (
    <aside className={`sidebar${open ? ' sidebar--open' : ''}`}>
      <NavLink to="/" className="brand" aria-label="PulseTrace ECG dashboard" onClick={onNavigate}>
        <span className="brand__mark">
          <Icon name="pulse" size={24} />
        </span>
        <span className="brand__text">
          <strong>PulseTrace ECG</strong>
        </span>
      </NavLink>

      <nav className="nav" aria-label="Main navigation">
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.exact}
            onClick={onNavigate}
            className={`nav-link${isNavActive(item, pathname) ? ' nav-link--active' : ''}`}
          >
            <Icon name={item.icon} size={18} />
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="sidebar__note">
        <Icon name="shield" size={15} />
        <span>Screening aid. Not a medical diagnosis.</span>
      </div>
    </aside>
  )
}
