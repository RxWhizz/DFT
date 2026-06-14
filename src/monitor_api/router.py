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


def _scf_rate_s(points: list[dict]) -> float | None:
    """Average seconds/iter from the last few SCF iterations."""
    if len(points) < 2:
        return None

    def _secs(clock: str) -> int:
        h, m, s = (int(x) for x in clock.split(":"))
        return h * 3600 + m * 60 + s

    deltas = []
    for prev, cur in zip(points[-6:-1], points[-5:]):
        try:
            d = _secs(cur["clock"]) - _secs(prev["clock"])
            if d < 0:
                d += 86400
            if 0 < d < 3600:
                deltas.append(d)
        except (KeyError, ValueError):
            pass
    return (sum(deltas) / len(deltas)) if deltas else None


_PHASE2_N_CONFIGS = 4
_SCF_TYPICAL_ITERS = 15


def _batch_eta(runs_dir: Path, n_recent: int = 8) -> tuple[float | None, int, int]:
    """Throughput-based ETA for the current batch.

    Returns (rate_per_hour, n_pending, n_running).
    Uses pbe/label.extxyz mtime as convergence timestamp (reliable proxy).
    """
    conv_times: list[float] = []
    n_pending = n_running = 0
    for st_path in runs_dir.glob("*/status.json"):
        try:
            d = json.loads(st_path.read_text())
        except Exception:
            continue
        s = d.get("status")
        if s == "converged":
            xyz = st_path.parent / "pbe" / "label.extxyz"
            if xyz.exists():
                conv_times.append(xyz.stat().st_mtime)
        elif s == "pending":
            n_pending += 1
        elif s == "running":
            n_running += 1

    if len(conv_times) < 2:
        return None, n_pending, n_running

    conv_times.sort()
    recent = conv_times[-n_recent:]
    window_h = (recent[-1] - recent[0]) / 3600.0
    rate = (len(recent) - 1) / window_h if window_h > 0 else None
    return rate, n_pending, n_running


def _build_statusfull_report(poller: DFTPoller, metrics: SysMetrics) -> list[str]:
    """Per-SCF-iteration detail for running Phase 2A jobs (/statusfull command)."""
    from buho.phase2_force.self_heal import parse_scf_points

    now = datetime.now().strftime("%H:%M")
    batch_name = poller.runs_dir.name
    active = [
        s for s in poller.snapshots.values()
        if s.status in ("running", "stalled", "oscillating")
    ]

    if not active:
        counts: dict[str, int] = {}
        for s in poller.snapshots.values():
            counts[s.status] = counts.get(s.status, 0) + 1
        summary = "  ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        rate, n_pend, _ = _batch_eta(poller.runs_dir)
        if rate and n_pend > 0:
            eta_h = n_pend / rate
            eta_str = f"ETA ~{eta_h*60:.0f}min" if eta_h < 1 else f"ETA ~{eta_h:.1f}h"
            rate_line = f"📈 {rate:.1f} jobs/h · {eta_str} ({n_pend} pendientes)"
        else:
            rate_line = f"📈 {n_pend} pendientes (runner pausado)"
        return [
            f"🔬 <b>Status full</b> — {now} | <code>{batch_name}</code>\n"
            f"Sin jobs activos  ({summary})\n"
            f"{rate_line}\n"
            f"{fmt_sys(metrics)}"
        ]

    ram_free = metrics.ram_total_gb - metrics.ram_used_gb
    rate, n_pend, n_run = _batch_eta(poller.runs_dir)
    n_conv = sum(1 for s in poller.snapshots.values() if s.status == "converged")
    n_total = len(poller.snapshots)
    if rate and (n_pend + n_run) > 0:
        eta_h = (n_pend + n_run) / rate
        if eta_h < 1:
            eta_str = f"ETA ~{eta_h*60:.0f}min"
        else:
            eta_str = f"ETA ~{eta_h:.1f}h"
        rate_str = f"{rate:.1f} jobs/h · {eta_str}"
    else:
        rate_str = "calculando tasa…"
    header = (
        f"🔬 <b>Status full</b> — {now} | <code>{batch_name}</code> | "
        f"{len(active)} activos | {n_conv}/{n_total} conv\n"
        f"📈 {rate_str} | RAM {ram_free:.0f} GB libre\n"
        f"{fmt_sys(metrics)}"
    )

    MAX_MSG = 4000
    messages: list[str] = []
    current_parts: list[str] = [header]
    current_len = len(header)

    for s in sorted(active, key=lambda x: x.job_id):
        job_dir = poller.runs_dir / s.job_id
        pbe_dir = job_dir / "pbe"

        n_done = 0
        frame_energies: list[str] = []
        for k in range(_PHASE2_N_CONFIGS):
            fj = pbe_dir / f"frame_{k}.json"
            if fj.exists():
                try:
                    fdata = json.loads(fj.read_text())
                    if fdata.get("status") == "ok":
                        e = fdata.get("energy_ev")
                        e_str = f"E={e:.4f}" if e is not None else "ok"
                        frame_energies.append(f"cfg{k}:{e_str}")
                        n_done += 1
                except Exception:
                    pass

        current_config = n_done
        config_label = f"config {current_config + 1}/{_PHASE2_N_CONFIGS}"

        log_path = pbe_dir / "r2scan.txt"
        points: list[dict] = []
        if log_path.exists():
            try:
                points = parse_scf_points(log_path)
            except Exception:
                pass

        formula = s.formula or s.job_id[:8]
        job_id_short = s.job_id[:8]
        elapsed = f"{s.elapsed_min:.1f} min" if s.elapsed_min else "?"

        job_lines = [
            f"\n🚀 <b>{fmt_formula(formula)}</b> (<code>{job_id_short}</code>) — "
            f"{config_label} · {elapsed}"
        ]

        if frame_energies:
            job_lines.append("  frames: " + "  ".join(frame_energies))

        if points:
            skip = len(points) - 12
            if skip > 0:
                job_lines.append(f"  … ({skip} iters previas)")
            for pt in points[-12:]:
                it = pt.get("iter", "?")
                clock = pt.get("clock", "?")
                e = pt.get("energy")
                e_str = f"E={e:.4f}" if e is not None else ""
                dens = pt.get("dens", "")
                job_lines.append(f"  iter {it:>3}  {clock}  {e_str}  dens={dens}")

            rate = _scf_rate_s(points)
            if rate is not None:
                last_iter = points[-1].get("iter") or 0
                remaining = max(0, _SCF_TYPICAL_ITERS - last_iter)
                eta_s = int(rate * remaining)
                eta_str = f"{eta_s // 60}min {eta_s % 60}s" if eta_s >= 60 else f"{eta_s}s"
                job_lines.append(f"  ritmo {rate:.0f} s/iter · ETA config ~{eta_str}")
        else:
            job_lines.append("  (sin iters SCF aún — inicializando)")

        block = "\n".join(job_lines)
        if current_len + len(block) > MAX_MSG:
            messages.append("\n".join(current_parts))
            current_parts = [block]
            current_len = len(block)
        else:
            current_parts.append(block)
            current_len += len(block)

    if current_parts:
        messages.append("\n".join(current_parts))

    return messages


@router.get("/api/statusfull")
async def statusfull_report(request: Request) -> dict:
    """Devuelve el reporte statusfull (detalle SCF por job activo) como lista de mensajes."""
    poller  = get_poller(request)
    metrics = collect_metrics()
    msgs    = _build_statusfull_report(poller, metrics)
    return {"messages": msgs, "count": len(msgs), "timestamp": datetime.now().isoformat()}


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
