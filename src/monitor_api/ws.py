"""Fan-out de eventos del poller hacia clientes WebSocket.

Sustituye al bucle de sondeo original (drenar cola + `sleep(1)` por cliente):

* una **única** task consume `poller.event_queue` y reparte a las colas por
  cliente, en vez de una task por conexión compitiendo sobre la misma cola;
* los clientes esperan con `await queue.get()` en lugar de sondear cada segundo;
* se emite un ping real cuando no hay tráfico, para que las conexiones muertas
  se detecten (el bucle anterior lo prometía en un comentario y nunca lo hacía);
* cada mensaje lleva un `seq` monotónico y una cola llena genera un aviso `gap`,
  de modo que el cliente sabe que perdió estado y puede resincronizar por REST
  en lugar de quedarse en silencio con datos obsoletos.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

log = logging.getLogger(__name__)

router = APIRouter()

# Segundos sin tráfico tras los que se envía un ping.
PING_INTERVAL_SEC = 15.0
# Mensajes en vuelo por cliente antes de empezar a descartar.
CLIENT_QUEUE_MAX = 256


@dataclass
class _Client:
    queue: asyncio.Queue[str] = field(
        default_factory=lambda: asyncio.Queue(maxsize=CLIENT_QUEUE_MAX)
    )
    dropped: int = 0


class EventHub:
    """Reparte los eventos del poller a todos los WebSocket conectados."""

    def __init__(self) -> None:
        self._clients: dict[int, _Client] = {}
        self._next_id = 0
        self._seq = 0
        self._task: asyncio.Task | None = None

    # ── ciclo de vida ────────────────────────────────────────────────────────

    def start(self, poller) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._pump(poller))

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    # ── estado ───────────────────────────────────────────────────────────────

    @property
    def seq(self) -> int:
        return self._seq

    @property
    def n_clients(self) -> int:
        return len(self._clients)

    # ── registro de clientes ─────────────────────────────────────────────────

    def register(self) -> tuple[int, _Client]:
        self._next_id += 1
        client = _Client()
        self._clients[self._next_id] = client
        return self._next_id, client

    def unregister(self, client_id: int) -> None:
        self._clients.pop(client_id, None)

    # ── reparto ──────────────────────────────────────────────────────────────

    async def _pump(self, poller) -> None:
        """Task única: consume la cola del poller y reparte a los clientes."""
        log.info("EventHub iniciado")
        while True:
            try:
                event = await poller.event_queue.get()
            except asyncio.CancelledError:
                log.info("EventHub detenido")
                raise
            except Exception as exc:  # la cola no debería fallar, pero no morimos por ello
                log.error("EventHub: error leyendo la cola del poller: %s", exc)
                await asyncio.sleep(1)
                continue

            self._seq += 1
            payload = event.model_dump()
            payload["type"] = "event"
            payload["seq"] = self._seq
            text = json.dumps(payload, default=str)

            for client in list(self._clients.values()):
                try:
                    client.queue.put_nowait(text)
                except asyncio.QueueFull:
                    client.dropped += 1


@router.websocket("/ws/events")
async def ws_events(websocket: WebSocket) -> None:
    await websocket.accept()
    hub: EventHub = websocket.app.state.hub
    client_id, client = hub.register()
    log.info("WebSocket conectado desde %s (clientes=%d)", websocket.client, hub.n_clients)

    try:
        await websocket.send_json({"type": "hello", "seq": hub.seq})

        while True:
            try:
                text = await asyncio.wait_for(client.queue.get(), timeout=PING_INTERVAL_SEC)
            except asyncio.TimeoutError:
                # Sin tráfico: ping real para detectar conexiones muertas.
                await websocket.send_json({"type": "ping", "seq": hub.seq})
                continue

            if client.dropped:
                dropped, client.dropped = client.dropped, 0
                log.warning("WebSocket %d: %d eventos descartados", client_id, dropped)
                await websocket.send_json(
                    {"type": "gap", "dropped": dropped, "seq": hub.seq}
                )

            await websocket.send_text(text)

    except WebSocketDisconnect:
        log.info("WebSocket desconectado")
    except (RuntimeError, ConnectionError) as exc:
        log.info("WebSocket cerrado: %s", exc)
    finally:
        hub.unregister(client_id)
