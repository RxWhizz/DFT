import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'

import { StructureViewer } from '@/components/StructureViewer'
import { api } from '@/lib/api'
import { fmtFormula } from '@/lib/format'

const GRUPOS = [
  { id: 'recientes', label: 'Generadas recientemente' },
  { id: 'jobs', label: 'Jobs actuales' },
  { id: 'fases', label: 'Fases de referencia' },
  { id: 'top8', label: 'Top 8' },
] as const

export function Structures() {
  const [seleccion, setSeleccion] = useState<string | null>(null)
  const [estilo, setEstilo] = useState<'ball-stick' | 'spacefill' | 'stick'>('ball-stick')
  const [supercell, setSupercell] = useState(1)
  const [celda, setCelda] = useState(true)
  const [filtro, setFiltro] = useState('')

  const lista = useQuery({ queryKey: ['structures'], queryFn: api.structures })

  const porGrupo = useMemo(() => {
    const needle = filtro.toLowerCase()
    const items = (lista.data?.items ?? []).filter(
      (s) => !needle || `${s.name} ${s.detail ?? ''}`.toLowerCase().includes(needle),
    )
    return GRUPOS.map((g) => ({
      ...g,
      items: items
        .filter((s) => s.group === g.id)
        .sort((a, b) => {
          if (g.id === 'recientes') {
            return (b.mtime ?? 0) - (a.mtime ?? 0) || a.name.localeCompare(b.name)
          }
          return a.name.localeCompare(b.name)
        }),
    }))
  }, [lista.data, filtro])

  const primerId = porGrupo.find((g) => g.items.length > 0)?.items[0]?.id ?? null
  const activo = seleccion ?? primerId
  const contenido = useQuery({
    queryKey: ['structure', activo],
    queryFn: () => api.structureContent(activo!),
    enabled: Boolean(activo),
  })
  const metadata = contenido.data?.metadata
  const organicPlaceholder = Boolean(metadata?.molecular_A_placeholder)

  return (
    <div className="grid gap-4 lg:grid-cols-[18rem_1fr]">
      <aside className="card-pad space-y-3">
        <input
          className="input"
          placeholder="Filtrar…"
          value={filtro}
          onChange={(e) => setFiltro(e.target.value)}
        />
        <div className="max-h-[calc(100vh-16rem)] space-y-3 overflow-y-auto">
          {porGrupo.map((g) => (
            <div key={g.id}>
              <div className="label mb-1">
                {g.label} ({g.items.length})
              </div>
              <ul className="space-y-0.5">
                {g.items.slice(0, 60).map((s) => (
                  <li key={s.id}>
                    <button
                      onClick={() => setSeleccion(s.id)}
                      className={`w-full rounded px-2 py-1.5 text-left text-sm transition ${
                        activo === s.id
                          ? 'bg-st-running/20 text-blue-200'
                          : 'text-ink-300 hover:bg-ink-850'
                      }`}
                    >
                      <span className="block truncate">{fmtFormula(s.name)}</span>
                      {s.detail && (
                        <span className="block truncate text-[10px] leading-tight text-ink-500">
                          {s.detail}
                        </span>
                      )}
                    </button>
                  </li>
                ))}
                {g.items.length > 60 && (
                  <li className="px-2 text-xs text-ink-400">+{g.items.length - 60} más — filtra</li>
                )}
              </ul>
            </div>
          ))}
        </div>
      </aside>

      <section className="card-pad space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="text-sm font-semibold">
            {contenido.data ? fmtFormula(contenido.data.name) : '—'}
          </h2>

          <div className="ml-auto flex flex-wrap items-center gap-3 text-xs">
            <label className="flex items-center gap-1.5">
              <span className="text-ink-400">Estilo</span>
              <select
                className="input w-auto py-1"
                value={estilo}
                onChange={(e) => setEstilo(e.target.value as typeof estilo)}
              >
                <option value="ball-stick">Bolas y varillas</option>
                <option value="spacefill">Compacto</option>
                <option value="stick">Varillas</option>
              </select>
            </label>

            <label className="flex items-center gap-1.5">
              <span className="text-ink-400">Supercelda</span>
              <select
                className="input w-auto py-1"
                value={supercell}
                onChange={(e) => setSupercell(Number(e.target.value))}
              >
                {[1, 2, 3].map((n) => (
                  <option key={n} value={n}>
                    {n}×{n}×{n}
                  </option>
                ))}
              </select>
            </label>

            <label className="flex items-center gap-1.5 text-ink-400">
              <input
                type="checkbox"
                checked={celda}
                onChange={(e) => setCelda(e.target.checked)}
                className="accent-blue-500"
              />
              Celda unidad
            </label>
          </div>
        </div>

        {contenido.isLoading ? (
          <div className="flex h-[460px] items-center justify-center text-sm text-ink-400">
            Cargando estructura…
          </div>
        ) : contenido.error ? (
          <div className="flex h-[460px] items-center justify-center text-sm text-red-300">
            {(contenido.error as Error).message}
          </div>
        ) : contenido.data ? (
          <StructureViewer
            cif={contenido.data.content}
            style={estilo}
            supercell={supercell}
            showCell={celda}
          />
        ) : null}

        {organicPlaceholder && (
          <p className="rounded border border-st-stalled/40 bg-st-stalled/10 px-3 py-2 text-xs leading-relaxed text-amber-300">
            {String(
              metadata?.organic_A_warning ??
                'MA/FA se representa con un placeholder inorgánico en el CIF.',
            )}
          </p>
        )}

        <p className="text-xs text-ink-400">
          Arrastra para rotar, rueda para acercar. Las estructuras en formato JSON de ASE se
          convierten a CIF en el servidor.
        </p>
      </section>
    </div>
  )
}
