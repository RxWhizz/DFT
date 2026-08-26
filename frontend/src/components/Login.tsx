import { useState, type FormEvent } from 'react'

import { useAuth } from '@/lib/auth'

export function Login() {
  const { login, loginError, loggingIn } = useAuth()
  const [token, setToken] = useState('')

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!token.trim()) return
    try {
      await login(token.trim())
    } catch {
      /* el error se muestra desde loginError */
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <form onSubmit={onSubmit} className="card-pad w-full max-w-sm space-y-4">
        <div>
          <h1 className="text-lg font-semibold">Monitor DFT</h1>
          <p className="mt-1 text-sm text-ink-400">
            Introduce el token de acceso para continuar.
          </p>
        </div>

        <div className="space-y-1.5">
          <label htmlFor="token" className="label block">
            Token
          </label>
          <input
            id="token"
            type="password"
            autoFocus
            autoComplete="current-password"
            className="input font-mono"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="••••••••••••••••"
          />
        </div>

        {loginError && (
          <p className="rounded-md border border-st-failed/40 bg-st-failed/10 px-3 py-2 text-sm text-red-300">
            {loginError}
          </p>
        )}

        <button type="submit" className="btn-primary w-full" disabled={loggingIn || !token.trim()}>
          {loggingIn ? 'Comprobando…' : 'Entrar'}
        </button>

        <p className="text-xs leading-relaxed text-ink-400">
          El token se define en <code className="font-mono">monitor.auth.token</code> dentro de{' '}
          <code className="font-mono">configs/monitor.yaml</code>, o en la variable de entorno{' '}
          <code className="font-mono">DFT_MONITOR_TOKEN</code>.
        </p>
      </form>
    </div>
  )
}
