"""Localización de los datasets PAW de GPAW.

Los runners llevaban la ruta escrita a mano:

    ROOT / ".venv/lib/python3.12/site-packages/gpaw_data/setups"

Ese directorio dejó de existir y **todos** los jobs empezaron a morir nada más
arrancar con `Could not find required PAW dataset file "Cs.PBE"` — 48/48 en
batch_248771, 48/48 en batch_836602, 23/55 en batch_181544. Como el fallo es de
cada job y no del runner, el lote entero se consumía sin que nada avisara.

Una sola ruta escrita a mano en siete archivos era el problema de fondo: aquí se
resuelve una vez, comprobando que el dataset esté de verdad y no solo que el
directorio exista.
"""
from __future__ import annotations

import glob
import os
from pathlib import Path

# Elemento presente en todo lo que calcula BUHO: si falta, la ruta no sirve.
MARCADOR = "Cs.PBE.gz"


def candidatos(repo_root: Path | None = None) -> list[str]:
    """Ubicaciones a probar, de más específica a más general."""
    rutas: list[str] = []
    if os.environ.get("GPAW_SETUP_PATH"):
        rutas.append(os.environ["GPAW_SETUP_PATH"])
    if repo_root is not None:
        rutas.append(str(repo_root / ".venv" / "lib" / "python3.12"
                         / "site-packages" / "gpaw_data" / "setups"))
    # Más reciente primero: gpaw-setups-24.11.0 antes que 24.1.0.
    rutas.extend(sorted(glob.glob(str(Path.home() / ".gpaw" / "gpaw-setups-*")),
                        reverse=True))
    if os.environ.get("CONDA_PREFIX"):
        rutas.append(str(Path(os.environ["CONDA_PREFIX"]) / "share" / "gpaw-setups"))
    rutas.append("/usr/share/gpaw-setups")
    return [r for r in rutas if r]


def find(repo_root: Path | None = None) -> str | None:
    """Primera ruta que contenga los datasets, o None."""
    for ruta in candidatos(repo_root):
        if (Path(ruta) / MARCADOR).is_file():
            return ruta
    return None


def resolve(repo_root: Path | None = None) -> str:
    """Como `find`, pero aborta con instrucciones si no hay ninguna.

    Fallar aquí cuesta un mensaje; no fallar cuesta un lote entero.
    """
    ruta = find(repo_root)
    if ruta:
        return ruta
    raise SystemExit(
        "No se encuentran los datasets PAW de GPAW.\n"
        f"Se buscó {MARCADOR} en:\n"
        + "\n".join(f"  {c}" for c in candidatos(repo_root))
        + "\n\nSin ellos TODOS los jobs fallan nada más arrancar. Instálalos con\n"
          "  gpaw install-data ~/.gpaw\n"
          "o exporta GPAW_SETUP_PATH al directorio donde estén."
    )
