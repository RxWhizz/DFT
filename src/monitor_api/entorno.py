"""Carga de `.env` para los secretos del monitor.

Los secretos no deben vivir en `monitor.yaml`. Ese fichero se comparte, se
copia al directorio XDG durante la instalación y se edita a mano, así que es
justo el que acaba por accidente en un commit o dentro de un `.tar.gz`. El
`.env` está gitignorado, no viaja en los artefactos y es el sitio donde el
código espera encontrar las claves.

Precedencia: **lo que ya está en el entorno gana siempre**. El `.env` solo
rellena huecos. Así un `DFT_MONITOR_TOKEN=xxx buho monitor serve` puntual no se
ve pisado por un fichero olvidado de hace meses.
"""
from __future__ import annotations

import os
from pathlib import Path

from . import paths

#: Variable para apuntar a un `.env` concreto, saltándose la búsqueda.
VARIABLE_RUTA = "DFT_ENV_FILE"


def rutas_candidatas(data_root: Path | None = None) -> list[Path]:
    """Dónde se busca el `.env`, en orden de preferencia."""
    candidatas: list[Path] = []

    explicita = os.environ.get(VARIABLE_RUTA, "").strip()
    if explicita:
        candidatas.append(Path(explicita).expanduser())

    # Junto a la configuración: es el par natural de monitor.yaml, y en la app
    # congelada es el único directorio de escritura que el usuario conoce.
    try:
        candidatas.append(paths.config_dir() / ".env")
    except Exception:
        pass

    raiz = data_root
    if raiz is None:
        try:
            raiz = paths.data_root()
        except Exception:
            raiz = None
    if raiz is not None:
        candidatas.append(Path(raiz) / ".env")

    candidatas.append(Path.cwd() / ".env")

    vistas: set[Path] = set()
    unicas: list[Path] = []
    for c in candidatas:
        if c not in vistas:
            vistas.add(c)
            unicas.append(c)
    return unicas


def cargar(data_root: Path | None = None) -> Path | None:
    """Carga el primer `.env` que exista. Devuelve cuál, o None si no hay.

    Sin `python-dotenv` instalado no falla: se limita a no cargar nada, porque
    las variables de entorno de verdad siguen funcionando y el monitor tiene
    que poder arrancar igual.
    """
    for ruta in rutas_candidatas(data_root):
        if not ruta.is_file():
            continue
        try:
            from dotenv import load_dotenv
        except ImportError:
            return None
        # override=False: el entorno real manda sobre el fichero.
        load_dotenv(ruta, override=False)
        return ruta
    return None
