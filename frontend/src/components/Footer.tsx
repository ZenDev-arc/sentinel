import { Link } from 'react-router-dom'

const links = [
  { to: '/docs',      label: 'docs' },
  { to: '/commands',  label: 'commands' },
  { to: '/agents',    label: 'agents' },
  { to: '/dashboard', label: 'dashboard' },
]

export default function Footer() {
  return (
    <footer className="border-t border-bg-border">
      <div className="max-w-7xl mx-auto px-6 py-12">
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-8">

          {/* Brand */}
          <div className="flex items-center gap-2.5">
            <svg width="18" height="18" viewBox="0 0 20 20" fill="none" className="shrink-0">
              <path d="M11 2L4 11h6l-1 7 7-9h-6l1-7z" fill="#f97316" stroke="#f97316" strokeWidth="0.5" strokeLinejoin="round" />
            </svg>
            <span className="font-display font-bold text-sm text-white">sentinel</span>
            <span className="font-mono text-xs text-text-muted ml-1">self-healing code review pipeline</span>
          </div>

          {/* Links */}
          <nav className="flex items-center gap-8 flex-wrap">
            {links.map(({ to, label }) => (
              <Link
                key={to}
                to={to}
                className="font-mono text-xs text-text-muted hover:text-orange-400 transition-colors duration-150"
              >
                {label}
              </Link>
            ))}
          </nav>
        </div>

        <div className="mt-8 pt-8 border-t border-bg-border flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <span className="font-mono text-xs text-text-muted">
            open source · mit license · built by devejya pandey
          </span>
          <div className="flex items-center gap-6">
            <span className="font-mono text-xs text-text-muted">19 agents · 5 swarms</span>
            <span className="font-mono text-xs text-orange-500/60">■ sentinel</span>
          </div>
        </div>
      </div>
    </footer>
  )
}
