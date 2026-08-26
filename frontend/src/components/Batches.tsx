import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { ConfirmButton } from './ConfirmButton'
import { api, type Batch } from '@/lib/api'
import { usePlatform } from '@/lib/usePlatform'
import { fmtEta } from '@/lib/format'

const ORDEN = ['converged', 'running', 'pending', 'failed', 'stopped', 'skipped_duplicate']
const COLOR: Record<string, string> = {
  converged: 'bg-st-converged',
  running: 'bg-st-running',
  pending: 'bg-st-pending',
  failed: 'bg-st-failed',
  stopped: 'bg-st-stopped',
  skipped_duplicate: 'bg-st-skipped',
}

export function Batches() {
  const plataforma = usePlatform()
  const qc = useQueryClient()
  const [aviso, setAviso] = useState<string | null>(null)

  const { data } = useQuery({ queryKey: ['batches'], queryFn: api.batches, refetchInterval: 30_000 })

  const arrancar = useMutation({
    mutationFn: (id: number) => api.startBatch(id),
    onSuccess: (r) => {
      setAviso(`Runner ${r.runner_kind} lanzado para batch_${String(r.batch_id).padStart(3, '0')}.`)
      void qc.invalidateQueries({ queryKey: ['batches'] })
    },
    onError: (e) => setAviso((e as Error).message),
  })

  if (!data?.items.length) return null

  return (
    <section className="card-pad">
      <header className="mb-3 flex flex-wrap items-baseline gap-x-3">
        <h2 className="label">Batches ({data.items.length})</h2>
        <span className="text-xs text-ink-400">
          runner: <code className="font-mono">{data.runner_kind}</code>
        </span>
      </header>

      <ul className="space-y-2">
        {data.items.map((b) => (
          <Fila
            key={b.name}
            b={b}
            puedeLanzar={plataforma.runner_launch}
            onStart={() => arrancar.mutate(b.batch_id)}
            pending={arrancar.isPending && arrancar.variables === b.batch_id}
          />
        ))}
      </ul>

      {!plataforma.runner_launch && (
        <p className="mt-2 text-xs text-ink-400">
          Lanzar runners no está disponible en esta máquina: falta un intérprete de Python o los{' '}
          <code className="font-mono">scripts/</code> del pipeline en la raíz de datos.
        </p>
      )}
      {aviso && <p className="mt-2 text-xs text-ink-300">{aviso}</p>}
    </section>
  )
}

function Fila({
  b,
  onStart,
  pending,
  puedeLanzar,
}: {
  b: Batch
  onStart: () => void
  pending: boolean
  puedeLanzar: boolean
}) {
  const total = b.total || 1

  return (
    <li className="flex flex-wrap items-center gap-3 text-sm">
      <span className={`w-24 shrink-0 font-medium ${b.is_current ? 'text-blue-200' : ''}`}>
        {b.name}
        {b.is_current && <span className="ml-1 text-[10px] text-ink-400">activo</span>}
      </span>

      {/* Barra apilada por estado */}
      <div className="flex h-2.5 min-w-40 flex-1 overflow-hidden rounded bg-ink-950">
        {ORDEN.filter((k) => b.counts[k]).map((k) => (
          <div
            key={k}
            className={COLOR[k] ?? 'bg-st-unknown'}
            style={{ width: `${(b.counts[k] / total) * 100}%` }}
            title={`${k}: ${b.counts[k]}`}
          />
        ))}
      </div>

      <span className="tnum w-28 shrink-0 text-xs text-ink-400">
        {b.counts.converged ?? 0}/{b.total}
      </span>
      <span className="tnum w-32 shrink-0 text-xs text-ink-400">
        {b.rate_per_hour != null ? `${b.rate_per_hour} jobs/h` : '—'}
        {b.eta_sec != null && ` · ${fmtEta(b.eta_sec)}`}
      </span>

      {b.n_pending > 0 && puedeLanzar && (
        <ConfirmButton
          onConfirm={onStart}
          confirmLabel="Sí, lanzar"
          pending={pending}
          className="btn px-2 py-1 text-xs"
        >
          Lanzar runner
        </ConfirmButton>
      )}
    </li>
  )
}
