import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import { api, type DiscoveryCandidate, type DiscoveryStatus } from '@/lib/api'
import { fmtFormula, fmtNumber } from '@/lib/format'

const POLL_MS = 4000

const STATUS: Record<string, { label: string; cls: string }> = {
  not_initialized: { label: 'sin iniciar', cls: 'text-ink-400' },
  idle: { label: 'listo', cls: 'text-green-300' },
  screening: { label: 'cribando', cls: 'text-blue-200' },
  dft_prepared: { label: 'DFT preparado', cls: 'text-amber-300' },
  dft_running: { label: 'DFT corriendo', cls: 'text-blue-200' },
  paused: { label: 'pausado', cls: 'text-amber-300' },
  done: { label: 'terminado', cls: 'text-green-300' },
  error: { label: 'error', cls: 'text-red-300' },
}

export function Discovery() {
  const qc = useQueryClient()
  const status = useQuery({
    queryKey: ['discovery', 'status'],
    queryFn: api.discoveryStatus,
    placeholderData: keepPreviousData,
    refetchInterval: (q) => {
      const data = q.state.data
      const s = data?.state.status
      return data?.background?.running || s === 'screening' || s === 'dft_running' ? POLL_MS : false
    },
  })

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ['discovery'] })
    void qc.invalidateQueries({ queryKey: ['jobs'] })
    void qc.invalidateQueries({ queryKey: ['batches'] })
    void qc.invalidateQueries({ queryKey: ['summary'] })
  }

  const init = useMutation({
    mutationFn: () => api.discoveryInit({ reset: false }),
    onSuccess: invalidate,
  })
  const run = useMutation({
    mutationFn: () => api.discoveryRun({ start_runner: true, dry_run: false }),
    onSuccess: invalidate,
  })
  const pause = useMutation({ mutationFn: api.discoveryPause, onSuccess: invalidate })
  const resume = useMutation({ mutationFn: api.discoveryResume, onSuccess: invalidate })
  const exportRun = useMutation({ mutationFn: api.discoveryExport, onSuccess: invalidate })

  const data = status.data
  const state = data?.state.status ?? 'not_initialized'
  const style = STATUS[state] ?? { label: state, cls: 'text-ink-300' }
  const running = Boolean(data?.background?.running)
  const canInit = state === 'not_initialized' || state === 'error'
  // `screening` no bloquea: sólo ocurre DENTRO del hilo de fondo, así que verlo
  // con `running` en false significa que ese hilo murió y el estado quedó
  // obsoleto — exactamente lo que pasaba cuando la ronda reventaba por falta de
  // torch. Bloquearlo dejaba el protocolo sin forma de rearrancar desde la GUI.
  // `dft_running` sí sigue bloqueando: esos son procesos externos, no el hilo.
  const canRun = !running && !['dft_running', 'done'].includes(state)
  const canPause = state !== 'paused' && !['not_initialized', 'done'].includes(state)
  const canResume = state === 'paused'

  return (
    <div className="flex min-h-[calc(100vh-6.5rem)] flex-col gap-4">
      <section className="card-pad flex flex-wrap items-center gap-4">
        <div className="min-w-48">
          <span className="label">Protocolo de Descubrimiento Autónomo</span>
          <div className={`mt-1 text-lg font-semibold ${style.cls}`}>
            {style.label}
            {running && <span className="ml-2 text-xs font-normal text-ink-400">en segundo plano</span>}
          </div>
        </div>

        <Metric label="Ronda" value={data?.state.current_round ?? 0} />
        <Metric
          label="Cobertura"
          value={`${data?.coverage.seen ?? 0}/${data?.coverage.total ?? 0}`}
          detail={`${fmtNumber(data?.coverage.percent, 2)}%`}
        />
        <Metric label="Frontera" value={data?.frontier.length ?? 0} />
        <Metric label="Cola DFT" value={data?.queue.length ?? 0} />

        <div className="ml-auto flex flex-wrap items-center gap-2">
          <button className="btn" onClick={() => init.mutate()} disabled={!canInit || init.isPending}>
            Inicializar
          </button>
          <button className="btn-primary" onClick={() => run.mutate()} disabled={!canRun || run.isPending}>
            Ejecutar protocolo
          </button>
          {canPause && (
            <button className="btn" onClick={() => pause.mutate()} disabled={pause.isPending}>
              Pausar
            </button>
          )}
          {canResume && (
            <button className="btn-primary" onClick={() => resume.mutate()} disabled={resume.isPending}>
              Reanudar
            </button>
          )}
          <button className="btn" onClick={() => exportRun.mutate()} disabled={exportRun.isPending}>
            Exportar reporte
          </button>
        </div>
      </section>

      <Errors status={status.error} mutations={[init.error, run.error, pause.error, resume.error, exportRun.error]} />
      {data?.background?.last_error && (
        <p className="rounded border border-st-failed/40 bg-st-failed/10 px-3 py-2 text-xs text-red-300">
          {data.background.last_error}
        </p>
      )}
      {data?.state.stop_reason && (
        <p className="rounded border border-st-converged/30 bg-st-converged/[0.07] px-3 py-2 text-xs text-green-300">
          {data.state.stop_reason}
        </p>
      )}
      {/* Ámbar, no rojo: la ronda SÍ avanzó, sólo que con menos criba. Pintarlo
          como error haría que se ignorase un protocolo que funciona; callarlo
          dejaría al usuario creyendo que hubo estabilidad MLFF. */}
      {data?.state.mlff_warning && (
        <div className="rounded border border-amber-600/40 bg-amber-500/[0.08] px-3 py-2 text-xs text-amber-200">
          <p className="font-medium">Cribado sin Tier 2 (MLFF/GNN)</p>
          <p className="mt-1">{data.state.mlff_warning.error}</p>
          <p className="mt-1 text-amber-300/80">
            {data.state.mlff_warning.remediation ||
              'La ronda avanzó con Tier 0/1: se descartó menos material del que se ' +
                'habría descartado con estabilidad MLFF.'}
          </p>
          <Link to="/entorno" className="mt-2 inline-block underline">
            Configurar entorno
          </Link>
        </div>
      )}
      {exportRun.data && (
        <p className="rounded border border-st-running/30 bg-st-running/[0.08] px-3 py-2 text-xs text-blue-200">
          Reporte: <code>{exportRun.data.report}</code>
        </p>
      )}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <section className="card flex min-h-[26rem] flex-col overflow-hidden">
          <header className="flex items-center gap-3 border-b border-ink-800 bg-ink-850 px-3 py-2">
            <span className="label">Frontera Pareto del protocolo</span>
            <span className="tnum ml-auto text-xs text-ink-400">{data?.frontier.length ?? 0} candidatos</span>
          </header>
          <CandidateTable items={data?.frontier ?? []} />
        </section>

        <aside className="space-y-4">
          <StatePanel data={data} />
          <section className="card overflow-hidden">
            <header className="border-b border-ink-800 bg-ink-850 px-3 py-2">
              <span className="label">Cola DFT</span>
            </header>
            <CandidateList items={data?.queue ?? []} />
          </section>
        </aside>
      </div>
    </div>
  )
}

function Metric({ label, value, detail }: { label: string; value: string | number; detail?: string }) {
  return (
    <div className="min-w-24">
      <span className="label">{label}</span>
      <div className="tnum mt-1 text-base font-semibold">
        {value}
        {detail && <span className="ml-2 text-xs font-normal text-ink-400">{detail}</span>}
      </div>
    </div>
  )
}

function Errors({ status, mutations }: { status: unknown; mutations: unknown[] }) {
  const err = status || mutations.find(Boolean)
  if (!err) return null
  return (
    <p className="rounded border border-st-failed/40 bg-st-failed/10 px-3 py-2 text-xs text-red-300">
      {(err as Error).message}
    </p>
  )
}

function StatePanel({ data }: { data?: DiscoveryStatus }) {
  const last = data?.state.last_screening ?? {}
  const rows: [string, unknown][] = [
    ['Generados viables', data?.state.space?.physically_viable ?? data?.coverage.total],
    ['Rankeados', last.n_ranked],
    ['MLFF', last.n_mlff],
    ['Elegibles', last.n_eligible],
    ['Ledger', data?.paths.ledger],
    ['DFT', data?.paths.dft_runs_dir],
  ]

  return (
    <section className="card-pad space-y-2.5">
      <h2 className="label">Estado</h2>
      <dl className="space-y-1 text-xs">
        {rows.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-3">
            <dt className="text-ink-400">{k}</dt>
            <dd className="max-w-48 truncate text-right tnum" title={String(v ?? '—')}>
              {String(v ?? '—')}
            </dd>
          </div>
        ))}
      </dl>
      <div className="border-t border-ink-800 pt-2 text-xs text-ink-400">
        {Object.entries(data?.counts ?? {}).map(([k, v]) => (
          <span key={k} className="mr-3 inline-block">
            {k}: <span className="tnum text-ink-200">{v}</span>
          </span>
        ))}
      </div>
    </section>
  )
}

function CandidateTable({ items }: { items: DiscoveryCandidate[] }) {
  if (!items.length) {
    return <p className="py-12 text-center text-sm text-ink-400">Sin frontera calculada.</p>
  }
  return (
    <div className="min-h-0 flex-1 overflow-auto">
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-ink-850 text-left">
          <tr className="label">
            <th className="px-3 py-2">Fórmula</th>
            <th className="px-3 py-2">Familia</th>
            <th className="px-3 py-2">Eg</th>
            <th className="px-3 py-2">σ</th>
            <th className="px-3 py-2">Eform</th>
            <th className="px-3 py-2">mₑ</th>
            <th className="px-3 py-2">mₕ</th>
            <th className="px-3 py-2">ε∞</th>
            <th className="px-3 py-2">PV</th>
            <th className="px-3 py-2">adq</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-ink-800">
          {items.map((r, i) => (
            <tr key={r.candidate_id ?? i} className="hover:bg-ink-850/60">
              <td className="px-3 py-1.5 font-medium">{fmtFormula(r.formula)}</td>
              <td className="px-3 py-1.5 text-xs text-ink-400">
                {r.B_family ?? '—'} · {r.dominant_halide ?? '—'}
              </td>
              <td className="tnum px-3 py-1.5">{fmtNumber(r.Eg_surrogate_eV, 3)}</td>
              <td className="tnum px-3 py-1.5 text-ink-400">{fmtNumber(r.Eg_sigma_eV, 3)}</td>
              <td className="tnum px-3 py-1.5">{fmtNumber(r.Eform_eV_atom, 3)}</td>
              <td className="tnum px-3 py-1.5 text-ink-300">{fmtNumber(r.meff_e_pred_m0, 2)}</td>
              <td className="tnum px-3 py-1.5 text-ink-300">{fmtNumber(r.meff_h_pred_m0, 2)}</td>
              <td className="tnum px-3 py-1.5 text-ink-300">{fmtNumber(r.eps_inf_pred, 2)}</td>
              <td className="tnum px-3 py-1.5 text-green-300">{fmtNumber(r.pv_score_ml, 3)}</td>
              <td className="tnum px-3 py-1.5 font-medium">{fmtNumber(r.acquisition_score, 3)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function CandidateList({ items }: { items: DiscoveryCandidate[] }) {
  if (!items.length) return <p className="p-4 text-sm text-ink-400">Sin ronda DFT activa.</p>
  return (
    <ol className="divide-y divide-ink-800 text-sm">
      {items.map((item, i) => (
        <li key={item.candidate_id ?? i} className="px-3 py-2">
          <div className="flex items-center justify-between gap-3">
            <span className="font-medium">{fmtFormula(item.formula)}</span>
            <span className="tnum text-xs text-ink-400">{fmtNumber(item.acquisition_score, 3)}</span>
          </div>
          <div className="mt-0.5 text-xs text-ink-400">
            {item.B_family ?? '—'} · {item.dominant_halide ?? '—'} · {item.status ?? 'seleccionado'}
          </div>
        </li>
      ))}
    </ol>
  )
}
