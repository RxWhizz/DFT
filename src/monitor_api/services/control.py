"""Acciones de control sobre jobs y batches.

Todo lo de aquí es destructivo o lanza procesos, así que:

* solo se actúa sobre jobs en un estado que lo admita;
* el PID de `status.json` se **verifica** antes de usarlo (ver
  `_pid_verificado`): puede llevar meses escrito y haberse reciclado, y
  `_kill_job_processes()` mata el grupo de procesos entero del PID que se le
  pase;
* el trabajo bloqueante va a un hilo, porque `_kill_job_processes()` duerme
  3 s entre SIGTERM y SIGKILL y colgaría el event loop.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil

from .. import paths

log = logging.getLogger(__name__)

# Estados sobre los que tiene sentido cada acción.
ESTADOS_MATABLES = {"running", "stalled", "oscillating", "pending"}
ESTADOS_REINTENTABLES = {"failed", "stopped", "stalled", "oscillating", "partial"}

_BATCH_RE = re.compile(r"^batch_(\d+)$")


class ControlError(RuntimeError):
    """La acción no se puede aplicar en el estado actual del job."""


def _leer_status(job_dir: Path) -> dict[str, Any]:
    try:
        return json.loads((job_dir / "status.json").read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _escribir_status(job_dir: Path, data: dict[str, Any]) -> None:
    tmp = job_dir / "status.json.tmp"
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    tmp.replace(job_dir / "status.json")


def _pid_verificado(job_dir: Path, pid: Any) -> int | None:
    """Devuelve el PID solo si sigue vivo y trabajando en este job.

    `status.json` conserva el PID de la última ejecución aunque haya terminado
    hace meses. En Linux los PID se reciclan, así que pasar ese número a
    `_kill_job_processes()` puede matar el grupo de procesos de algo ajeno.
    """
    if not isinstance(pid, int) or pid <= 0:
        return None
    try:
        cwd = psutil.Process(pid).cwd()
    except (psutil.Error, OSError, ValueError):
        return None  # no existe, no es nuestro, o no se puede inspeccionar

    raiz = str(job_dir.resolve())
    return pid if cwd and (cwd == raiz or cwd.startswith(raiz + os.sep)) else None


async def kill_job(job_dir: Path) -> dict[str, Any]:
    """Termina los procesos del job. Devuelve los PID afectados."""
    from ..poller import _kill_job_processes

    status = _leer_status(job_dir)
    estado = status.get("status")
    if estado not in ESTADOS_MATABLES:
        raise ControlError(
            f"El job está en estado '{estado}'; solo se puede detener uno en "
            f"{sorted(ESTADOS_MATABLES)}."
        )

    root_pid = _pid_verificado(job_dir, status.get("pid"))
    if status.get("pid") and root_pid is None:
        log.warning(
            "PID %s de %s no corresponde a este job (terminado o reciclado); "
            "se matan solo los procesos cuyo cwd cuelga del directorio.",
            status.get("pid"),
            job_dir.name,
        )

    pids = await asyncio.to_thread(_kill_job_processes, job_dir, root_pid)

    status["status"] = "stopped"
    status["stopped_at"] = datetime.now(timezone.utc).isoformat()
    status["stopped_by"] = "monitor-api"
    status.pop("pid", None)
    _escribir_status(job_dir, status)

    return {"job_id": job_dir.name, "killed_pids": pids, "status": "stopped"}


def retry_job(job_dir: Path) -> dict[str, Any]:
    """Devuelve el job a la cola para que el runner lo recoja."""
    status = _leer_status(job_dir)
    estado = status.get("status")
    if estado not in ESTADOS_REINTENTABLES:
        raise ControlError(
            f"El job está en estado '{estado}'; solo se puede reintentar uno en "
            f"{sorted(ESTADOS_REINTENTABLES)}."
        )

    for clave in ("pid", "started_at", "finished_at", "stopped_at", "stopped_by", "error"):
        status.pop(clave, None)
    status["status"] = "pending"
    status["requeued_at"] = datetime.now(timezone.utc).isoformat()
    status["requeue_count"] = int(status.get("requeue_count", 0)) + 1
    _escribir_status(job_dir, status)

    return {"job_id": job_dir.name, "status": "pending", "requeue_count": status["requeue_count"]}


# ── Batches ──────────────────────────────────────────────────────────────────

def _raiz_batches(poller) -> Path:
    """Directorio que contiene los batch_NNN."""
    # Se comprueba la cadena de config, no el Path: Path("") es Path("."), que
    # es truthy y apuntaría a la raíz del repo.
    configurada = poller.cfg.get("phase2_runs_dir") or poller.cfg.get("batches_dir") or ""
    if configurada:
        raiz = paths.resolve_data(configurada)
        if raiz.is_dir():
            return raiz

    # Si runs_dir ya es un batch_NNN, los hermanos son los demás batches.
    return poller.runs_dir.parent if _BATCH_RE.match(poller.runs_dir.name) else poller.runs_dir


def list_batches(poller) -> dict[str, Any]:
    raiz = _raiz_batches(poller)
    batches = []
    if raiz.is_dir():
        for d in sorted(raiz.iterdir()):
            if not (d.is_dir() and _BATCH_RE.match(d.name)):
                continue
            conteo: dict[str, int] = {}
            tiempos: list[float] = []
            for st in d.glob("*/status.json"):
                try:
                    data = json.loads(st.read_text())
                except (OSError, json.JSONDecodeError):
                    continue
                estado = str(data.get("status", "unknown"))
                conteo[estado] = conteo.get(estado, 0) + 1
                if estado == "converged":
                    xyz = st.parent / "pbe" / "label.extxyz"
                    if xyz.exists():
                        tiempos.append(xyz.stat().st_mtime)

            batches.append(
                {
                    "batch_id": int(_BATCH_RE.match(d.name).group(1)),
                    "name": d.name,
                    "path": str(d),
                    "counts": conteo,
                    "total": sum(conteo.values()),
                    "is_current": d.resolve() == poller.runs_dir.resolve(),
                    "runner_launched": (d / ".runner_launched").exists(),
                    **_ritmo(tiempos, conteo),
                }
            )
    return {"items": batches, "root": str(raiz), "runner_kind": poller.cfg.get("runner_kind", "relax")}


def _ritmo(tiempos: list[float], conteo: dict[str, int]) -> dict[str, Any]:
    """Throughput y ETA a partir de los mtime de las etiquetas convergidas."""
    pendientes = conteo.get("pending", 0) + conteo.get("running", 0)
    if len(tiempos) < 2:
        return {"rate_per_hour": None, "eta_sec": None, "n_pending": pendientes}

    tiempos.sort()
    recientes = tiempos[-8:]
    ventana_h = (recientes[-1] - recientes[0]) / 3600.0
    if ventana_h <= 0:
        return {"rate_per_hour": None, "eta_sec": None, "n_pending": pendientes}

    ritmo = (len(recientes) - 1) / ventana_h
    return {
        "rate_per_hour": round(ritmo, 2),
        "eta_sec": round(pendientes / ritmo * 3600) if ritmo > 0 and pendientes else None,
        "n_pending": pendientes,
    }


def start_batch(poller, batch_id: int) -> dict[str, Any]:
    """Lanza el runner configurado para un batch, si no hay ya uno vivo."""
    raiz = _raiz_batches(poller)
    batch_dir = raiz / f"batch_{batch_id:03d}"
    if not batch_dir.is_dir():
        raise FileNotFoundError(f"batch_{batch_id:03d}")

    if poller._runner_running_for(batch_dir):
        raise ControlError(f"Ya hay un runner activo para batch_{batch_id:03d}.")

    poller._launch_runner(batch_dir)
    return {
        "batch_id": batch_id,
        "launched": True,
        "runner_kind": poller.cfg.get("runner_kind", "relax"),
        "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
