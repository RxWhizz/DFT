"""Candidatos ABX3 del generador BUHO.

Dos orígenes, en este orden:

1. El CSV del generador (`data/processed/top500_candidates.csv`), cuando existe.
2. Los `metadata.json` de los jobs, que llevan la `selection_row` completa.

El fallback importa: `data/processed/` está en .gitignore y vive en el volumen
externo, así que sin él la vista quedaría vacía aunque haya cientos de
candidatos perfectamente legibles en los directorios de runs.
"""
from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any

from .. import paths

log = logging.getLogger(__name__)



def csv_candidatos() -> Path:
    """CSV del generador. Está en .gitignore y vive en la raíz de datos."""
    return paths.resolve_data("data/processed/top500_candidates.csv")

# Cotas de aceptación de config/generator.yaml, para dibujar las zonas válidas.
FILTROS = {
    "goldschmidt": {"min": 0.80, "max": 1.10},
    "octahedral": {"min": 0.40, "max": 0.90},
}


def _num(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # descarta NaN


def _from_csv(path: Path) -> list[dict[str, Any]]:
    filas = []
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            filas.append(
                {
                    "candidate_id": row.get("candidate_id") or row.get("id"),
                    "formula": row.get("formula"),
                    "generation_mode": row.get("generation_mode"),
                    "tolerance_t": _num(row.get("tolerance_t")),
                    "oct_factor": _num(row.get("oct_factor")),
                    "vol_est_A3": _num(row.get("vol_est_A3")),
                    "score": _num(row.get("pre_dft_score") or row.get("selection_score")),
                    "b_family": row.get("b_family"),
                    "dominant_halide": row.get("dominant_halide"),
                    "has_dft": False,
                }
            )
    return filas


def _from_jobs(runs_dir: Path) -> list[dict[str, Any]]:
    """Reconstruye los candidatos desde los metadata.json de los jobs."""
    filas = []
    for meta_path in sorted(runs_dir.glob("*/metadata.json")):
        try:
            md = json.loads(meta_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        sel = md.get("selection_row") or {}
        estado = None
        try:
            estado = json.loads((meta_path.parent / "status.json").read_text()).get("status")
        except (OSError, json.JSONDecodeError):
            pass

        filas.append(
            {
                "candidate_id": md.get("candidate_id") or meta_path.parent.name,
                "formula": md.get("formula"),
                "generation_mode": md.get("generation_mode"),
                "tolerance_t": _num(md.get("tolerance_t")),
                "oct_factor": _num(md.get("oct_factor")),
                "vol_est_A3": _num(sel.get("vol_est_A3")),
                "score": _num(sel.get("pre_dft_score") or sel.get("selection_score")),
                "b_family": sel.get("b_family"),
                "dominant_halide": sel.get("dominant_halide"),
                "n_atoms": md.get("n_atoms"),
                "lattice_constant_A": _num(md.get("lattice_constant_A")),
                "has_dft": True,
                "dft_status": estado,
            }
        )
    return filas


def _relativo(path: Path) -> str:
    """Ruta legible respecto a la raíz de datos, o absoluta si cae fuera."""
    try:
        return str(path.relative_to(paths.data_root()))
    except ValueError:
        return str(path)


import re as _re

_BATCH_DIR_RE = _re.compile(r"^batch_\d+$")


def load_candidates(runs_dir: Path) -> tuple[list[dict[str, Any]], str]:
    """Devuelve (candidatos, origen)."""
    csv_path = csv_candidatos()
    if csv_path.is_file():
        try:
            return _from_csv(csv_path), _relativo(csv_path)
        except OSError as exc:
            log.warning("No se pudo leer %s: %s", csv_path, exc)

    if runs_dir.is_dir():
        return _from_jobs(runs_dir), f"metadata.json de {runs_dir.name}"

    return [], "sin datos"


_ORDENES = {
    "score": lambda c: c.get("score") if c.get("score") is not None else -1e9,
    "formula": lambda c: (c.get("formula") or "").lower(),
    "tolerance_t": lambda c: c.get("tolerance_t") if c.get("tolerance_t") is not None else -1e9,
    "oct_factor": lambda c: c.get("oct_factor") if c.get("oct_factor") is not None else -1e9,
}


def query_candidates(
    runs_dir: Path,
    *,
    solo_verificados: bool = True,
    umbral_pv: float = 0.5,
    q: str | None = None,
    generation_mode: str | None = None,
    b_family: str | None = None,
    halide: str | None = None,
    sort: str = "score",
    desc: bool = True,
    limit: int = 500,
    offset: int = 0,
) -> dict[str, Any]:
    if solo_verificados:
        # Los lotes son hermanos de `runs_dir` cuando este es un batch_NNN.
        raiz = runs_dir.parent if _BATCH_DIR_RE.match(runs_dir.name) else runs_dir
        filas, origen = candidatos_verificados(raiz, umbral_pv)
        if not filas:
            # Sin nada verificado todavía, es preferible enseñar el listado
            # completo a dejar la vista vacía sin explicación.
            filas, origen_crudo = load_candidates(runs_dir)
            origen = f"{origen}; se muestran los del generador ({origen_crudo})"
    else:
        filas, origen = load_candidates(runs_dir)

    if q:
        needle = q.lower()
        filas = [c for c in filas if needle in (c.get("formula") or "").lower()]
    if generation_mode:
        modos = {m.strip() for m in generation_mode.split(",") if m.strip()}
        filas = [c for c in filas if c.get("generation_mode") in modos]
    if b_family:
        familias = {f.strip() for f in b_family.split(",") if f.strip()}
        filas = [c for c in filas if c.get("b_family") in familias]
    if halide:
        halogenos = {h.strip() for h in halide.split(",") if h.strip()}
        filas = [c for c in filas if c.get("dominant_halide") in halogenos]

    filas.sort(key=_ORDENES.get(sort, _ORDENES["score"]), reverse=desc)

    return {
        "items": filas[offset : offset + limit],
        "total": len(filas),
        "limit": limit,
        "offset": offset,
        "source": origen,
        "filters": FILTROS,
        "facets": _facetas(filas),
    }


def _facetas(filas: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Valores presentes en cada dimensión, para poblar los filtros de la GUI."""
    def unicos(clave: str) -> list[str]:
        return sorted({str(c[clave]) for c in filas if c.get(clave)})

    return {
        "generation_mode": unicos("generation_mode"),
        "b_family": unicos("b_family"),
        "dominant_halide": unicos("dominant_halide"),
    }


# ── Candidatos verificados por DFT ───────────────────────────────────────────
#
# La vista listaba los `metadata.json` de un único `runs_dir`, fijado al
# arrancar el motor: enseñaba siempre el mismo lote, sin importar cuántos se
# hubieran corrido después. Y mezclaba lo prometedor con lo descartado.
#
# Aquí se recorren todos los lotes y solo sobrevive lo que cumple las tres
# condiciones: pasó los tiers del cribado, terminó en DFT, y su bandgap cae
# cerca de la ventana fotovoltaica.

_VERIF_CACHE: dict[str, Any] = {"t": 0.0, "clave": None, "valor": None}
_VERIF_TTL = 60.0     # leer cientos de logs y predecir no es gratis

_PV_CENTRO = 1.45
_PV_SIGMA = 0.35


def _band_score(eg: float) -> float:
    """Proximidad a la ventana fotovoltaica.

    Misma gaussiana que `buho.screening.cascade._band_score`: si allí cambia el
    criterio, este listado debe seguirlo en vez de tener el suyo propio.
    """
    import math

    return math.exp(-0.5 * ((eg - _PV_CENTRO) / _PV_SIGMA) ** 2)


def _familia_b(fracciones: dict) -> str | None:
    """Especie del sitio B, o «mixed» si hay más de una.

    Los jobs preparados desde el cribado no llevan `selection_row`, así que
    estos dos campos —de los que dependen las facetas y los filtros de la
    vista— se derivan de la composición en vez de quedarse vacíos.
    """
    b = fracciones.get("B") or {}
    if not b:
        return None
    return next(iter(b)) if len(b) == 1 else "mixed"


def _haluro_dominante(fracciones: dict) -> str | None:
    """El haluro con mayor fracción."""
    x = fracciones.get("X") or {}
    if not x:
        return None
    return max(x.items(), key=lambda kv: kv[1])[0]


def candidatos_verificados(raiz_batches: Path,
                           umbral_pv: float = 0.5) -> tuple[list[dict[str, Any]], str]:
    """Candidatos viables, con DFT terminado y buen score fotovoltaico.

    `umbral_pv` recorta por `band_score`: 0.5 equivale a un bandgap dentro de
    ±0.41 eV del centro de la ventana.
    """
    import time as _t

    ahora = _t.time()
    clave = f"{raiz_batches}|{umbral_pv}"
    if (_VERIF_CACHE["clave"] == clave
            and ahora - _VERIF_CACHE["t"] < _VERIF_TTL
            and _VERIF_CACHE["valor"] is not None):
        return _VERIF_CACHE["valor"]

    from .ml import _gap_dft

    crudos: list[dict[str, Any]] = []
    feats: list[dict[str, Any]] = []

    for meta_path in sorted(raiz_batches.glob("batch_*/*/metadata.json")):
        job = meta_path.parent
        try:
            md = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        # 1. Viable: pasó los tiers del cribado.
        if not md.get("screening_passed_tiers"):
            continue

        # 2. Verificado: el DFT terminó bien.
        try:
            estado = json.loads((job / "status.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if estado.get("status") != "converged":
            continue

        if not md.get("fractions"):
            continue

        crudos.append({
            "candidate_id": md.get("candidate_id") or job.name,
            "formula": md.get("formula"),
            "generation_mode": md.get("generation_mode"),
            "tolerance_t": _num(md.get("tolerance_t")),
            "oct_factor": _num(md.get("oct_factor")),
            "n_atoms": md.get("n_atoms"),
            "lattice_constant_A": _num(md.get("lattice_constant_A")),
            "b_family": _familia_b(md.get("fractions", {})),
            "dominant_halide": _haluro_dominante(md.get("fractions", {})),
            "vol_est_A3": None,
            "batch": job.parent.name,
            "has_dft": True,
            "dft_status": "converged",
            "eg_dft_ev": _gap_dft(job),
            "energy_per_atom_eV": _num(estado.get("energy_per_atom_eV")),
            "_fractions": md["fractions"],
            "_organico": bool(md.get("molecular_A_placeholder")),
        })

    if not crudos:
        vacio = ([], f"sin candidatos verificados en {raiz_batches.name}")
        _VERIF_CACHE.update(t=ahora, clave=clave, valor=vacio)
        return vacio

    # 3. Score fotovoltaico: se predice el bandgap de la composición y se mide
    # su cercanía a la ventana. Se reutiliza el constructor de features de la
    # cascada para que el número sea el mismo que rankeó al candidato.
    try:
        import pandas as pd
        from types import SimpleNamespace

        from buho.screening.cascade import ScreeningCascade
        from ml_surrogate.features import build_X

        from .ml import _load

        for c in crudos:
            feats.append(ScreeningCascade._features(SimpleNamespace(
                fractions=c["_fractions"], is_organic_A=c["_organico"])))
        modelo = _load()
        medias, sigmas = modelo.predict_batch(build_X(pd.DataFrame(feats),
                                                      modelo.feature_cols))
        for c, m, s in zip(crudos, medias, sigmas):
            c["eg_pred_ev"] = float(m)
            c["eg_pred_std_ev"] = float(s)
            c["pv_score"] = round(_band_score(float(m)), 4)
    except Exception as exc:                              # noqa: BLE001
        log.warning("Sin score PV (%s): se listan sin filtrar por ventana", exc)
        for c in crudos:
            c["pv_score"] = None

    for c in crudos:
        c.pop("_fractions", None)
        c.pop("_organico", None)
        # `score` es la columna que ordena la vista: aquí manda el PV.
        c["score"] = c.get("pv_score")

    filas = [c for c in crudos
             if c.get("pv_score") is None or c["pv_score"] >= umbral_pv]
    filas.sort(key=lambda c: c.get("pv_score") or 0.0, reverse=True)

    lotes = len({c["batch"] for c in crudos})
    origen = (f"{len(filas)} de {len(crudos)} verificados en {lotes} lote(s), "
              f"score PV ≥ {umbral_pv}")
    resultado = (filas, origen)
    _VERIF_CACHE.update(t=ahora, clave=clave, valor=resultado)
    return resultado
