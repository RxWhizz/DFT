"""Wizard de entorno para el monitor.

Expone `buho.setup_wizard` por HTTP: la GUI enseña qué falta y lanza la
instalación sin que nadie tenga que abrir una terminal ni saber si el paquete
va a Windows o a WSL.

La instalación corre en un hilo con el log en memoria, no como subproceso
desacoplado (que es lo que hace `bench`): un `pip install` dura minutos y el
usuario lo está mirando, así que lo que importa es transmitir la salida, no
sobrevivir al cierre de la app.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any

import yaml

from .. import paths

log = logging.getLogger(__name__)

#: Cuántas líneas de salida se guardan. pip es verboso y la GUI solo enseña
#: la cola; retener el log entero de un torch sería decenas de MB por instalación.
MAX_LINEAS = 2000

_lock = threading.Lock()
_thread: threading.Thread | None = None
_job: dict[str, Any] = {}
_log: deque[str] = deque(maxlen=MAX_LINEAS)


def _config() -> dict[str, Any]:
    ruta = paths.resolve_data("config/generator.yaml")
    if not ruta.is_file():
        ruta = paths.bundle_file("config", "generator.yaml")
    try:
        with ruta.open(encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except OSError:
        return {}


def _corriendo() -> bool:
    return _thread is not None and _thread.is_alive()


def status(*, fast: bool = False) -> dict[str, Any]:
    """Matriz de capacidades, más el estado del trabajo en curso."""
    from buho import setup_wizard

    data = setup_wizard.check(_config(), project_root=paths.data_root(), incluir_mlff=not fast)
    data["job"] = job()
    return data


def job() -> dict[str, Any]:
    """Estado del trabajo de instalación, con la cola del log."""
    with _lock:
        actual = dict(_job)
        actual["running"] = _corriendo()
        actual["log"] = list(_log)
    return actual


def plan(target: str, **opciones: Any) -> dict[str, Any]:
    from buho import setup_wizard

    return setup_wizard.plan(target, config=_config(), **opciones).as_dict()


def start_install(target: str, **opciones: Any) -> dict[str, Any]:
    """Lanza el plan en segundo plano. Devuelve el estado inicial del trabajo."""
    from buho import setup_wizard

    global _thread

    with _lock:
        if _corriendo():
            raise RuntimeError("Ya hay una instalación en curso.")

        # Instalar mientras el protocolo criba dejaría a la cascada importando
        # un entorno a medio escribir. Es exactamente el fallo que este wizard
        # existe para evitar, así que no se permite provocarlo desde aquí.
        try:
            from . import discovery as discovery_service

            if discovery_service.status().get("background", {}).get("running"):
                raise RuntimeError(
                    "Pausa el protocolo de descubrimiento antes de instalar dependencias."
                )
        except ImportError:
            pass

        plan_obj = setup_wizard.plan(target, config=_config(), **opciones)
        if not plan_obj.steps:
            return {"status": "skipped", "target": target, "notas": plan_obj.notas,
                    "running": False, "log": []}

        _log.clear()
        _job.clear()
        _job.update({
            "target": target,
            "status": "running",
            "started_at": time.time(),
            "finished_at": None,
            "error": None,
            "plan": plan_obj.as_dict(),
        })

        def _emit(linea: str) -> None:
            with _lock:
                _log.append(linea)

        def _target_fn() -> None:
            try:
                resultado = setup_wizard.execute(plan_obj, on_output=_emit)
            except Exception as exc:  # noqa: BLE001 - un hilo no puede morir mudo
                log.exception("Instalación '%s' falló", target)
                resultado = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
            with _lock:
                _job["status"] = resultado.get("status", "error")
                _job["error"] = resultado.get("error")
                _job["steps"] = resultado.get("steps", [])
                _job["finished_at"] = time.time()

        _thread = threading.Thread(target=_target_fn, name=f"perovowl-setup-{target}",
                                   daemon=True)
        _thread.start()

    return job()


def reset_for_tests() -> None:
    global _thread
    with _lock:
        _thread = None
        _job.clear()
        _log.clear()
