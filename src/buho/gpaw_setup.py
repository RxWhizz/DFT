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

import os
import site
import sys
from pathlib import Path

# Elemento presente en todo lo que calcula BUHO: si falta, la ruta no sirve.
MARCADOR = "Cs.PBE.gz"


def candidatos(repo_root: Path | None = None) -> list[str]:
    """Ubicaciones a probar, de más específica a más general."""
    rutas: list[str] = []
    for env_name in ("BUHO_GPAW_SETUP_PATH", "GPAW_SETUP_PATH"):
        if os.environ.get(env_name):
            rutas.append(os.environ[env_name])
    if repo_root is not None:
        root = Path(repo_root)
        rutas.extend(str(p) for p in root.glob(".venv*/lib/python*/site-packages/gpaw_data/setups"))
        rutas.extend(str(p) for p in root.glob(".venv*/Lib/site-packages/gpaw_data/setups"))
        rutas.append(str(root / "gpaw-setups"))
        rutas.append(str(root / "data" / "gpaw-setups"))
    rutas.extend(str(Path(p) / "gpaw_data" / "setups") for p in _site_package_dirs())
    # Más reciente primero: gpaw-setups-24.11.0 antes que 24.1.0.
    rutas.extend(str(p) for p in sorted((Path.home() / ".gpaw").glob("gpaw-setups-*"), reverse=True))
    if os.environ.get("CONDA_PREFIX"):
        conda_prefix = Path(os.environ["CONDA_PREFIX"])
        rutas.append(str(conda_prefix / "share" / "gpaw-setups"))
        rutas.extend(str(p) for p in conda_prefix.glob("lib/python*/site-packages/gpaw_data/setups"))
        rutas.extend(str(p) for p in conda_prefix.glob("Lib/site-packages/gpaw_data/setups"))
    rutas.append("/usr/share/gpaw-setups")
    return _dedupe(rutas)


def _site_package_dirs() -> list[str]:
    dirs = [sys.prefix, sys.base_prefix]
    try:
        dirs.extend(site.getsitepackages())
    except Exception:
        pass
    try:
        dirs.append(site.getusersitepackages())
    except Exception:
        pass

    out: list[str] = []
    for item in dirs:
        if not item:
            continue
        path = Path(item)
        if path.name == "site-packages":
            out.append(str(path))
        else:
            out.extend(str(p) for p in path.glob("lib/python*/site-packages"))
            out.extend(str(p) for p in path.glob("Lib/site-packages"))
    return _dedupe(out)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if not item:
            continue
        key = str(Path(item).expanduser())
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


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
