import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import { api, type Gallery } from '@/lib/api'

export function Results() {
  const [doc, setDoc] = useState<string | null>(null)
  const reports = useQuery({ queryKey: ['reports'], queryFn: api.reports })

  const activo = doc ?? reports.data?.documents[0]?.path ?? null
  const contenido = useQuery({
    queryKey: ['report', activo],
    queryFn: () => api.reportDocument(activo!),
    enabled: Boolean(activo),
  })

  return (
    <div className="grid gap-4 lg:grid-cols-[18rem_1fr]">
      <aside className="card-pad space-y-4">
        <div>
          <div className="label mb-1.5">Documentos ({reports.data?.documents.length ?? 0})</div>
          <ul className="space-y-0.5">
            {(reports.data?.documents ?? []).map((d) => (
              <li key={d.path}>
                <button
                  onClick={() => setDoc(d.path)}
                  className={`w-full rounded px-2 py-1 text-left text-sm transition ${
                    activo === d.path
                      ? 'bg-st-running/20 text-blue-200'
                      : 'text-ink-300 hover:bg-ink-850'
                  }`}
                  title={d.path}
                >
                  <div className="truncate">{d.name}</div>
                  <div className="truncate text-[10px] text-ink-400">{d.group}</div>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </aside>

      <div className="min-w-0 space-y-4">
        <section className="card-pad">
          {contenido.isLoading ? (
            <p className="text-sm text-ink-400">Cargando…</p>
          ) : contenido.data ? (
            <article className="prose-dft">
              <Markdown remarkPlugins={[remarkGfm]}>{contenido.data.content}</Markdown>
            </article>
          ) : (
            <p className="text-sm text-ink-400">Selecciona un documento.</p>
          )}
        </section>

        {(reports.data?.galleries ?? []).map((g) => (
          <Galeria key={g.name} galeria={g} />
        ))}
      </div>
    </div>
  )
}

function Galeria({ galeria }: { galeria: Gallery }) {
  const presentes = galeria.figures.filter((f) => f.present)
  const ausentes = galeria.n_declared - galeria.n_present

  return (
    <section className="card-pad">
      <header className="mb-3 flex flex-wrap items-baseline gap-x-3">
        <h2 className="label">{galeria.name}</h2>
        <span className="tnum text-xs text-ink-400">
          {galeria.n_present} de {galeria.n_declared} figuras en disco
        </span>
      </header>

      {presentes.length > 0 && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {presentes.map((f) => (
            <figure key={f.path} className="space-y-1">
              <img
                src={api.figureUrl(f.path)}
                alt={f.name}
                loading="lazy"
                className="w-full rounded border border-ink-800 bg-ink-950"
              />
              <figcaption className="truncate text-[11px] text-ink-400" title={f.name}>
                {f.name}
              </figcaption>
            </figure>
          ))}
        </div>
      )}

      {ausentes > 0 && (
        <p className="mt-2 text-xs leading-relaxed text-ink-400">
          {ausentes} figura{ausentes === 1 ? '' : 's'} declarada
          {ausentes === 1 ? '' : 's'} en el manifest pero ausente
          {ausentes === 1 ? '' : 's'} del disco — los PNG y PDF están en{' '}
          <code className="font-mono">.gitignore</code>. Regenéralas con{' '}
          <code className="font-mono">scripts/generate_visualizations.py</code>.
        </p>
      )}
    </section>
  )
}
