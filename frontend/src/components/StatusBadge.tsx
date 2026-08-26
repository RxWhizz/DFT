import type { JobStatusName } from '@/lib/api'

/**
 * Misma semántica de estados que el mapa `_ICON` del bot de Telegram
 * (src/monitor_api/router.py), para que ambas superficies se lean igual.
 */
const STYLE: Record<JobStatusName, { dot: string; text: string; label: string }> = {
  running:           { dot: 'bg-st-running',     text: 'text-blue-300',   label: 'corriendo' },
  converged:         { dot: 'bg-st-converged',   text: 'text-green-300',  label: 'convergido' },
  failed:            { dot: 'bg-st-failed',      text: 'text-red-300',    label: 'fallido' },
  stopped:           { dot: 'bg-st-stopped',     text: 'text-rose-300',   label: 'detenido' },
  stalled:           { dot: 'bg-st-stalled',     text: 'text-amber-300',  label: 'estancado' },
  oscillating:       { dot: 'bg-st-oscillating', text: 'text-orange-300', label: 'oscilando' },
  pending:           { dot: 'bg-st-pending',     text: 'text-slate-300',  label: 'en cola' },
  partial:           { dot: 'bg-st-stalled',     text: 'text-amber-200',  label: 'parcial' },
  skipped_duplicate: { dot: 'bg-st-skipped',     text: 'text-violet-300', label: 'duplicado' },
  unknown:           { dot: 'bg-st-unknown',     text: 'text-ink-400',    label: 'desconocido' },
}

export function StatusBadge({ status, compact }: { status: JobStatusName; compact?: boolean }) {
  const s = STYLE[status] ?? STYLE.unknown
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs ${s.text}`}>
      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${s.dot}`} />
      {!compact && s.label}
    </span>
  )
}

export function statusLabel(status: JobStatusName): string {
  return (STYLE[status] ?? STYLE.unknown).label
}
