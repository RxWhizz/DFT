/**
 * Cliente WebSocket del monitor.
 *
 * El servidor (src/monitor_api/ws.py) manda cuatro tipos de mensaje:
 *   hello — al conectar, con el `seq` actual
 *   event — un cambio de estado de un job
 *   ping  — cada 15 s sin tráfico, para detectar conexiones muertas
 *   gap   — se descartaron N eventos: hay que resincronizar por REST
 *
 * Aquí se añade reconexión con backoff exponencial y, ante un `gap` o una
 * reconexión, se avisa para refrescar el estado desde REST en vez de seguir
 * con datos incompletos.
 */
import { useCallback, useEffect, useRef, useState } from 'react'

export type EventName =
  | 'STARTED' | 'CONVERGED' | 'FAILED' | 'STOPPED'
  | 'STALLED' | 'OSCILLATING' | 'PING'

export interface JobEvent {
  seq: number
  job_id: string
  event: EventName
  timestamp: string
  data: Record<string, unknown>
}

export type ConnState = 'connecting' | 'open' | 'closed' | 'unauthorized'

const MAX_EVENTS = 200
const BASE_DELAY_MS = 500
const MAX_DELAY_MS = 30_000
/** Cierre con 1008 = el servidor nos rechazó por falta de sesión. */
const POLICY_VIOLATION = 1008

function wsUrl(): string {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}/ws/events`
}

export interface UseEventsOptions {
  /** Se llama al reconectar o tras un `gap`: momento de refrescar por REST. */
  onResync?: () => void
  enabled?: boolean
}

export function useEvents({ onResync, enabled = true }: UseEventsOptions = {}) {
  const [state, setState] = useState<ConnState>('connecting')
  const [events, setEvents] = useState<JobEvent[]>([])
  const [lastSeq, setLastSeq] = useState(0)

  const socketRef = useRef<WebSocket | null>(null)
  const timerRef = useRef<number | null>(null)
  const attemptRef = useRef(0)
  const closedByUs = useRef(false)
  // En un ref para que reconectar no dependa de la identidad del callback.
  const resyncRef = useRef(onResync)
  resyncRef.current = onResync

  const connect = useCallback(() => {
    if (closedByUs.current) return

    setState((s) => (s === 'open' ? s : 'connecting'))
    const socket = new WebSocket(wsUrl())
    socketRef.current = socket

    socket.onopen = () => {
      attemptRef.current = 0
      setState('open')
      // Una reconexión implica un hueco de duración desconocida.
      resyncRef.current?.()
    }

    socket.onmessage = (raw) => {
      let msg: { type?: string; seq?: number; dropped?: number }
      try {
        msg = JSON.parse(raw.data)
      } catch {
        return
      }
      if (typeof msg.seq === 'number') setLastSeq(msg.seq)

      switch (msg.type) {
        case 'event':
          setEvents((prev) => [msg as unknown as JobEvent, ...prev].slice(0, MAX_EVENTS))
          break
        case 'gap':
          // El servidor descartó eventos: el estado local ya no es fiable.
          resyncRef.current?.()
          break
        case 'hello':
        case 'ping':
          break
      }
    }

    socket.onclose = (ev) => {
      socketRef.current = null
      if (closedByUs.current) return

      if (ev.code === POLICY_VIOLATION) {
        setState('unauthorized')
        return // sin sesión no tiene sentido reintentar
      }

      setState('closed')
      const delay = Math.min(BASE_DELAY_MS * 2 ** attemptRef.current, MAX_DELAY_MS)
      attemptRef.current += 1
      timerRef.current = window.setTimeout(connect, delay)
    }

    socket.onerror = () => socket.close()
  }, [])

  useEffect(() => {
    if (!enabled) return
    closedByUs.current = false
    connect()

    return () => {
      closedByUs.current = true
      if (timerRef.current) window.clearTimeout(timerRef.current)
      socketRef.current?.close()
      socketRef.current = null
    }
  }, [connect, enabled])

  const clear = useCallback(() => setEvents([]), [])

  return { state, events, lastSeq, clear }
}
