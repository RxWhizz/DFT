import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { ConfirmButton } from '@/components/ConfirmButton'
import {
  api,
  type FunnelTier,
  type ScreeningStartDftResult,
} from '@/lib/api'
import { fmtEta, fmtFormula, fmtNumber } from '@/lib/format'

/** Cuánto tarda cada tier en refrescar mientras la cascada corre. */
const POLL_MS = 2000

export function Screening() {
  const qc = useQueryClient()
  const [runId, setRunId] = useState<string | null>(null)
  const [randomSeed, setRandomSeed] = useState(() => Math.floor(Date.now() % 1_000_000))
  const [nBatches, setNBatches] = useState(1)
  const [nCandidates, setNCandidates] = useState(200)

  const config = useQuery({ queryKey: ['screening', 'config'], queryFn: api.screeningConfig })
  const historial = useQuery({
    queryKey: ['screening', 'runs'],
    queryFn: api.screeningRuns,
    refetchInterval: POLL_MS,
  })

  const activo = runId ?? historial.data?.items[0]?.run_id ?? null
  const run = useQuery({
    queryKey: ['screening', 'run', activo],
    queryFn: () => api.screeningRunDetail(activo!),
    enabled: Boolean(activo),
    placeholderData: keepPreviousData,
    // Solo se sondea mientras hay algo en marcha.
    refetchInterval: (q) => {
      const s = q.state.data?.status
      return s === 'running' || s === 'pending' ? POLL_MS : false
    },
  })

  const lotesValidos = Math.max(1, nBatches)
  const maxCandidatesPerLot = Math.max(1, Math.floor(5000 / lotesValidos))

  const lanzar = useMutation({
    mutationFn: () =>
      api.screeningRun({
        random_seed: randomSeed,
        n_batches: lotesValidos,
        n_candidates: Math.min(nCandidates, maxCandidatesPerLot),
      }),
    onSuccess: (r) => {
      setRunId(r.run_id)
      void qc.invalidateQueries({ queryKey: ['screening', 'runs'] })
    },
  })

  const d = run.data
  const empezarDft = useMutation({
    mutationFn: () => api.screeningStartDft(d!.run_id, { start_runner: true }),
    onSuccess: (r) => {
      void qc.invalidateQueries({ queryKey: ['screening', 'run', r.run_id] })
      void qc.invalidateQueries({ queryKey: ['screening', 'runs'] })
      void qc.invalidateQueries({ queryKey: ['batches'] })
      void qc.invalidateQueries({ queryKey: ['jobs'] })
      void qc.invalidateQueries({ queryKey: ['summary'] })
      void qc.invalidateQueries({ queryKey: ['structures'] })
    },
  })

  const mlffOff = config.data?.tiers.find((t) => t.tier === 2 && !t.available)
  const puedeEmpezarDft = d?.status === 'done' && d.n_selected > 0
  const dftResult = empezarDft.data?.run_id === d?.run_id ? empezarDft.data : null

  return (
    <div className="flex min-h-[calc(100vh-6.5rem)] flex-col gap-4">
      {config.data && !config.data.available && (
        <div className="rounded-md border border-st-failed/40 bg-st-failed/10 px-4 py-3 text-sm">
          <span className="font-semibold text-red-300">Cribado no disponible.</span>{' '}
          <span className="text-ink-300">{config.data.reason}</span>
        </div>
      )}

      {mlffOff && (
        <div className="rounded-md border border-st-stalled/40 bg-st-stalled/10 px-4 py-3 text-sm">
          <span className="font-semibold text-amber-300">Tier 2 (MLFF) no disponible.</span>{' '}
          <span className="text-ink-300">{mlffOff.reason}</span>
        </div>
      )}

      {/* ── Controles ──────────────────────────────────────────────────── */}
      <section className="card-pad flex flex-wrap items-end gap-4">
        <label className="flex flex-col gap-1">
          <span className="label">Semilla</span>
          <input
            type="number"
            className="input w-32 tnum"
            value={randomSeed}
            min={0}
            max={999999999}
            onChange={(e) => setRandomSeed(Number(e.target.value))}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="label">Lotes</span>
          <input
            type="number"
            className="input w-24 tnum"
            value={nBatches}
            min={1}
            max={50}
            onChange={(e) => {
              const next = Math.max(1, Number(e.target.value))
              setNBatches(next)
              setNCandidates((current) => Math.min(current, Math.max(1, Math.floor(5000 / next))))
            }}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="label">Candidatos/lote</span>
          <input
            type="number"
            className="input w-28 tnum"
            value={nCandidates}
            min={1}
            max={maxCandidatesPerLot}
            onChange={(e) => setNCandidates(Number(e.target.value))}
          />
        </label>

        <div className="ml-auto flex items-center gap-3">
          {d?.status === 'running' && (
            <span className="flex items-center gap-2 text-xs text-blue-200">
              <span className="h-3 w-3 rounded-full border-2 border-st-running border-r-transparent" />
              {d.stage}
            </span>
          )}
          <button
            onClick={() => lanzar.mutate()}
            disabled={lanzar.isPending || d?.status === 'running'}
            className="btn-primary"
          >
            {lanzar.isPending ? '…' : 'Ejecutar'}
          </button>
          {puedeEmpezarDft && (
            <ConfirmButton
              onConfirm={() => empezarDft.mutate()}
              confirmLabel="Sí, preparar y lanzar"
              pending={empezarDft.isPending}
              className="btn"
            >
              Empezar DFT
            </ConfirmButton>
          )}
        </div>
      </section>

      {lanzar.error && (
        <p className="rounded border border-st-failed/40 bg-st-failed/10 px-3 py-2 text-xs text-red-300">
          {(lanzar.error as Error).message}
        </p>
      )}

      {empezarDft.error && (
        <p className="rounded border border-st-failed/40 bg-st-failed/10 px-3 py-2 text-xs text-red-300">
          {(empezarDft.error as Error).message}
        </p>
      )}

      {dftResult ? <DftStartNotice result={dftResult} /> : d?.dft_batch_path ? (
        <p className="rounded border border-st-converged/30 bg-st-converged/[0.07] px-3 py-2 text-xs text-green-300">
          DFT preparado en <code className="font-mono">{d.dft_batch_path}</code>
          {d.dft_prepared != null && (
            <>
              {' '}
              · <span className="tnum">{d.dft_prepared}</span> estructuras nuevas
            </>
          )}
        </p>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_396px]">
        {/* ── Embudo ───────────────────────────────────────────────────── */}
        <section className="card-pad space-y-3">
          <header className="flex flex-wrap items-baseline gap-3">
            <h2 className="label">Cascada</h2>
            {d && (
              <span className="tnum text-xs text-ink-400">
                {d.n_requested} pedidos · {d.n_batches} lotes · semilla {d.random_seed} ·{' '}
                {fmtEta(d.elapsed_sec)}
                {d.status === 'error' && ' · falló'}
              </span>
            )}
          </header>

          {d?.error && (
            <p className="rounded border border-st-failed/40 bg-st-failed/10 px-3 py-2 text-xs text-red-300">
              {d.error}
            </p>
          )}

          {!d?.tiers.length ? (
            <p className="py-8 text-center text-sm text-ink-400">
              {d?.status === 'running' ? 'Ejecutando…' : 'Aún no has ejecutado la cascada.'}
            </p>
          ) : (
            <ul className="space-y-2">
              {d.tiers.map((t) => (
                <TierRow key={t.tier} t={t} total={d.tiers[0]?.n_in || 1} />
              ))}
            </ul>
          )}
        </section>

        {/* ── Cotas ────────────────────────────────────────────────────── */}
        <aside className="space-y-4">
          {config.data?.gates && <Cotas gates={config.data.gates} />}
        </aside>
      </div>

      {/* ── Ranking ────────────────────────────────────────────────────── */}
      {d?.items?.length ? (
        <section className="card flex min-h-[20rem] flex-1 flex-col overflow-hidden">
          <div className="flex items-center gap-3 border-b border-ink-800 bg-ink-850 px-3 py-2">
            <span className="label">Ranking por total_score</span>
            <span className="tnum ml-auto text-xs text-ink-400">
              {d.items.length} de {d.n_items_total} · {d.n_selected} irían a DFT
            </span>
          </div>
          <div className="min-h-0 flex-1 overflow-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-ink-850 text-left">
                <tr className="label">
                  <th className="px-3 py-2">Fórmula</th>
                  <th className="px-3 py-2">Eg (eV)</th>
                  <th className="px-3 py-2">σ</th>
                  <th className="px-3 py-2">PV</th>
                  <th className="px-3 py-2">E_form</th>
                  <th className="px-3 py-2">band</th>
                  <th className="px-3 py-2">stab</th>
                  <th className="px-3 py-2">ucb</th>
                  <th className="px-3 py-2">total</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-800">
                {d.items.map((r, i) => (
                  <tr key={r.candidate_id ?? i} className="hover:bg-ink-850/60">
                    <td className="px-3 py-1.5 font-medium">{fmtFormula(r.formula)}</td>
                    <td className="tnum px-3 py-1.5">{fmtNumber(r.Eg_surrogate_eV, 3)}</td>
                    <td className="tnum px-3 py-1.5 text-ink-400">
                      {fmtNumber(r.Eg_sigma_eV, 3)}
                    </td>
                    <td className="px-3 py-1.5 text-xs">
                      {r.in_pv_window == null ? '—' : r.in_pv_window ? (
                        <span className="text-green-300">✓</span>
                      ) : (
                        <span className="text-ink-400">·</span>
                      )}
                    </td>
                    <td className="tnum px-3 py-1.5 text-ink-300">
                      {fmtNumber(r.Eform_eV_atom, 3)}
                    </td>
                    <td className="tnum px-3 py-1.5 text-ink-400">{fmtNumber(r.band_score, 2)}</td>
                    <td className="tnum px-3 py-1.5 text-ink-400">{fmtNumber(r.stab_score, 2)}</td>
                    <td className="tnum px-3 py-1.5 text-violet-300">
                      {fmtNumber(r.ucb_bonus, 2)}
                    </td>
                    <td className="tnum px-3 py-1.5 font-medium">
                      {fmtNumber(r.total_score, 3)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
    </div>
  )
}

const ESTILO_TIER: Record<FunnelTier['kind'], { barra: string; etiqueta: string; texto: string }> = {
  gate: { barra: 'bg-st-pending', etiqueta: 'descarta', texto: 'text-ink-300' },
  signal: { barra: 'bg-st-skipped', etiqueta: 'puntúa', texto: 'text-violet-300' },
  select: { barra: 'bg-st-running', etiqueta: 'corta', texto: 'text-blue-200' },
}

function TierRow({ t, total }: { t: FunnelTier; total: number }) {
  const s = ESTILO_TIER[t.kind]
  const ancho = total > 0 ? Math.max(4, (t.n_in / total) * 100) : 0
  const anchoSalida = total > 0 ? Math.max(2, (t.n_out / total) * 100) : 0

  return (
    <li className="grid grid-cols-[104px_minmax(0,1fr)_92px] items-center gap-3">
      <div className="flex flex-col gap-0.5">
        <span className="tnum text-[11px] text-ink-400">TIER {t.tier}</span>
        <span className={`text-[13px] font-medium ${s.texto}`}>{t.name}</span>
        <span className="text-[10px] uppercase tracking-wider text-ink-400">{s.etiqueta}</span>
      </div>

      <div className="flex flex-col gap-1.5">
        <div className="relative h-9 overflow-hidden rounded-md bg-ink-950">
          <span className={`absolute inset-y-0 left-0 ${s.barra} opacity-30`} style={{ width: `${ancho}%` }} />
          {/* El tramo sólido es lo que sobrevive; el traslúcido, lo que entró. */}
          <span className={`absolute inset-y-0 left-0 ${s.barra}`} style={{ width: `${anchoSalida}%` }} />
          <span className="tnum absolute inset-y-0 left-3 flex items-center text-xs text-ink-100">
            {t.n_in} entran
          </span>
          {t.n_dropped > 0 && (
            <span className="tnum absolute inset-y-0 right-3 flex items-center text-xs text-red-300">
              −{t.n_dropped}
            </span>
          )}
        </div>
      </div>

      <div className="flex flex-col items-end">
        <span className="tnum text-lg font-semibold">{t.ran ? t.n_out : '—'}</span>
        <span className="text-[11px] text-ink-400">
          {t.kind === 'signal' ? 'marcados' : 'siguen'}
        </span>
      </div>
    </li>
  )
}

function DftStartNotice({ result }: { result: ScreeningStartDftResult }) {
  const hayErrorRunner = Boolean(result.runner_error)

  return (
    <p
      className={`rounded border px-3 py-2 text-xs ${
        hayErrorRunner
          ? 'border-st-stalled/40 bg-st-stalled/10 text-amber-300'
          : 'border-st-converged/30 bg-st-converged/[0.07] text-green-300'
      }`}
    >
      DFT preparado en <code className="font-mono">{result.batch_path}</code> ·{' '}
      <span className="tnum">{result.n_prepared}</span> nuevos ·{' '}
      <span className="tnum">{result.n_existing_or_skipped}</span> existentes
      {result.runner_launched ? (
        <>
          {' '}
          · runner <span className="font-mono">{result.runner_kind}</span> lanzado
        </>
      ) : result.runner_error ? (
        <>
          {' '}
          · {result.runner_error}
        </>
      ) : null}
    </p>
  )
}

function Cotas({ gates }: { gates: NonNullable<import('@/lib/api').ScreeningConfig['gates']> }) {
  const filas: [string, string][] = [
    ['Goldschmidt t', `${gates.goldschmidt.min} – ${gates.goldschmidt.max}`],
    ['Factor octaédrico', `${gates.octahedral.min} – ${gates.octahedral.max}`],
    ['Volumen (Å³)', `${gates.volume_A3.min} – ${gates.volume_A3.max}`],
    ['Ventana PV (eV)', `${gates.pv_window[0]} – ${gates.pv_window[1]}`],
    ['E_form máx.', `${gates.eform_max_eV_atom} eV/át`],
    ['β (exploración)', String(gates.beta)],
  ]

  return (
    <section className="card-pad space-y-2.5">
      <h2 className="label">Cotas</h2>
      <dl className="space-y-1 text-xs">
        {filas.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-2">
            <dt className="text-ink-400">{k}</dt>
            <dd className="tnum">{v}</dd>
          </div>
        ))}
      </dl>
      <div className="space-y-1 border-t border-ink-800 pt-2.5 text-xs">
        {(['A', 'B', 'X'] as const).map((sitio) => (
          <div key={sitio} className="flex gap-2">
            <span className="tnum w-4 text-ink-400">{sitio}</span>
            <span className="tnum text-ink-300">{gates.chemical_space[sitio].join(' · ')}</span>
          </div>
        ))}
      </div>
    </section>
  )
}
