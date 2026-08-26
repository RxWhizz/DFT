import { useQuery } from '@tanstack/react-query'

import { Batches } from '@/components/Batches'
import { Sparkline } from '@/components/Sparkline'
import { StatusBadge } from '@/components/StatusBadge'
import { usePlatform } from '@/lib/usePlatform'
import { api, type JobStatus } from '@/lib/api'
import { fmtDuration, fmtEnergy, fmtFormula, fmtNumber } from '@/lib/format'
import type { JobEvent } from '@/lib/useEvents'

const ACTIVOS = 'running,stalled,oscillating'

export function Live({ events }: { events: JobEvent[] }) {
  const plataforma = usePlatform()
  const summary = useQuery({ queryKey: ['summary'], queryFn: api.summary, refetchInterval: 10_000 })
  const system = useQuery({ queryKey: ['system'], queryFn: api.system, refetchInterval: 5_000 })
  const history = useQuery({
    queryKey: ['system', 'history'],
    queryFn: () => api.systemHistory(10),
    refetchInterval: 15_000,
  })
  const activos = useQuery({
    queryKey: ['jobs', { status: ACTIVOS }],
    queryFn: () => api.jobs({ status: ACTIVOS, limit: 50, sort: 'elapsed_min', desc: true }),
    refetchInterval: 10_000,
  })

  const s = summary.data
  const m = system.data
  const muestras = history.data?.samples ?? []

  return (
    <div className="space-y-4">
      {/* ── Recuento por estado ──────────────────────────────────────────── */}
      <section className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label="Corriendo" value={s?.n_running} tone="text-blue-300" />
        <Stat label="Convergidos" value={s?.n_converged} tone="text-green-300" />
        <Stat label="Fallidos" value={s?.n_failed} tone="text-red-300" />
        <Stat label="En cola" value={s?.n_pending} tone="text-slate-300" />
        <Stat label="Duplicados" value={s?.n_skipped_duplicate} tone="text-violet-300" />
        <Stat
          label="Tasa converg."
          value={s?.convergence_rate != null ? `${(s.convergence_rate * 100).toFixed(1)}%` : '—'}
          tone="text-ink-100"
        />
      </section>

      {/* ── Hardware ─────────────────────────────────────────────────────── */}
      <section className="card-pad">
        <h2 className="label mb-3">Hardware</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Metric
            label="CPU"
            value={m ? `${m.cpu_percent.toFixed(0)}%` : '—'}
            spark={muestras.map((x) => x.cpu_percent)}
            max={100}
            tone="text-st-running"
          />
          <Metric
            label="RAM"
            value={m ? `${m.ram_used_gb.toFixed(1)} / ${m.ram_total_gb.toFixed(0)} GB` : '—'}
            sub={m ? `${(m.ram_total_gb - m.ram_used_gb).toFixed(0)} GB libres` : undefined}
            spark={muestras.map((x) => x.ram_percent)}
            max={100}
            tone="text-st-converged"
          />
          {plataforma.hardware_temps && (
            <Metric
              label="Temp. núcleo"
              value={m ? `${fmtNumber(m.core_temp_max, 0)} °C` : '—'}
              sub={m?.nvme_temp != null ? `NVMe ${fmtNumber(m.nvme_temp, 0)} °C` : undefined}
              spark={muestras.map((x) => x.core_temp_max)}
              max={100}
              tone="text-st-stalled"
            />
          )}
          {plataforma.hardware_temps && (
            <Metric
              label="GPU"
              value={m?.gpu_temps.length ? `${fmtNumber(Math.max(...m.gpu_temps), 0)} °C` : 'n/d'}
              spark={muestras.map((x) => x.gpu_temp_max ?? 0)}
              max={100}
              tone="text-st-oscillating"
            />
          )}
        </div>

        {m && m.cpu_per_core.length > 0 && (
          <div className="mt-4">
            <div className="label mb-1.5">Núcleos ({m.cpu_per_core.length})</div>
            <div className="flex flex-wrap gap-1">
              {m.cpu_per_core.map((pct, i) => (
                <div
                  key={i}
                  title={`core ${i}: ${pct.toFixed(0)}%`}
                  className="h-5 w-5 rounded-sm border border-ink-800"
                  style={{
                    background: `color-mix(in oklab, #3b82f6 ${pct.toFixed(0)}%, #141b24)`,
                  }}
                />
              ))}
            </div>
          </div>
        )}
      </section>

      <Batches />

      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        {/* ── Jobs activos ───────────────────────────────────────────────── */}
        <section className="card-pad">
          <h2 className="label mb-3">Jobs activos ({activos.data?.total ?? 0})</h2>
          {activos.isLoading ? (
            <p className="text-sm text-ink-400">Cargando…</p>
          ) : !activos.data?.items.length ? (
            <p className="text-sm text-ink-400">
              Ningún job activo. {s ? `${s.n_pending} en cola.` : ''}
            </p>
          ) : (
            <ul className="divide-y divide-ink-800">
              {activos.data.items.map((j) => (
                <JobRow key={j.job_id} job={j} />
              ))}
            </ul>
          )}
        </section>

        {/* ── Eventos en vivo ────────────────────────────────────────────── */}
        <section className="card-pad">
          <h2 className="label mb-3">Eventos</h2>
          {!events.length ? (
            <p className="text-sm text-ink-400">
              Sin eventos desde que se abrió la sesión. Aparecerán aquí en cuanto un job cambie de
              estado.
            </p>
          ) : (
            <ul className="max-h-96 space-y-1.5 overflow-y-auto text-xs">
              {events.map((e) => (
                <li key={`${e.seq}`} className="flex items-baseline gap-2">
                  <span className="tnum shrink-0 text-ink-400">
                    {e.timestamp.slice(11, 19)}
                  </span>
                  <span className="shrink-0 font-medium text-ink-300">{e.event}</span>
                  <span className="truncate text-ink-100">
                    {fmtFormula(String(e.data?.formula ?? e.job_id.slice(0, 8)))}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  )
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string
  value: number | string | undefined
  tone: string
}) {
  return (
    <div className="card-pad">
      <div className="label">{label}</div>
      <div className={`tnum mt-1 text-2xl font-semibold ${tone}`}>{value ?? '—'}</div>
    </div>
  )
}

function Metric({
  label,
  value,
  sub,
  spark,
  max,
  tone,
}: {
  label: string
  value: string
  sub?: string
  spark: number[]
  max?: number
  tone: string
}) {
  return (
    <div>
      <div className="label">{label}</div>
      <div className="tnum mt-0.5 text-lg font-semibold">{value}</div>
      {sub && <div className="tnum text-xs text-ink-400">{sub}</div>}
      <div className="mt-1.5">
        <Sparkline values={spark} max={max} className={tone} width={140} height={28} />
      </div>
    </div>
  )
}

function JobRow({ job }: { job: JobStatus }) {
  const { data } = useQuery({
    queryKey: ['job', job.job_id],
    queryFn: () => api.job(job.job_id),
    refetchInterval: 15_000,
  })

  const pasos = data?.n_fire_steps
    ? `FIRE ${data.n_fire_steps}`
    : data?.n_scf_iters
      ? `SCF ${data.n_scf_iters}`
      : 'inicializando'
  const energia = data?.energy_history?.at(-1)
  const fmax = data?.fmax_history?.at(-1)

  return (
    <li className="flex items-center gap-3 py-2 text-sm">
      <StatusBadge status={job.status} compact />
      <span className="w-52 shrink-0 truncate font-medium">{fmtFormula(job.formula)}</span>
      <span className="tnum w-24 shrink-0 text-xs text-ink-400">{pasos}</span>
      <span className="tnum w-28 shrink-0 text-xs text-ink-300">{fmtEnergy(energia, 3)}</span>
      <span className="tnum w-24 shrink-0 text-xs text-ink-400">
        {fmax != null ? `fmax ${fmax.toFixed(3)}` : ''}
      </span>
      <span className="tnum ml-auto shrink-0 text-xs text-ink-400">
        {fmtDuration(job.elapsed_min)}
      </span>
      {data?.stall_minutes != null && (
        <span className="tnum shrink-0 text-xs text-amber-300">
          parado {data.stall_minutes.toFixed(0)}min
        </span>
      )}
    </li>
  )
}
