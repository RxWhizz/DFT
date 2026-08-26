import { useMutation, useQuery } from '@tanstack/react-query'
import { FormEvent, useMemo, useState } from 'react'

import { api, type AgentChatResponse, type AgentMessage } from '@/lib/api'

interface ChatTurn {
  role: 'user' | 'assistant'
  content: string
  response?: AgentChatResponse
}

export function Agent() {
  const health = useQuery({
    queryKey: ['agent', 'health'],
    queryFn: api.agentHealth,
    refetchInterval: 15_000,
  })
  const [input, setInput] = useState('')
  const [structured, setStructured] = useState(false)
  const [turns, setTurns] = useState<ChatTurn[]>([])
  const [proposalState, setProposalState] = useState<Record<string, string>>({})

  const history = useMemo<AgentMessage[]>(
    () =>
      turns.slice(-8).map((t) => ({
        role: t.role,
        content: t.content,
      })),
    [turns],
  )

  const chat = useMutation({
    mutationFn: (message: string) => api.agentChat({ message, history, structured }),
    onSuccess: (response, message) => {
      setTurns((prev) => [
        ...prev,
        { role: 'user', content: message },
        { role: 'assistant', content: response.message || '(sin texto)', response },
      ])
      setInput('')
    },
  })

  const approve = useMutation({
    mutationFn: (id: string) => api.approveAgentProposal(id),
    onSuccess: (p) => setProposalState((s) => ({ ...s, [p.id]: p.status })),
  })

  const reject = useMutation({
    mutationFn: (id: string) => api.rejectAgentProposal(id),
    onSuccess: (p) => setProposalState((s) => ({ ...s, [p.id]: p.status })),
  })

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    const message = input.trim()
    if (message) chat.mutate(message)
  }

  const h = health.data
  const canChat = Boolean(h?.enabled && h?.ok) && !health.isError
  const statusText = health.isLoading
    ? 'comprobando'
    : health.isError
      ? (health.error as Error).message
      : h?.ok
        ? 'listo'
        : h?.enabled
          ? h?.error || 'no disponible'
          : 'desactivado'

  return (
    <div className="grid h-[calc(100vh-7rem)] gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
      <section className="flex min-h-0 flex-col rounded-lg border border-ink-800 bg-ink-900">
        <header className="flex flex-wrap items-center gap-3 border-b border-ink-800 px-4 py-3">
          <h1 className="text-sm font-semibold">Agente</h1>
          <span
            className={`h-2 w-2 rounded-full ${
              health.isLoading
                ? 'animate-pulse bg-ink-400'
                : h?.ok
                  ? 'bg-st-converged'
                  : h?.enabled
                    ? 'bg-st-stalled'
                    : 'bg-ink-600'
            }`}
            title={statusText}
          />
          <span className="tnum text-xs text-ink-400">{h?.model ?? 'dft-agent:14b-q4'}</span>
          {h?.model_present === false && h?.enabled && (
            <span className="rounded border border-st-stalled/40 bg-st-stalled/10 px-2 py-0.5 text-[11px] text-amber-300">
              modelo pendiente
            </span>
          )}
        </header>

        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          {health.isError && (
            <p className="rounded border border-st-failed/40 bg-st-failed/10 p-3 text-sm text-red-200">
              No se pudo consultar el agente: {(health.error as Error).message}
            </p>
          )}
          {!health.isError && h?.enabled && !h.ok && (
            <p className="rounded border border-st-stalled/40 bg-st-stalled/10 p-3 text-sm text-amber-200">
              Agente no disponible: {h.error || 'Ollama no respondio al health check'}.
            </p>
          )}
          {!turns.length ? (
            <p className="max-w-2xl text-sm leading-relaxed text-ink-400">
              Pregunta por el estado del pipeline, lista jobs fallidos, resume logs o compara lotes.
              Para diagnosticar un job desde esta vista, pega su job_id exacto; el botón Diagnosticar
              del detalle de job lo envía automáticamente.
            </p>
          ) : (
            turns.map((turn, i) => (
              <article
                key={i}
                className={`max-w-3xl rounded-lg border p-3 text-sm ${
                  turn.role === 'user'
                    ? 'ml-auto border-st-running/30 bg-st-running/10'
                    : 'border-ink-800 bg-ink-950'
                }`}
              >
                <div className="mb-1 text-[11px] font-medium uppercase text-ink-400">
                  {turn.role === 'user' ? 'Tú' : 'Agente'}
                </div>
                <p className="whitespace-pre-wrap leading-relaxed">{turn.content}</p>
                {turn.response && <AgentResult response={turn.response} />}
                {turn.response?.proposal_ids?.map((id) => (
                  <div key={id} className="mt-3 flex flex-wrap items-center gap-2 text-xs">
                    <span className="tnum text-ink-400">{id}</span>
                    <button
                      className="btn px-2 py-1 text-xs"
                      onClick={() => approve.mutate(id)}
                      disabled={approve.isPending || proposalState[id] === 'approved'}
                    >
                      Aprobar
                    </button>
                    <button
                      className="btn px-2 py-1 text-xs"
                      onClick={() => reject.mutate(id)}
                      disabled={reject.isPending || proposalState[id] === 'rejected'}
                    >
                      Rechazar
                    </button>
                    {proposalState[id] && <span className="text-ink-300">{proposalState[id]}</span>}
                  </div>
                ))}
              </article>
            ))
          )}
          {chat.isError && <p className="text-sm text-red-300">{(chat.error as Error).message}</p>}
        </div>

        <form onSubmit={onSubmit} className="border-t border-ink-800 p-3">
          <div className="flex flex-col gap-2 sm:flex-row">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              className="input min-w-0 flex-1"
              placeholder="Pregunta al agente local…"
              disabled={!canChat || chat.isPending}
            />
            <label className="flex items-center gap-2 rounded-md border border-ink-800 px-3 py-1.5 text-xs text-ink-300">
              <input
                type="checkbox"
                checked={structured}
                onChange={(e) => setStructured(e.target.checked)}
              />
              JSON
            </label>
            <button className="btn-primary" disabled={!input.trim() || !canChat || chat.isPending}>
              {chat.isPending ? 'Consultando…' : 'Enviar'}
            </button>
          </div>
        </form>
      </section>

      <aside className="space-y-3 overflow-y-auto">
        <section className="card-pad">
          <h2 className="label mb-3">Ollama</h2>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-xs">
            <dt className="text-ink-400">Estado</dt>
            <dd>{statusText}</dd>
            <dt className="text-ink-400">URL</dt>
            <dd className="tnum break-all">{h?.base_url ?? '—'}</dd>
            <dt className="text-ink-400">Versión</dt>
            <dd className="tnum">{h?.version ?? '—'}</dd>
            <dt className="text-ink-400">Modelos</dt>
            <dd className="break-all">{h?.models_dir ?? '—'}</dd>
            <dt className="text-ink-400">Revive</dt>
            <dd className="break-all">{h?.revive_repo ?? '—'}</dd>
          </dl>
        </section>

        <section className="card-pad">
          <h2 className="label mb-3">Límites</h2>
          <ul className="space-y-2 text-xs leading-relaxed text-ink-300">
            <li>Herramientas v1: sólo lectura.</li>
            <li>Máximo 4 rondas de tool calls.</li>
            <li>Escrituras: propuestas auditadas.</li>
          </ul>
        </section>
      </aside>
    </div>
  )
}

function AgentResult({ response }: { response: AgentChatResponse }) {
  const proposal = response.structured?.proposal
  const command = isRecord(proposal) ? textValue(proposal.command) : null
  const rationale = isRecord(proposal) ? textValue(proposal.rationale) : null
  return (
    <div className="mt-3 space-y-2 border-t border-ink-800 pt-3 text-xs">
      {!!response.tool_results.length && (
        <div className="flex flex-wrap gap-1.5">
          {response.tool_results.map((tool, i) => (
            <span
              key={`${tool.name}-${i}`}
              className={`rounded border px-2 py-0.5 ${
                tool.ok
                  ? 'border-st-converged/30 bg-st-converged/10 text-green-200'
                  : 'border-st-failed/30 bg-st-failed/10 text-red-200'
              }`}
              title={tool.error || tool.name}
            >
              {tool.name}
            </span>
          ))}
        </div>
      )}
      {response.structured && (
        <pre className="max-h-72 overflow-auto rounded border border-ink-800 bg-ink-950 p-2 text-[11px] text-ink-300">
          {JSON.stringify(response.structured, null, 2)}
        </pre>
      )}
      {isRecord(proposal) && (
        <div className="rounded border border-st-stalled/40 bg-st-stalled/10 p-2">
          <div className="font-medium text-amber-200">{String(proposal.title ?? 'Propuesta')}</div>
          {command && <pre className="mt-1 overflow-auto font-mono">{command}</pre>}
          {rationale && <p className="mt-1 text-ink-300">{rationale}</p>}
        </div>
      )}
    </div>
  )
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function textValue(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null
}
