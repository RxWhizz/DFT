import { useQuery } from '@tanstack/react-query'

import { api } from '@/lib/api'

/**
 * Aviso de volumen caído.
 *
 * `runs/` y `calculations/` son symlinks a un disco externo. Desmontado, el
 * poller no ve jobs y el panel se queda vacío y en calma — indistinguible de
 * "no hay trabajo". Este banner es la señal que faltaba.
 */
export function HealthBanner() {
  const { data } = useQuery({
    queryKey: ['health'],
    queryFn: api.health,
    refetchInterval: 15_000,
  })

  if (!data || data.ok) return null

  const congelado = data.runs_mounted
  const edad = data.last_poll_age_sec

  return (
    <div className="border-b border-st-failed/40 bg-st-failed/10 px-4 py-2.5 text-sm">
      {congelado ? (
        <>
          <span className="font-semibold text-red-300">Poller sin responder.</span>{' '}
          <span className="text-ink-300">
            Último sondeo hace {edad != null ? `${Math.round(edad)} s` : 'un tiempo indeterminado'}{' '}
            (intervalo configurado: {data.poll_interval_sec} s).
          </span>
        </>
      ) : (
        <>
          <span className="font-semibold text-red-300">Volumen de datos no disponible.</span>{' '}
          <span className="text-ink-300">
            No se puede leer <code className="font-mono text-xs">{data.runs_dir}</code>. La cadena
            se rompe a partir de{' '}
            <code className="font-mono text-xs">{data.nearest_existing_path}</code> — probablemente
            el disco externo no está montado. Los jobs listados pueden estar incompletos.
          </span>
        </>
      )}
    </div>
  )
}
