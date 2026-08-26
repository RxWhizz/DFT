"""Qué puede hacer el monitor en la máquina donde corre.

En vez de suponer capacidades a partir del sistema operativo, se comprueban.
El frontend lee esto de `GET /api/health` y esconde lo que no está disponible,
en lugar de ofrecer acciones que van a fallar.
"""
from __future__ import annotations

import logging
import shutil
import sys
from pathlib import Path

import psutil

from . import paths

log = logging.getLogger(__name__)

# Nombres de intérprete a buscar cuando el nuestro no sirve.
_CANDIDATOS_PYTHON = ("python3", "python")


def hardware_temps_available() -> bool:
    """Windows no implementa `sensors_temperatures` en psutil."""
    return hasattr(psutil, "sensors_temperatures")


def runner_python(cfg: dict | None = None) -> str | None:
    """Intérprete con el que lanzar los runners del pipeline.

    Congelado, `sys.executable` **es el propio binario**: lanzarlo arrancaría
    otro monitor en vez del runner. Por eso se busca un Python de verdad.
    """
    declarado = (cfg or {}).get("python_executable")
    if declarado:
        return declarado if Path(declarado).is_file() else None

    if not paths.is_frozen():
        return sys.executable

    for nombre in _CANDIDATOS_PYTHON:
        ruta = shutil.which(nombre)
        if ruta:
            return ruta
    return None


def runner_launch_available(cfg: dict | None = None) -> bool:
    """Hace falta un intérprete y los scripts del pipeline en la raíz de datos."""
    if runner_python(cfg) is None:
        return False
    return (paths.data_root() / "scripts").is_dir()


def describe(cfg: dict | None = None) -> dict[str, object]:
    """Capacidades efectivas, para `GET /api/health`."""
    interprete = runner_python(cfg)
    return {
        "os": sys.platform,
        "frozen": paths.is_frozen(),
        "hardware_temps": hardware_temps_available(),
        "runner_launch": runner_launch_available(cfg),
        "runner_python": interprete,
        # Un monitor que puede reentrenar y generar lotes por su cuenta tiene
        # que decirlo: no debería ser una sorpresa al abrir la pestaña.
        "auto_advance": bool((cfg or {}).get("auto_advance", True)),
    }
