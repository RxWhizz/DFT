import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'

import { Scatter, type Punto } from '@/components/Scatter'
import { api, type CandidatesQuery } from '@/lib/api'
import { fmtFormula, fmtNumber } from '@/lib/format'

export function Candidates() {
  const [q, setQ] = useState('')
  const [modo, setModo] = useState('')
  const [halide, setHalide] = useState('')

  const params: CandidatesQuery = { q, generation_mode: modo, halide, limit: 2000 }
  const { data, isFetching } = useQuery({
    queryKey: ['candidates', params],
    queryFn: () => api.candidates(params),
    placeholderData: keepPreviousData,
  })

  const puntos: Punto[] = useMemo(
    () =>
      (data?.items ?? [])
        .filter((c) => c.tolerance_t != null && c.oct_factor != null)
        .map((c) => ({
          x: c.tolerance_t as number,
          y: c.oct_factor as number,
          label: c.formula ?? '—',
          value: c.score,
        })),
    [data],
  )

  const cotas = data?.filters
  const dentro = useMemo(() => {
    if (!cotas) return 0
    return puntos.filter(
      (p) =>
        p.x >= cotas.goldschmidt.min &&
        p.x <= cotas.goldschmidt.max &&
        p.y >= cotas.octahedral.min &&
        p.y <= cotas.octahedral.max,
    ).length
  }, [puntos, cotas])

  const conDft = (data?.items ?? []).filter((c) => c.has_dft).length
  const convergidos = (data?.items ?? []).filter((c) => c.dft_status === 'converged').length

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <input
          className="input max-w-xs"
          placeholder="Buscar fórmula…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <Select
          value={modo}
          onChange={setModo}
          placeholder="Modo de generación"
          options={data?.facets.generation_mode ?? []}
        />
        <Select
          value={halide}
          onChange={setHalide}
          placeholder="Haluro dominante"
          options={data?.facets.dominant_halide ?? []}
        />
        <span className="ml-auto text-xs text-ink-400">
          origen: <code className="font-mono">{data?.source ?? '—'}</code>
          {isFetching && ' · actualizando'}
        </span>
      </div>

      {/* Embudo de cribado */}
      <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Candidatos" value={data?.total} />
        <Stat label="Dentro de filtros" value={dentro} tone="text-green-300" />
        <Stat label="Con DFT" value={conDft} tone="text-blue-300" />
        <Stat label="Convergidos" value={convergidos} tone="text-green-300" />
      </section>

      <section className="card-pad">
        <div className="mb-2 flex items-baseline justify-between">
          <h2 className="label">Espacio de estabilidad</h2>
          <span className="text-xs text-ink-400">Cotas</span>
        </div>
        <Scatter
          puntos={puntos}
          bandaX={cotas?.goldschmidt}
          bandaY={cotas?.octahedral}
          xLabel="Tolerancia de Goldschmidt  t"
          yLabel="Factor octaédrico"
        />
      </section>

      <section className="card overflow-hidden">
        <div className="max-h-[26rem] overflow-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 border-b border-ink-800 bg-ink-850 text-left">
              <tr className="label">
                <th className="px-3 py-2">Fórmula</th>
                <th className="px-3 py-2">Score</th>
                <th className="px-3 py-2">t</th>
                <th className="px-3 py-2">oct</th>
                <th className="px-3 py-2">Modo</th>
                <th className="px-3 py-2">Familia B</th>
                <th className="px-3 py-2">DFT</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-800">
              {(data?.items ?? []).slice(0, 300).map((c) => (
                <tr key={c.candidate_id ?? c.formula} className="hover:bg-ink-850/60">
                  <td className="px-3 py-1.5 font-medium">{fmtFormula(c.formula)}</td>
                  <td className="tnum px-3 py-1.5">{fmtNumber(c.score, 3)}</td>
                  <td className="tnum px-3 py-1.5 text-ink-300">{fmtNumber(c.tolerance_t, 3)}</td>
                  <td className="tnum px-3 py-1.5 text-ink-300">{fmtNumber(c.oct_factor, 3)}</td>
                  <td className="px-3 py-1.5 text-xs text-ink-400">{c.generation_mode ?? '—'}</td>
                  <td className="px-3 py-1.5 text-xs text-ink-400">{c.b_family ?? '—'}</td>
                  <td className="px-3 py-1.5 text-xs text-ink-400">{c.dft_status ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {(data?.items.length ?? 0) > 300 && (
          <p className="border-t border-ink-800 px-3 py-2 text-xs text-ink-400">
            Mostrando 300 de {data?.items.length}. Afina con los filtros de arriba.
          </p>
        )}
      </section>
    </div>
  )
}

function Select({
  value,
  onChange,
  placeholder,
  options,
}: {
  value: string
  onChange: (v: string) => void
  placeholder: string
  options: string[]
}) {
  return (
    <select
      className="input w-auto"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={!options.length}
    >
      <option value="">{placeholder}</option>
      {options.map((o) => (
        <option key={o} value={o}>
          {o}
        </option>
      ))}
    </select>
  )
}

function Stat({ label, value, tone }: { label: string; value?: number; tone?: string }) {
  return (
    <div className="card-pad">
      <div className="label">{label}</div>
      <div className={`tnum mt-1 text-2xl font-semibold ${tone ?? ''}`}>{value ?? '—'}</div>
    </div>
  )
}
