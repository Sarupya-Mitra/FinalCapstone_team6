import { useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { ROLE_HOME, ROLE_LABEL, useAuth } from '../auth/AuthContext'
import { Container } from './ui'

const NAV = {
  clerk: [
    { to: '/clerk', label: 'Invoices', end: true },
    { to: '/clerk/upload', label: 'Upload' },
    { to: '/clerk/vendors', label: 'Vendors' },
  ],
  approver: [{ to: '/approver', label: 'Approval queue', end: true }],
  auditor: [{ to: '/auditor', label: 'Audit trail', end: true }],
}

export function Logo({ to = '/' }) {
  return (
    <Link to={to} className="flex items-center gap-3 shrink-0">
      <span className="grid place-items-center size-9 bg-surface-dark">
        <svg viewBox="0 0 24 24" className="size-5" fill="none" aria-hidden>
          <path d="M6 3h9l3 3v15H6z" stroke="#fff" strokeWidth="1.8" />
          <path d="M9 11h6M9 15h6" stroke="#1c69d4" strokeWidth="1.8" />
        </svg>
      </span>
      <span className="text-[15px] font-bold text-ink leading-tight">
        Invoice<span className="font-light">Processing</span>
      </span>
    </Link>
  )
}

function initials(name = '') {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((s) => s[0].toUpperCase())
    .join('')
}

export default function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  const [openedAt, setOpenedAt] = useState(location.pathname)
  const links = NAV[user?.role] || []

  // Close the mobile menu when the route changes.
  if (menuOpen && openedAt !== location.pathname) setMenuOpen(false)

  const handleLogout = () => {
    logout()
    navigate('/login', { replace: true })
  }

  const navLinkCls = ({ isActive }) =>
    `relative h-16 inline-flex items-center text-[14px] tracking-[0.3px] transition-colors ${
      isActive
        ? 'text-primary font-bold after:absolute after:inset-x-0 after:bottom-0 after:h-0.5 after:bg-primary'
        : 'text-ink font-normal hover:text-primary'
    }`

  return (
    <div className="min-h-screen flex flex-col">
      <header className="sticky top-0 z-40 bg-canvas border-b border-hairline">
        <Container className="h-16 flex items-center justify-between gap-6">
          <Logo to={ROLE_HOME[user?.role] || '/'} />

          <nav className="hidden md:flex items-center gap-8 flex-1 ml-6">
            {links.map((l) => (
              <NavLink key={l.to} to={l.to} end={l.end} className={navLinkCls}>
                {l.label}
              </NavLink>
            ))}
          </nav>

          <div className="hidden md:flex items-center gap-4">
            <div className="text-right leading-tight">
              <p className="text-[14px] font-bold text-ink">{user?.name}</p>
              <p className="caption text-muted">{ROLE_LABEL[user?.role]}</p>
            </div>
            <span className="grid place-items-center size-9 rounded-full bg-surface-strong text-[12px] font-bold text-ink">
              {initials(user?.name)}
            </span>
            <button onClick={handleLogout} className="label-upper text-muted hover:text-ink ml-2">
              Sign out
            </button>
          </div>

          <button
            className="md:hidden grid place-items-center size-10 -mr-2"
            onClick={() => {
              setOpenedAt(location.pathname)
              setMenuOpen((o) => !o)
            }}
            aria-label="Menu"
            aria-expanded={menuOpen}
          >
            <svg viewBox="0 0 24 24" className="size-6" fill="none" stroke="currentColor" strokeWidth="1.8">
              {menuOpen ? <path d="M6 6l12 12M18 6L6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}
            </svg>
          </button>
        </Container>

        {menuOpen && (
          <div className="md:hidden fixed inset-x-0 top-16 bottom-0 bg-canvas z-40 overflow-y-auto">
            <Container className="py-6 flex flex-col">
              {links.map((l) => (
                <NavLink
                  key={l.to}
                  to={l.to}
                  end={l.end}
                  className={({ isActive }) =>
                    `py-4 border-b border-hairline text-title-md ${isActive ? 'text-primary font-bold' : 'text-ink font-light'}`
                  }
                >
                  {l.label}
                </NavLink>
              ))}
              <div className="mt-8">
                <p className="text-title-sm text-ink">{user?.name}</p>
                <p className="text-body-sm text-muted">
                  {user?.email} · {ROLE_LABEL[user?.role]}
                </p>
                <button onClick={handleLogout} className="mt-6 label-upper text-ink">
                  Sign out ›
                </button>
              </div>
            </Container>
          </div>
        )}
      </header>

      <main className="flex-1">
        <Outlet />
      </main>

      <footer className="bg-surface-soft mt-section">
        <Container className="py-10 flex flex-col sm:flex-row gap-4 justify-between text-body-sm text-muted">
          <p>AI-Powered Invoice Processing &amp; Approval · Capstone Team 6</p>
          <p>
            Signed in as {user?.email} ({ROLE_LABEL[user?.role]})
          </p>
        </Container>
      </footer>
    </div>
  )
}
