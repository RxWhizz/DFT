import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useVirtualizer } from '@tanstack/react-virtual'
import { useRef, useState } from 'react'

import { JobDetail } from '@/components/JobDetail'
import { StatusBadge } from '@/components/StatusBadge'
import { api, type JobStatus, type JobsQuery } from '@/lib/api'
import { fmtDuration, fmtFormula } from '@/lib/format'

const ESTADOS = [
  { value: '', label: 'Todos' },
  { value: 'running,stalled,oscillating', label: 'Activos' },
  { value: 'converged', label: 'Convergidos' },
  { value: 'failed,stopped', label: 'Fallidos' },
  { value: 'pending', label: 'En cola' },
  { value: 'skipped_duplicate', label: 'Duplicados' },
]

/** Se piden bastantes filas por página porque la tabla está virtualizada. */
const PAGE = 500
const ROW_H = 34

export function Jobs() {
  const [status, setStatus] = useState('')
  const [q, setQ] = useState('')
  const [sort, setSort] = useState<NonNullable<JobsQuery['sort']>>('formula')
  const [desc, setDesc] = useState(false)
  const [offset, setOffset] = useState(0)
  const [selected, setSelected] = useState<JobStatus | null>(null)

  const { data, isFetching } = useQuery({
    queryKey: ['jobs', { status, q, sort, desc, offset }],
    queryFn: () => api.jobs({ status, q, sort, desc, limit: PAGE, offset }),
    placeholderData: keepPreviousData,
    refetchInterval: 20_000,
  })

  const items = data?.items ?? []
  const scroller = useRef<HTMLDivElement>(null)
  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => scroller.current,
    estimateSize: () => ROW_H,
    overscan: 12,
  })

  function ordenarPor(col: NonNullable<JobsQuery['sort']>) {
    if (col === sort) setDesc((d) => !d)
    else {
      setSort(col)
      setDesc(false)
    }
    setOffset(0)
  }

  const total = data?.total ?? 0
  const hasta = Math.min(offset + PAGE, total)

  return (
    <div className={`grid gap-4 ${selected ? 'lg:grid-cols-[1fr_minmax(28rem,40%)]' : ''}`}>
      <div className="min-w-0 space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <input
            className="input max-w-xs"
            placeholder="Buscar fórmula o job_id…"
            value={q}
            onChange={(e) => {
              setQ(e.target.value)
              setOffset(0)
            }}
          />
          <div className="flex flex-wrap gap-1">
            {ESTADOS.map((e) => (
              <button
                key={e.value}
                onClick={() => {
                  setStatus(e.value)
                  setOffset(0)
                }}
                className={`rounded-md px-2.5 py-1 text-xs transition ${
                  status === e.value
                    ? 'bg-st-running/20 text-blue-200'
                    : 'text-ink-400 hover:bg-ink-850 hover:text-ink-100'
                }`}
              >
                {e.label}
              </button>
            ))}
          </div>
          <span className="tnum ml-auto text-xs text-ink-400">
            {total ? `${offset + 1}–${hasta} de ${total}` : 'sin resultados'}
            {isFetching && ' · actualizando'}
          </span>
        </div>

        <div className="card overflow-hidden">
          {/* Cabecera fuera del contenedor con scroll para que quede fija. */}
          <div className="label grid grid-cols-[1fr_8rem_6rem_4rem_8rem] gap-2 border-b border-ink-800 bg-ink-850 px-3 py-2">
            <Th onClick={() => ordenarPor('formula')} active={sort === 'formula'} desc={desc}>
              Fórmula
            </Th>
            <Th onClick={() => ordenarPor('status')} active={sort === 'status'} desc={desc}>
              Estado
            </Th>
            <Th
              onClick={() => ordenarPor('elapsed_min')}
              active={sort === 'elapsed_min'}
              desc={desc}
            >
              Duración
            </Th>
            <span>Cores</span>
            <Th onClick={() => ordenarPor('job_id')} active={sort === 'job_id'} desc={desc}>
              Job ID
            </Th>
          </div>

          <div ref={scroller} className="h-[calc(100vh-16rem)] overflow-auto">
            {!items.length ? (
              <p className="px-3 py-6 text-center text-sm text-ink-400">
                Sin jobs que coincidan con el filtro.
              </p>
            ) : (
              <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
                {virtualizer.getVirtualItems().map((v) => {
                  const j = items[v.index]
                  const activo = selected?.job_id === j.job_id
                  return (
                    <button
                      key={j.job_id}
                      onClick={() => setSelected(activo ? null : j)}
                      style={{
                        position: 'absolute',
                        top: 0,
                        left: 0,
                        width: '100%',
                        height: v.size,
                        transform: `translateY(${v.start}px)`,
                      }}
                      className={`grid grid-cols-[1fr_8rem_6rem_4rem_8rem] items-center gap-2 border-b
                                  border-ink-800/60 px-3 text-left text-sm transition ${
                                    activo ? 'bg-st-running/10' : 'hover:bg-ink-850/60'
                                  }`}
                    >
                      <span className="truncate font-medium">{fmtFormula(j.formula)}</span>
                      <StatusBadge status={j.status} />
                      <span className="tnum text-xs text-ink-300">
                        {fmtDuration(j.elapsed_min)}
                      </span>
                      <span className="tnum text-xs text-ink-400">{j.mpi_cores ?? '—'}</span>
                      <span className="truncate font-mono text-xs text-ink-400">
                        {j.job_id.slice(0, 10)}
                      </span>
                    </button>
                  )
                })}
              </div>
            )}
          </div>
        </div>

        {total > PAGE && (
          <div className="flex items-center justify-end gap-2">
            <button
              className="btn"
              disabled={offset === 0}
              onClick={() => setOffset((o) => Math.max(0, o - PAGE))}
            >
              Anterior
            </button>
            <button
              className="btn"
              disabled={hasta >= total}
              onClick={() => setOffset((o) => o + PAGE)}
            >
              Siguiente
            </button>
          </div>
        )}
      </div>

      {selected && (
        <div className="h-[calc(100vh-9rem)]">
          <JobDetail job={selected} onClose={() => setSelected(null)} />
        </div>
      )}
    </div>
  )
}

function Th({
  children,
  onClick,
  active,
  desc,
}: {
  children: React.ReactNode
  onClick: () => void
  active: boolean
  desc: boolean
}) {
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center gap-1 text-left transition hover:text-ink-100 ${
        active ? 'text-ink-100' : ''
      }`}
    >
      {children}
      {active && <span aria-hidden>{desc ? '↓' : '↑'}</span>}
    </button>
  )
}
