import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'

import { ConfirmButton } from '@/components/ConfirmButton'
import { api, type SetupCapability, type SetupJob, type SetupStatus } from '@/lib/api'

/** Cada cuánto se refresca el log mientras hay una instalación viva. */
const POLL_MS = 1500

/**
 * Sólo el MLFF se instala desde aquí: los demás grupos van al intérprete del
 * propio monitor, que no puede reinstalarse a sí mismo mientras está sirviendo.
 */
const INSTALABLES = new Set(['mlff'])

export function Setup() {
  const qc = useQueryClient()

  // La sonda MLFF lanza un proceso (y en Windows, una distro de WSL). Se pide
  // primero la versión rápida para pintar algo ya y luego la completa, en vez
  // de dejar la página en blanco varios segundos.
  const rapido = useQuery({
    queryKey: ['setup', 'status', 'fast'],
    queryFn: () => api.setupStatus(true),
  })
  const completo = useQuery({
    queryKey: ['setup', 'status', 'full'],
    queryFn: () => api.setupStatus(false),
  })

  const job = useQuery({
    queryKey: ['setup', 'job'],
    queryFn: api.setupJob,
    refetchInterval: (q) => (q.state.data?.running ? POLL_MS : false),
  })

  // Al terminar una instalación, lo que estaba roto ya no lo está: se vuelve a
  // comprobar sin que el usuario tenga que pulsar nada.
  const corriendoAntes = useRef(false)
  useEffect(() => {
    const ahora = Boolean(job.data?.running)
    if (corriendoAntes.current && !ahora) {
      void qc.invalidateQueries({ queryKey: ['setup', 'status'] })
      void qc.invalidateQueries({ queryKey: ['health'] })
    }
    corriendoAntes.current = ahora
  }, [job.data?.running, qc])

  const data = completo.data ?? rapido.data
  const instalar = useMutation({
    mutationFn: (v: { target: string; recreate: boolean }) =>
      api.setupInstall(v.target, { recreate: v.recreate }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['setup', 'job'] }),
  })

  if (!data) {
    return <p className="p-4 text-sm text-ink-400">Comprobando el entorno…</p>
  }

  return (
    <div className="space-y-4 p-4">
      <header className="flex items-center gap-3">
        <h1 className="text-lg font-semibold">Entorno</h1>
        <EstadoGlobal status={data.status} />
        {completo.isFetching && !completo.data && (
          <span className="text-xs text-ink-400">sondeando MLFF…</span>
        )}
        <button
          type="button"
          className="ml-auto rounded border border-ink-700 px-3 py-1 text-sm"
          onClick={() => void qc.invalidateQueries({ queryKey: ['setup'] })}
        >
          Recomprobar
        </button>
      </header>

      {data.frozen && (
        <p className="rounded border border-ink-700 bg-ink-900/40 p-3 text-sm text-ink-300">
          Este monitor es un binario empaquetado: no tiene dónde instalar paquetes de
          Python. Las dependencias que corren fuera (WSL) sí se pueden instalar desde aquí.
        </p>
      )}

      <div className="grid gap-3">
        {data.capacidades.map((cap) => (
          <Capacidad
            key={cap.id}
            cap={cap}
            bloqueado={Boolean(job.data?.running) || instalar.isPending}
            onInstalar={(recreate) =>
              instalar.mutate({ target: cap.id, recreate })
            }
          />
        ))}
      </div>

      {instalar.isError && (
        <p className="text-sm text-red-400">{(instalar.error as Error).message}</p>
      )}

      {job.data && !esVacio(job.data) && <PanelJob job={job.data} />}

      <Interprete data={data} />
    </div>
  )
}

function esVacio(job: SetupJob): boolean {
  return !job.target && job.log.length === 0
}

function EstadoGlobal({ status }: { status: SetupStatus['status'] }) {
  const [clase, texto] =
    status === 'ok'
      ? ['border-emerald-600 text-emerald-400', 'Todo listo']
      : status === 'degradado'
        ? ['border-amber-600 text-amber-400', 'Funciona con limitaciones']
        : ['border-red-600 text-red-400', 'Falta algo esencial']
  return <span className={`rounded border px-2 py-0.5 text-xs ${clase}`}>{texto}</span>
}

function Capacidad({
  cap,
  bloqueado,
  onInstalar,
}: {
  cap: SetupCapability
  bloqueado: boolean
  onInstalar: (recreate: boolean) => void
}) {
  // Un `versiones` que no sea un objeto (un string suelto, por ejemplo) haría
  // que Object.entries recorriera sus caracteres y pintara un chip por letra.
  const crudo = cap.detalle?.versiones
  const versiones =
    crudo && typeof crudo === 'object' && !Array.isArray(crudo)
      ? (crudo as Record<string, string>)
      : {}
  const instalable = INSTALABLES.has(cap.id)
  const color = cap.ok
    ? 'border-emerald-800'
    : cap.requerido
      ? 'border-red-800'
      : 'border-amber-800'

  return (
    <section className={`rounded border ${color} bg-ink-900/30 p-3`}>
      <div className="flex items-center gap-2">
        <span className={cap.ok ? 'text-emerald-400' : 'text-amber-400'}>
          {cap.ok ? '●' : '○'}
        </span>
        <h2 className="text-sm font-medium">{cap.titulo}</h2>
        {!cap.requerido && <span className="text-xs text-ink-500">opcional</span>}
        <div className="ml-auto">
          {instalable && !cap.ok && (
            <ConfirmButton onConfirm={() => onInstalar(false)} disabled={bloqueado}>
              Instalar
            </ConfirmButton>
          )}
          {instalable && cap.ok && (
            <ConfirmButton onConfirm={() => onInstalar(true)} disabled={bloqueado}>
              Reinstalar
            </ConfirmButton>
          )}
        </div>
      </div>

      {Object.keys(versiones).length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-2">
          {Object.entries(versiones).map(([k, v]) => (
            <li key={k} className="rounded bg-ink-800 px-2 py-0.5 text-xs text-ink-300">
              {k} {v}
            </li>
          ))}
        </ul>
      )}

      {!cap.ok && (
        <div className="mt-2 space-y-1 text-xs">
          {cap.error && <p className="text-red-400">{cap.error}</p>}
          {cap.remediacion && <p className="text-ink-300">{cap.remediacion}</p>}
          {cap.comando && (
            <code className="block rounded bg-ink-950 px-2 py-1 text-ink-400">
              $ {cap.comando}
            </code>
          )}
        </div>
      )}
    </section>
  )
}

function PanelJob({ job }: { job: SetupJob }) {
  const fondo = useRef<HTMLPreElement>(null)
  useEffect(() => {
    if (fondo.current) fondo.current.scrollTop = fondo.current.scrollHeight
  }, [job.log])

  return (
    <section className="rounded border border-ink-700 p-3">
      <h2 className="text-sm font-medium">
        {job.running
          ? `Instalando ${job.target ?? ''}…`
          : `Instalación de ${job.target ?? ''}: ${job.status ?? ''}`}
      </h2>
      {job.error && <p className="mt-1 text-xs text-red-400">{job.error}</p>}
      <pre
        ref={fondo}
        className="mt-2 h-64 overflow-auto rounded bg-ink-950 p-2 text-xs text-ink-300"
      >
        {job.log.length ? job.log.join('\n') : '(sin salida todavía)'}
      </pre>
    </section>
  )
}

function Interprete({ data }: { data: SetupStatus }) {
  return (
    <section className="rounded border border-ink-800 p-3 text-xs text-ink-400">
      <p className="uppercase tracking-wide text-ink-500">Intérprete del monitor</p>
      <p className="mt-1">
        Python {data.python} · {data.plataforma}
      </p>
      <code className="mt-1 block break-all">{data.executable}</code>
    </section>
  )
}
