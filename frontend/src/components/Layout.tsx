import { NavLink, Outlet } from 'react-router-dom'

import { HealthBanner } from './HealthBanner'
import { useAuth } from '@/lib/auth'
import { usePlatform, useVersion } from '@/lib/usePlatform'
import type { ConnState } from '@/lib/useEvents'

const NAV = [
  { to: '/', label: 'Live', end: true },
  { to: '/agent', label: 'Agente' },
  { to: '/jobs', label: 'Jobs' },
  { to: '/screening', label: 'Cribado' },
  { to: '/candidates', label: 'Candidatos' },
  { to: '/ml', label: 'ML' },
  { to: '/structures', label: 'Estructuras' },
  { to: '/results', label: 'Resultados' },
]

const CONN: Record<ConnState, { dot: string; text: string }> = {
  open: { dot: 'bg-st-converged', text: 'en vivo' },
  connecting: { dot: 'bg-st-stalled animate-pulse', text: 'conectando' },
  closed: { dot: 'bg-st-failed', text: 'sin conexión' },
  unauthorized: { dot: 'bg-st-failed', text: 'sesión caducada' },
}

export function Layout({ conn }: { conn: ConnState }) {
  const { state, logout } = useAuth()
  const version = useVersion()
  const plataforma = usePlatform()
  const c = CONN[conn]

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center gap-6 border-b border-ink-800 bg-ink-900 px-4">
        <span className="flex shrink-0 items-baseline gap-1.5 py-3">
          <span className="text-sm font-semibold tracking-tight">Monitor DFT</span>
          {version && <span className="tnum text-[10px] text-ink-400">v{version}</span>}
        </span>

        <nav className="flex flex-1 items-center gap-1 overflow-x-auto">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `whitespace-nowrap border-b-2 px-3 py-3 text-sm transition ${
                  isActive
                    ? 'border-st-running text-ink-100'
                    : 'border-transparent text-ink-400 hover:text-ink-100'
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="flex shrink-0 items-center gap-4">
          <span className="flex items-center gap-1.5 text-xs text-ink-400">
            <span className={`h-1.5 w-1.5 rounded-full ${c.dot}`} />
            {c.text}
          </span>
          {plataforma.auto_advance && (
            <span
              className="flex items-center gap-1.5 rounded border border-st-stalled/40 bg-st-stalled/10 px-2 py-1 text-[11px] text-amber-300"
              title="Al terminar un lote, el monitor lanza el siguiente runner o reentrena por su cuenta. Se desactiva con monitor.auto_advance: false."
            >
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M5 4l14 8-14 8V4z" />
              </svg>
              avance automático
            </span>
          )}
          {state?.auth_enabled && (
            <button onClick={() => void logout()} className="text-xs text-ink-400 hover:text-ink-100">
              Salir
            </button>
          )}
        </div>
      </header>

      <HealthBanner />

      <main className="flex-1 p-4">
        <Outlet />
      </main>
    </div>
  )
}
