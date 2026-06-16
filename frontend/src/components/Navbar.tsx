import { NavLink } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { useApi } from '../hooks/useApi'
import { api } from '../api/client'

const links = [
  { to: '/docs',      label: 'docs' },
  { to: '/commands',  label: 'commands' },
  { to: '/agents',    label: 'agents' },
  { to: '/dashboard', label: 'dashboard' },
]

export default function Navbar() {
  const [scrolled, setScrolled] = useState(false)
  const { data: status } = useApi(() => api.status(), [], { interval: 30_000 })

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  const isLive = status?.status === 'healthy'

  return (
    <header
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
        scrolled
          ? 'bg-black/90 backdrop-blur-md border-b border-bg-border'
          : 'bg-transparent'
      }`}
    >
      <div className="max-w-7xl mx-auto px-6 h-14 flex items-center">

        {/* Logo — left */}
        <NavLink to="/" className="flex items-center gap-2 shrink-0 group">
          <span className="font-display font-bold text-[14px] text-white group-hover:text-orange-400 transition-colors tracking-tight">
            sentinel
          </span>
        </NavLink>

        {/* Nav links + status — pushed to right */}
        <div className="ml-auto flex items-center gap-8">
          <nav className="flex items-center gap-6">
            {links.map(({ to, label }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `font-mono text-xs transition-colors duration-150 whitespace-nowrap ${
                    isActive ? 'text-orange-400' : 'text-text-muted hover:text-white'
                  }`
                }
              >
                {label}
              </NavLink>
            ))}
          </nav>

          {/* Status pill */}
          <div className="flex items-center gap-2 shrink-0">
            <span className={`w-1.5 h-1.5 rounded-full transition-colors ${
              isLive ? 'bg-white animate-pulse-slow' : 'bg-orange-400'
            }`} />
            <span className="font-mono text-xs text-text-muted hidden sm:block">
              {isLive ? 'live' : 'connecting'}
            </span>
          </div>
        </div>
      </div>
    </header>
  )
}
