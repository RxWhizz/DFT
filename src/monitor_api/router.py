"""Endpoints REST y WebSocket del monitor DFT."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Request
from pydantic import BaseModel

from .models import (
    JobStatus,
    PingResponse,
    StatsResponse,
    SummaryResponse,
    WsEvent,
)
from .poller import DFTPoller, ping_job, _read_status
from .sysmetrics import SysMetrics, collect as collect_metrics, format_telegram as fmt_sys
from .utils import fmt_formula

log = logging.getLogger(__name__)

router = APIRouter()

# WebSocket suscriptores activos
_ws_clients: list[asyncio.Queue[str]] = []


def get_poller(request: Request) -> DFTPoller:
    return request.app.state.poller


# ── REST endpoints ────────────────────────────────────────────────────────────

@router.get("/api/jobs", response_model=list[JobStatus])
async def list_jobs(request: Request) -> list[JobStatus]:
    poller = get_poller(request)
    return [
        JobStatus(
            job_id=s.job_id,
            formula=s.formula,
            status=s.status,
            pid=s.pid,
            start_time=s.start_time,
            elapsed_min=s.elapsed_min,
            mpi_cores=s.mpi_cores,
        )
        for s in poller.snapshots.values()
    ]


@router.get("/api/jobs/{job_id}", response_model=StatsResponse)
async def get_job(job_id: str, request: Request) -> StatsResponse:
    poller = get_poller(request)
    snap = poller.snapshots.get(job_id)
    if snap is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' no encontrado")
    return snap


@router.get("/api/jobs/{job_id}/ping", response_model=PingResponse)
async def ping(job_id: str, request: Request) -> PingResponse:
    """Lectura instantánea del log actual — no usa caché."""
    poller   = get_poller(request)
    job_dir  = poller.runs_dir / job_id
    if not job_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' no encontrado")

    data = ping_job(job_dir)
    return PingResponse(job_id=job_id, **data)


@router.get("/api/jobs/{job_id}/stats", response_model=StatsResponse)
async def get_stats(job_id: str, request: Request) -> StatsResponse:
    """Igual que GET /api/jobs/{job_id} pero fuerza re-parseo del disco."""
    from .poller import snapshot_job
    poller  = get_poller(request)
    job_dir = poller.runs_dir / job_id
    if not job_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' no encontrado")
    snap = snapshot_job(job_dir, poller.cfg)
    poller.snapshots[job_id] = snap
    return snap


@router.get("/api/summary", response_model=SummaryResponse)
async def summary(request: Request) -> SummaryResponse:
    poller = get_poller(request)
    snaps  = list(poller.snapshots.values())
    counts: dict[str, int] = {}
    for s in snaps:
        counts[s.status] = counts.get(s.status, 0) + 1

    n_conv = counts.get("converged", 0)
    n_fail = counts.get("failed", 0)
    rate   = round(n_conv / (n_conv + n_fail), 3) if (n_conv + n_fail) > 0 else None

    return SummaryResponse(
        n_pending=counts.get("pending", 0),
        n_running=counts.get("running", 0),
        n_converged=n_conv,
        n_failed=n_fail,
        n_stalled=counts.get("stalled", 0),
        n_oscillating=counts.get("oscillating", 0),
        total=len(snaps),
        convergence_rate=rate,
    )


class SysMetricsResponse(BaseModel):
    cpu_percent: float
    cpu_per_core: list[float]
    ram_used_gb: float
    ram_total_gb: float
    ram_percent: float
    pkg_temps: list[float]
    core_temp_max: float
    nvme_temp: float | None
    gpu_temps: list[float]


@router.get("/api/system", response_model=SysMetricsResponse)
async def system_metrics() -> SysMetricsResponse:
    """Temperaturas, uso de CPU y RAM en tiempo real."""
    m = collect_metrics()
    return SysMetricsResponse(**m.__dict__)


def _count_total_converged(poller: DFTPoller) -> int:
    """Cuenta convergidos en todos los batches históricos + relax_basic."""
    total = 0
    runs_root = Path(__file__).resolve().parents[2]  # …/dft

    def cfg_path(key: str, default: str) -> Path:
        p = Path(poller.cfg.get(key, default))
        return p if p.is_absolute() else runs_root / p

    for search_dir in [
        cfg_path("runs_dir", "runs/relax_basic"),
        cfg_path("batches_dir", "runs/batches"),
    ]:
        if not search_dir.exists():
            continue
        # relax_basic: hijos directos son job_dirs
        # batches: hijos son batch_NNN/, nietos son job_dirs
        depth1 = [d for d in search_dir.iterdir() if d.is_dir()]
        for d1 in depth1:
            s = d1 / "status.json"
            if s.exists():
                # job directo (relax_basic)
                try:
                    if json.loads(s.read_text()).get("status") == "converged":
                        total += 1
                except Exception:
                    pass
            else:
                # batch_NNN — iterar nietos
                for d2 in d1.iterdir():
                    if not d2.is_dir():
                        continue
                    s2 = d2 / "status.json"
                    try:
                        if s2.exists() and json.loads(s2.read_text()).get("status") == "converged":
                            total += 1
                    except Exception:
                        pass
    return total


def _build_status_report(poller: DFTPoller, metrics: SysMetrics) -> str:
    """Genera el texto HTML del reporte tipo STATUS para Telegram."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    snaps = list(poller.snapshots.values())

    counts: dict[str, int] = {}
    for s in snaps:
        counts[s.status] = counts.get(s.status, 0) + 1

    n_run  = counts.get("running",  0) + counts.get("stalled", 0) + counts.get("oscillating", 0)
    n_conv = counts.get("converged", 0)
    n_fail = counts.get("failed",   0) + counts.get("stopped", 0)
    n_pend = counts.get("pending",  0)

    batch_name = poller.runs_dir.name
    total_conv = _count_total_converged(poller)

    lines = [
        f"📊 <b>DFT Status</b> — {now}",
        f"📦 Batch: <code>{batch_name}</code>   🧮 Total simuladas: <b>{total_conv}</b>",
        "",
        fmt_sys(metrics),
        "",
        f"📋 <b>Jobs</b>: {n_run} corriendo | {n_conv} ✅ | {n_fail} ❌ | {n_pend} en cola",
    ]

    _ICON = {
        "running":     "🔄",
        "converged":   "✅",
        "failed":      "❌",
        "stopped":     "🔴",
        "stalled":     "⏸️",
        "oscillating": "⚠️",
        "pending":     "⏳",
        "unknown":     "❓",
    }

    # Activos: detalle completo
    active = [s for s in snaps if s.status in ("running", "oscillating", "stalled")]
    for s in sorted(active, key=lambda s: s.job_id):
        icon = _ICON.get(s.status, "❓")
        name = f"<code>{fmt_formula(s.formula or s.job_id)}</code>"
        parts = []
        if s.n_fire_steps:
            parts.append(f"FIRE {s.n_fire_steps}")
            if s.fmax_history:
                parts.append(f"fmax={s.fmax_history[-1]:.3f}")
        elif s.n_scf_iters:
            parts.append(f"SCF {s.n_scf_iters}")
        if s.energy_history:
            parts.append(f"E={s.energy_history[-1]:.3f} eV")
        if s.is_oscillating:
            parts.append("⚠️osc")
        if s.stall_minutes:
            parts.append(f"stall {s.stall_minutes:.0f}min")
        elapsed = f"  {s.elapsed_min:.0f}min" if s.elapsed_min else ""
        lines.append(f"{icon} {name}  {'  '.join(parts) or 'init'}{elapsed}")

    # Fallidos/detenidos: todos (suelen ser pocos)
    failed = [s for s in snaps if s.status in ("failed", "stopped")]
    for s in sorted(failed, key=lambda s: s.job_id):
        icon = _ICON.get(s.status, "❓")
        name = f"<code>{fmt_formula(s.formula or s.job_id)}</code>"
        t_str = f"  {s.elapsed_min:.0f}min" if s.elapsed_min else ""
        lines.append(f"{icon} {name}{t_str}")

    # Convergidos: solo los últimos 5
    converged = sorted(
        [s for s in snaps if s.status == "converged"],
        key=lambda s: s.elapsed_min or 0,
        reverse=True,
    )
    for s in converged[:5]:
        icon = _ICON["converged"]
        name = f"<code>{fmt_formula(s.formula or s.job_id)}</code>"
        e_str = f"  E={s.final_energy_ev:.3f} eV" if s.final_energy_ev else ""
        lines.append(f"{icon} {name}{e_str}")
    if len(converged) > 5:
        lines.append(f"  … +{len(converged)-5} más convergidos")

    return "\n".join(lines)


@router.get("/api/jobs/converged", response_model=list[JobStatus])
async def list_converged(request: Request, limit: int = 50) -> list[JobStatus]:
    """Lista los primeros N jobs convergidos ordenados por fórmula."""
    poller = get_poller(request)
    jobs = [
        JobStatus(
            job_id=s.job_id,
            formula=s.formula,
            status=s.status,
            pid=s.pid,
            start_time=s.start_time,
            elapsed_min=s.elapsed_min,
            mpi_cores=s.mpi_cores,
        )
        for s in poller.snapshots.values()
        if s.status == "converged"
    ]
    jobs.sort(key=lambda j: j.formula)
    return jobs[:limit]


def _build_converged_text(poller: DFTPoller, limit: int = 50) -> str:
    """Construye el texto HTML del listado de convergidos (reutilizable por el bot)."""
    converged = sorted(
        [s for s in poller.snapshots.values() if s.status == "converged"],
        key=lambda s: s.formula,
    )
    MAX_CHARS = 4000
    header = f"✅ <b>Convergidos</b> ({len(converged)} total)\n\n"
    lines: list[str] = []
    for s in converged[:limit]:
        e_str = f"  E={s.final_energy_ev:.3f} eV" if s.final_energy_ev else ""
        line = f"• <code>{fmt_formula(s.formula)}</code>{e_str}"
        if len(header + "\n".join(lines + [line])) > MAX_CHARS:
            lines.append(f"…(truncado, mostrados {len(lines)} de {len(converged)})")
            break
        lines.append(line)
    return header + "\n".join(lines)


@router.post("/api/notify/converged")
async def notify_converged(request: Request, limit: int = 50) -> dict:
    """Envía a Telegram los primeros N convergidos que quepan en 4096 chars."""
    from .notifier import send_telegram
    poller  = get_poller(request)
    app_cfg = request.app.state.config
    tg      = app_cfg.get("telegram", {})
    token   = tg.get("bot_token", "")
    chat_id = tg.get("chat_id", "")
    text    = _build_converged_text(poller, limit)
    ok      = await send_telegram(token, chat_id, "PING", "converged", {"_raw": text})
    total   = sum(1 for s in poller.snapshots.values() if s.status == "converged")
    shown   = text.count("•")
    return {"ok": ok, "shown": shown, "total": total}


@router.get("/api/status/report")
async def status_report(request: Request) -> dict:
    """Devuelve el reporte STATUS completo como texto."""
    poller  = get_poller(request)
    metrics = collect_metrics()
    text    = _build_status_report(poller, metrics)
    return {"report": text, "timestamp": datetime.now().isoformat()}


@router.post("/api/notify/status")
async def notify_status(request: Request) -> dict:
    """Envía reporte STATUS completo a Telegram ahora."""
    from .notifier import send_telegram
    poller   = get_poller(request)
    app_cfg  = request.app.state.config
    tg       = app_cfg.get("telegram", {})
    token    = tg.get("bot_token", "")
    chat_id  = tg.get("chat_id", "")
    metrics  = collect_metrics()
    text     = _build_status_report(poller, metrics)
    ok = await send_telegram(token, chat_id, "PING", "status-report", {"_raw": text})
    return {"ok": ok}


@router.post("/api/notify/test")
async def notify_test(request: Request) -> dict:
    from .notifier import send_test
    app_cfg  = request.app.state.config
    tg       = app_cfg.get("telegram", {})
    token    = tg.get("bot_token", "")
    chat_id  = tg.get("chat_id", "")
    ok       = await send_test(token, chat_id)
    return {"ok": ok, "message": "Mensaje enviado" if ok else "Fallo — revisa bot_token y chat_id"}


# ── WebSocket ─────────────────────────────────────────────────────────────────

@router.websocket("/ws/events")
async def ws_events(websocket: WebSocket) -> None:
    await websocket.accept()
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=128)
    _ws_clients.append(queue)
    log.info("WebSocket conectado desde %s", websocket.client)

    # Reenviar eventos del poller a todos los clientes
    poller: DFTPoller = websocket.app.state.poller

    async def _forward_from_poller():
        while True:
            event: WsEvent = await poller.event_queue.get()
            payload = event.model_dump_json()
            # broadcast a todos
            for q in list(_ws_clients):
                try:
                    q.put_nowait(payload)
                except asyncio.QueueFull:
                    pass

    forward_task = asyncio.create_task(_forward_from_poller())

    try:
        while True:
            # Enviar mensajes pendientes
            while not queue.empty():
                msg = queue.get_nowait()
                await websocket.send_text(msg)

            # Keepalive ping cada 15 s
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        log.info("WebSocket desconectado")
    finally:
        _ws_clients.remove(queue)
        forward_task.cancel()
