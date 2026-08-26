import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { ConfirmButton } from './ConfirmButton'
import { LineChart, type Serie } from './LineChart'
import { StatusBadge } from './StatusBadge'
import { api, type JobStatus } from '@/lib/api'
import { fmtDuration, fmtEnergy, fmtEta, fmtFormula, fmtNumber } from '@/lib/format'

const MATABLES = new Set(['running', 'stalled', 'oscillating', 'pending'])
const REINTENTABLES = new Set(['failed', 'stopped', 'stalled', 'oscillating', 'partial'])

const COLORES = ['#3b82f6', '#22c55e', '#f59e0b', '#fb923c', '#8b5cf6', '#ef4444']

type Pestana = 'trazas' | 'frames' | 'log' | 'ficha'

export function JobDetail({ job, onClose }: { job: JobStatus; onClose: () => void }) {
  const [tab, setTab] = useState<Pestana>('trazas')

  return (
    <aside className="flex h-full w-full flex-col border-l border-ink-800 bg-ink-900">
      <header className="flex items-start gap-3 border-b border-ink-800 p-4">
        <div className="min-w-0 flex-1">
          <div className="truncate text-base font-semibold">{fmtFormula(job.formula)}</div>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-400">
            <StatusBadge status={job.status} />
            <span className="font-mono">{job.job_id}</span>
            <span className="tnum">{fmtDuration(job.elapsed_min)}</span>
            {job.mpi_cores && <span className="tnum">{job.mpi_cores} cores MPI</span>}
          </div>
        </div>
        <button onClick={onClose} className="btn px-2 py-1 text-xs" aria-label="Cerrar">
          ✕
        </button>
      </header>

      <Acciones job={job} />

      <nav className="flex gap-1 border-b border-ink-800 px-2">
        {(
          [
            ['trazas', 'Trazas SCF'],
            ['frames', 'Frames'],
            ['log', 'Log'],
            ['ficha', 'Ficha'],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`border-b-2 px-3 py-2 text-xs transition ${
              tab === id
                ? 'border-st-running text-ink-100'
                : 'border-transparent text-ink-400 hover:text-ink-100'
            }`}
          >
            {label}
          </button>
        ))}
      </nav>

      <div className="flex-1 overflow-y-auto p-4">
        {tab === 'trazas' && <Trazas jobId={job.job_id} />}
        {tab === 'frames' && <Frames jobId={job.job_id} />}
        {tab === 'log' && <Log jobId={job.job_id} />}
        {tab === 'ficha' && <Ficha jobId={job.job_id} />}
      </div>
    </aside>
  )
}

function Acciones({ job }: { job: JobStatus }) {
  const qc = useQueryClient()
  const [aviso, setAviso] = useState<string | null>(null)

  const refrescar = () => {
    void qc.invalidateQueries({ queryKey: ['jobs'] })
    void qc.invalidateQueries({ queryKey: ['summary'] })
    void qc.invalidateQueries({ queryKey: ['batches'] })
  }

  const matar = useMutation({
    mutationFn: () => api.killJob(job.job_id),
    onSuccess: (r) => {
      setAviso(
        r.killed_pids.length
          ? `Detenido. Procesos terminados: ${r.killed_pids.join(', ')}.`
          : 'Marcado como detenido; no había procesos vivos.',
      )
      refrescar()
    },
    onError: (e) => setAviso((e as Error).message),
  })

  const reintentar = useMutation({
    mutationFn: () => api.retryJob(job.job_id),
    onSuccess: (r) => {
      setAviso(`De vuelta en la cola (intento ${r.requeue_count}).`)
      refrescar()
    },
    onError: (e) => setAviso((e as Error).message),
  })

  const diagnosticar = useMutation({
    mutationFn: () =>
      api.agentChat({
        message: 'Diagnostica este job y sugiere acciones seguras.',
        job_id: job.job_id,
        structured: true,
      }),
    onSuccess: (r) => {
      const summary = (r.structured as { summary?: unknown } | null | undefined)?.summary
      setAviso(String(summary || r.message || 'Diagnóstico recibido.'))
    },
    onError: (e) => setAviso((e as Error).message),
  })

  const puedeMatar = MATABLES.has(job.status)
  const puedeReintentar = REINTENTABLES.has(job.status)

  return (
    <div className="space-y-2 border-b border-ink-800 px-4 py-2.5">
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => diagnosticar.mutate()}
          className="btn-primary text-xs"
          disabled={diagnosticar.isPending}
        >
          {diagnosticar.isPending ? 'Diagnosticando…' : 'Diagnosticar'}
        </button>
        {puedeMatar && (
          <ConfirmButton
            onConfirm={() => matar.mutate()}
            confirmLabel="Sí, detener"
            pending={matar.isPending}
            className="btn text-xs"
          >
            Detener job
          </ConfirmButton>
        )}
        {puedeReintentar && (
          <ConfirmButton
            onConfirm={() => reintentar.mutate()}
            confirmLabel="Sí, reintentar"
            pending={reintentar.isPending}
            className="btn text-xs"
          >
            Volver a la cola
          </ConfirmButton>
        )}
      </div>
      {aviso && <p className="text-xs text-ink-300">{aviso}</p>}
    </div>
  )
}

function Trazas({ jobId }: { jobId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['job', jobId, 'traces'],
    queryFn: () => api.jobTraces(jobId),
    refetchInterval: 20_000,
  })

  if (isLoading) return <p className="text-sm text-ink-400">Cargando…</p>
  if (!data?.labels.length)
    return <p className="text-sm text-ink-400">Este job no tiene iteraciones SCF registradas.</p>

  return (
    <div className="space-y-6">
      {data.labels.map((lab, i) => {
        const x = lab.points.map((p) => p.iter)
        const energia: Serie[] = [
          {
            label: 'E (eV)',
            values: lab.points.map((p) => p.energy),
            color: COLORES[i % COLORES.length],
          },
        ]
        const residuos: Serie[] = [
          {
            label: 'log₁₀ dens',
            values: lab.points.map((p) => p.dens),
            color: '#f59e0b',
          },
        ]
        const restantes = Math.max(0, 15 - (lab.points.at(-1)?.iter ?? 0))

        return (
          <section key={lab.label} className="space-y-2">
            <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <h3 className="text-sm font-semibold">{lab.label}</h3>
              <span className="tnum text-xs text-ink-400">{lab.n_iters} iteraciones</span>
              {lab.rate_s_per_iter != null && (
                <>
                  <span className="tnum text-xs text-ink-400">
                    {fmtNumber(lab.rate_s_per_iter, 0)} s/iter
                  </span>
                  {restantes > 0 && (
                    <span className="tnum text-xs text-ink-300">
                      ETA ~{fmtEta(lab.rate_s_per_iter * restantes)}
                    </span>
                  )}
                </>
              )}
            </header>

            <LineChart x={x} series={energia} yLabel="Energía (eV)" xLabel="iteración" height={190} />
            {lab.points.some((p) => p.dens != null) && (
              <LineChart
                x={x}
                series={residuos}
                yLabel="log₁₀ densidad"
                xLabel="iteración"
                height={130}
              />
            )}
          </section>
        )
      })}
    </div>
  )
}

function Frames({ jobId }: { jobId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['job', jobId, 'traces'],
    queryFn: () => api.jobTraces(jobId),
  })

  if (isLoading) return <p className="text-sm text-ink-400">Cargando…</p>
  if (!data?.frames.length)
    return (
      <p className="text-sm text-ink-400">
        Sin frames etiquetados. Son los single-points E+F sobre configuraciones perturbadas de la
        Fase 2A.
      </p>
    )

  return (
    <table className="w-full text-sm">
      <thead className="border-b border-ink-800 text-left">
        <tr className="label">
          <th className="py-2 pr-3">Config</th>
          <th className="py-2 pr-3">Estado</th>
          <th className="py-2 pr-3">Energía</th>
          <th className="py-2 pr-3">eV/átomo</th>
          <th className="py-2 pr-3">fmax</th>
          <th className="py-2">Tiempo</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-ink-800">
        {data.frames.map((f) => (
          <tr key={`${f.label}-${f.config_index}`}>
            <td className="tnum py-1.5 pr-3">
              {f.label}/{f.config_index}
            </td>
            <td className="py-1.5 pr-3">
              <span className={f.status === 'ok' ? 'text-green-300' : 'text-red-300'}>
                {f.status ?? '—'}
              </span>
            </td>
            <td className="tnum py-1.5 pr-3">{fmtEnergy(f.energy_ev, 4)}</td>
            <td className="tnum py-1.5 pr-3 text-ink-300">
              {fmtNumber(f.energy_per_atom_ev, 4)}
            </td>
            <td className="tnum py-1.5 pr-3 text-ink-300">{fmtNumber(f.forces_max_eva, 4)}</td>
            <td className="tnum py-1.5 text-ink-400">
              {f.elapsed_s != null ? fmtEta(f.elapsed_s) : '—'}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function Log({ jobId }: { jobId: string }) {
  const [label, setLabel] = useState<string | undefined>()
  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ['job', jobId, 'log', label],
    queryFn: () => api.jobLog(jobId, label, 300),
    refetchInterval: 15_000,
  })

  if (isLoading) return <p className="text-sm text-ink-400">Cargando…</p>
  if (!data?.lines.length) return <p className="text-sm text-ink-400">Este job no tiene log.</p>

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        {data.available.length > 1 &&
          data.available.map((l) => (
            <button
              key={l}
              onClick={() => setLabel(l)}
              className={`rounded px-2 py-1 text-xs ${
                (label ?? data.label) === l
                  ? 'bg-st-running/20 text-blue-200'
                  : 'text-ink-400 hover:text-ink-100'
              }`}
            >
              {l}
            </button>
          ))}
        <span className="tnum ml-auto text-xs text-ink-400">
          últimas {data.lines.length} de {data.total_lines} líneas
        </span>
        <button onClick={() => void refetch()} className="btn px-2 py-1 text-xs">
          {isFetching ? '…' : 'Refrescar'}
        </button>
      </div>

      <pre className="max-h-[60vh] overflow-auto rounded border border-ink-800 bg-ink-950 p-3 text-[11px] leading-relaxed text-ink-300">
        {data.lines.join('\n')}
      </pre>
    </div>
  )
}

function Ficha({ jobId }: { jobId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['job', jobId, 'metadata'],
    queryFn: () => api.jobMetadata(jobId),
  })

  if (isLoading) return <p className="text-sm text-ink-400">Cargando…</p>
  const md = data?.metadata ?? {}
  if (!Object.keys(md).length)
    return <p className="text-sm text-ink-400">Este job no tiene metadata.json.</p>

  const destacados: [string, unknown][] = [
    ['Fórmula', md.formula],
    ['Modo de generación', md.generation_mode],
    ['Átomos', md.n_atoms],
    ['Supercelda', Array.isArray(md.supercell) ? md.supercell.join('×') : md.supercell],
    ['Tolerancia Goldschmidt', md.tolerance_t],
    ['Factor octaédrico', md.oct_factor],
    ['a (Å)', md.lattice_constant_A],
    ['k-points', Array.isArray(md.kpts_supercell) ? md.kpts_supercell.join('×') : undefined],
    ['Política DFT', md.dft_policy],
  ]

  return (
    <div className="space-y-4">
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
        {destacados
          .filter(([, v]) => v !== undefined && v !== null)
          .map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-ink-400">{k}</dt>
              <dd className="tnum">{String(v)}</dd>
            </div>
          ))}
      </dl>

      <details className="text-xs">
        <summary className="cursor-pointer text-ink-400 hover:text-ink-100">
          metadata.json completo
        </summary>
        <pre className="mt-2 max-h-96 overflow-auto rounded border border-ink-800 bg-ink-950 p-3 text-[11px] text-ink-300">
          {JSON.stringify(md, null, 2)}
        </pre>
      </details>

      <details className="text-xs">
        <summary className="cursor-pointer text-ink-400 hover:text-ink-100">
          Artefactos ({data?.artifacts.length ?? 0})
        </summary>
        <ul className="mt-2 space-y-0.5 font-mono text-[11px] text-ink-400">
          {data?.artifacts.map((a) => <li key={a}>{a}</li>)}
        </ul>
      </details>
    </div>
  )
}
