import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { api, type Prediction, type Top8Row } from '@/lib/api'
import { fmtFormula, fmtNumber } from '@/lib/format'

// Espacio químico de config/generator.yaml.
const SITIOS_A = ['Cs', 'MA', 'FA', 'Rb', 'K']
const SITIOS_B = ['Pb', 'Sn', 'Ge']
const SITIOS_X = ['I', 'Br', 'Cl']

export function Ml() {
  const [A, setA] = useState('Cs')
  const [B, setB] = useState('Pb')
  const [X, setX] = useState('I')

  const modelos = useQuery({ queryKey: ['models'], queryFn: api.models })
  const top8 = useQuery({ queryKey: ['top8'], queryFn: api.top8, staleTime: 300_000 })
  const pred = useMutation({ mutationFn: api.predict })

  const indisponible = modelos.data?.surrogate_status === 'error'

  return (
    <div className="space-y-4">
      {indisponible && (
        <div className="rounded-md border border-st-stalled/40 bg-st-stalled/10 px-4 py-3 text-sm">
          <span className="font-semibold text-amber-300">Surrogate no disponible.</span>{' '}
          <span className="text-ink-300">{modelos.data?.surrogate_error}</span>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[22rem_1fr]">
        {/* ── Predicción puntual ──────────────────────────────────────────── */}
        <section className="card-pad space-y-4">
          <h2 className="label">Predicción</h2>

          <div className="grid grid-cols-3 gap-2">
            <Sitio label="A" value={A} onChange={setA} options={SITIOS_A} />
            <Sitio label="B" value={B} onChange={setB} options={SITIOS_B} />
            <Sitio label="X" value={X} onChange={setX} options={SITIOS_X} />
          </div>

          <div className="text-center text-lg font-semibold">{fmtFormula(`${A}${B}${X}3`)}</div>

          <button
            className="btn-primary w-full"
            disabled={pred.isPending || indisponible}
            onClick={() => pred.mutate({ A, B, X })}
          >
            {pred.isPending ? 'Calculando…' : 'Predecir bandgap'}
          </button>

          {pred.error && (
            <p className="rounded border border-st-failed/40 bg-st-failed/10 px-3 py-2 text-xs text-red-300">
              {(pred.error as Error).message}
            </p>
          )}

          {pred.data && <Resultado p={pred.data} />}
        </section>

        {/* ── Parity plot ─────────────────────────────────────────────────── */}
        <section className="card-pad">
          <div className="mb-2 flex items-baseline justify-between">
            <h2 className="label">ML frente a referencia — top 8</h2>
            <span className="text-xs text-ink-400">
              la diagonal es el acuerdo perfecto
            </span>
          </div>
          <Parity filas={top8.data?.items ?? []} />
        </section>
      </div>

      <section className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="border-b border-ink-800 bg-ink-850 text-left">
            <tr className="label">
              <th className="px-3 py-2">Material</th>
              <th className="px-3 py-2">ML (eV)</th>
              <th className="px-3 py-2">σ</th>
              <th className="px-3 py-2">DFT (eV)</th>
              <th className="px-3 py-2">Exp. (eV)</th>
              <th className="px-3 py-2">|ML − exp|</th>
              <th className="px-3 py-2">Ventana PV</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ink-800">
            {(top8.data?.items ?? []).map((r) => {
              const err =
                r.Eg_ml_eV != null && r.Eg_exp_eV != null
                  ? Math.abs(r.Eg_ml_eV - r.Eg_exp_eV)
                  : null
              return (
                <tr key={r.material} className="hover:bg-ink-850/60">
                  <td className="px-3 py-1.5 font-medium">{fmtFormula(r.material)}</td>
                  <td className="tnum px-3 py-1.5">{fmtNumber(r.Eg_ml_eV, 3)}</td>
                  <td className="tnum px-3 py-1.5 text-ink-400">{fmtNumber(r.Eg_ml_std_eV, 3)}</td>
                  <td className="tnum px-3 py-1.5 text-ink-300">{fmtNumber(r.Eg_dft_eV, 3)}</td>
                  <td className="tnum px-3 py-1.5 text-ink-300">{fmtNumber(r.Eg_exp_eV, 2)}</td>
                  <td
                    className={`tnum px-3 py-1.5 ${
                      err == null ? '' : err < 0.2 ? 'text-green-300' : err < 0.5 ? 'text-amber-300' : 'text-red-300'
                    }`}
                  >
                    {fmtNumber(err, 3)}
                  </td>
                  <td className="px-3 py-1.5 text-xs">
                    {r.in_pv_window == null ? '—' : r.in_pv_window ? '✓' : '·'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </section>

      {/* ── Modelos ─────────────────────────────────────────────────────── */}
      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {(modelos.data?.models ?? []).map((m) => {
          const cv = (m.metrics.cv ?? {}) as Record<string, number | string>
          return (
            <div key={m.name} className="card-pad">
              <div className="truncate text-sm font-medium">{m.name.replace('surrogate_', '')}</div>
              <dl className="mt-2 space-y-0.5 text-xs">
                <Fila k="MAE (CV)" v={fmtNumber(cv.MAE_eV as number, 3)} />
                <Fila k="R²" v={fmtNumber(cv.R2 as number, 3)} />
                <Fila k="muestras" v={String(m.metrics.n_samples ?? cv.n_samples ?? '—')} />
                <Fila k="features" v={String(m.metrics.n_features ?? '—')} />
              </dl>
            </div>
          )
        })}
      </section>
    </div>
  )
}

function Fila({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-2">
      <dt className="text-ink-400">{k}</dt>
      <dd className="tnum">{v}</dd>
    </div>
  )
}

function Sitio({
  label,
  value,
  onChange,
  options,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  options: string[]
}) {
  return (
    <div>
      <label className="label mb-1 block">Sitio {label}</label>
      <select className="input" value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => (
          <option key={o}>{o}</option>
        ))}
      </select>
    </div>
  )
}

function Resultado({ p }: { p: Prediction }) {
  // Ventana fotovoltaica útil, para situar la predicción visualmente.
  const lo = 0.9
  const hi = 2.0
  const pct = (v: number) => Math.max(0, Math.min(100, ((v - 0.5) / (3.0 - 0.5)) * 100))

  return (
    <div className="space-y-3 border-t border-ink-800 pt-3">
      <div>
        <div className="tnum text-3xl font-semibold">
          {p.bandgap_pred.toFixed(3)}
          <span className="ml-1 text-base font-normal text-ink-400">eV</span>
        </div>
        <div className="tnum text-xs text-ink-400">± {p.bandgap_uncertainty.toFixed(3)} eV (bootstrap)</div>
      </div>

      <div className="relative h-6 rounded bg-ink-950">
        <div
          className="absolute inset-y-0 bg-st-converged/15"
          style={{ left: `${pct(lo)}%`, width: `${pct(hi) - pct(lo)}%` }}
          title="Ventana fotovoltaica útil 0.9–2.0 eV"
        />
        <div
          className="absolute inset-y-0 bg-st-running/40"
          style={{
            left: `${pct(p.bandgap_pred - p.bandgap_uncertainty)}%`,
            width: `${pct(p.bandgap_pred + p.bandgap_uncertainty) - pct(p.bandgap_pred - p.bandgap_uncertainty)}%`,
          }}
        />
        <div
          className="absolute inset-y-0 w-0.5 bg-ink-100"
          style={{ left: `${pct(p.bandgap_pred)}%` }}
        />
      </div>
      <div className="tnum flex justify-between text-[10px] text-ink-400">
        <span>0.5</span>
        <span>ventana PV 0.9–2.0 eV</span>
        <span>3.0</span>
      </div>

      <dl className="space-y-0.5 text-xs">
        <Fila k="Score solar" v={p.solar_score.toFixed(3)} />
        <Fila k="Score estabilidad" v={p.stability_score.toFixed(3)} />
        <Fila k="En ventana PV" v={p.in_pv_window ? 'sí' : 'no'} />
      </dl>
      <p className="text-[11px] text-ink-400">{p.model_name}</p>
    </div>
  )
}

function Parity({ filas }: { filas: Top8Row[] }) {
  const puntos = filas.filter((r) => r.Eg_ml_eV != null && r.Eg_exp_eV != null)
  if (!puntos.length)
    return (
      <div className="flex h-64 items-center justify-center text-sm text-ink-400">
        Sin predicciones disponibles
      </div>
    )

  const W = 420
  const H = 300
  const pad = 44
  const vals = puntos.flatMap((r) => [r.Eg_ml_eV!, r.Eg_exp_eV!, r.Eg_dft_eV ?? r.Eg_exp_eV!])
  const lo = Math.min(...vals) - 0.15
  const hi = Math.max(...vals) + 0.15
  const sx = (v: number) => pad + ((v - lo) / (hi - lo)) * (W - pad - 12)
  const sy = (v: number) => H - pad - ((v - lo) / (hi - lo)) * (H - pad - 12)
  const ticks = Array.from({ length: 5 }, (_, i) => lo + ((hi - lo) * i) / 4)

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Parity plot ML vs experimento">
      {ticks.map((v) => (
        <g key={v}>
          <line x1={sx(v)} x2={sx(v)} y1={12} y2={H - pad} stroke="#1a222d" />
          <line x1={pad} x2={W - 12} y1={sy(v)} y2={sy(v)} stroke="#1a222d" />
          <text x={sx(v)} y={H - pad + 15} textAnchor="middle" className="fill-ink-400 text-[9px]">
            {v.toFixed(1)}
          </text>
          <text x={pad - 6} y={sy(v) + 3} textAnchor="end" className="fill-ink-400 text-[9px]">
            {v.toFixed(1)}
          </text>
        </g>
      ))}

      {/* Diagonal de acuerdo perfecto */}
      <line x1={sx(lo)} y1={sy(lo)} x2={sx(hi)} y2={sy(hi)} stroke="#334155" strokeDasharray="4 3" />

      {puntos.map((r) => (
        <g key={r.material}>
          {/* Barra de incertidumbre del modelo */}
          {r.Eg_ml_std_eV != null && (
            <line
              x1={sx(r.Eg_exp_eV!)}
              x2={sx(r.Eg_exp_eV!)}
              y1={sy(r.Eg_ml_eV! - r.Eg_ml_std_eV)}
              y2={sy(r.Eg_ml_eV! + r.Eg_ml_std_eV)}
              stroke="#3b82f6"
              strokeOpacity={0.45}
              strokeWidth={1.5}
            />
          )}
          <circle cx={sx(r.Eg_exp_eV!)} cy={sy(r.Eg_ml_eV!)} r={4} fill="#3b82f6" />
          {r.Eg_dft_eV != null && (
            <circle
              cx={sx(r.Eg_exp_eV!)}
              cy={sy(r.Eg_dft_eV)}
              r={3}
              fill="none"
              stroke="#f59e0b"
              strokeWidth={1.5}
            />
          )}
          <title>
            {r.material}: ML {r.Eg_ml_eV!.toFixed(3)} · DFT {r.Eg_dft_eV?.toFixed(3) ?? '—'} · exp{' '}
            {r.Eg_exp_eV!.toFixed(2)}
          </title>
        </g>
      ))}

      <text x={W / 2} y={H - 6} textAnchor="middle" className="fill-ink-400 text-[10px]">
        Experimento (eV)
      </text>
      <text x={-H / 2} y={11} transform="rotate(-90)" textAnchor="middle" className="fill-ink-400 text-[10px]">
        Predicción (eV)
      </text>

      <g transform={`translate(${W - 108}, 20)`}>
        <circle cx={0} cy={0} r={4} fill="#3b82f6" />
        <text x={9} y={3} className="fill-ink-300 text-[10px]">ML</text>
        <circle cx={44} cy={0} r={3} fill="none" stroke="#f59e0b" strokeWidth={1.5} />
        <text x={53} y={3} className="fill-ink-300 text-[10px]">DFT</text>
      </g>
    </svg>
  )
}
