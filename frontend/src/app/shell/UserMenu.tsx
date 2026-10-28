import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { useAuth } from '@/features/auth/useAuth'
import { Icon } from '@/shared/icons/Icon'
import { initials } from '@/shared/lib/format'

export function UserMenu() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const hostRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function onClick(event: MouseEvent) {
      if (!hostRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  if (!user) return null

  return (
    <div className="topbar-user" ref={hostRef}>
      <button
        type="button"
        className="topbar-user__button"
        onClick={() => setOpen((value) => !value)}
        aria-label="Account menu"
      >
        <span className="avatar">{initials(user.username)}</span>
        <span className="topbar-user__name">
          <strong>{user.username}</strong>
          <small>{user.role === 'admin' ? 'Admin' : 'Operator'}</small>
        </span>
        <Icon name="chevron-down" size={15} />
      </button>
      {open && (
        <div className="topbar-popover topbar-popover--user">
          <Link to="/settings" onClick={() => setOpen(false)}>
            <Icon name="settings" size={16} />
            Settings
          </Link>
          <button
            type="button"
            onClick={() => {
              setOpen(false)
              logout()
              navigate('/login', { replace: true })
            }}
          >
            <Icon name="logout" size={16} />
            Sign out
          </button>
        </div>
      )}
    </div>
  )
}
