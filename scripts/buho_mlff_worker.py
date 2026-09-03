#!/usr/bin/env python3
"""Worker del tier MLFF/GNN (Tier 2 de la cascada).

Corre en el entorno que tiene torch/matgl/pymatgen, que no tiene por que ser
el del monitor. En Windows ese entorno vive en WSL: el monitor invoca este
script por `wsl.exe` y se comunica con el por JSON en stdin/stdout.

Protocolo, deliberadamente minimo:

    buho_mlff_worker.py --preflight-only
        -> {"status":"ok","versions":{"torch":"...","matgl":"...",...}}

    echo '{"candidates":[...],"config":{...}}' | buho_mlff_worker.py --stdin
        -> {"status":"ok","results":[{"candidate_id":...,"Eg_gnn_eV":...},...]}

El lote entero va en una sola invocacion a proposito: cargar MEGNet y M3GNet
cuesta bastante mas que predecir, asi que una llamada por candidato
multiplicaria ese coste fijo por N.

**Todo el JSON sale por stdout y nada mas sale por stdout.** matgl, dgl y el
propio arranque de WSL escriben avisos sin pedir permiso; si se mezclaran con
la respuesta, el lado Windows no podria parsearla. Por eso el trabajo pesado
corre con stdout redirigido a stderr y la respuesta se escribe al final sobre
el stdout real.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import math
import sys
import traceback
from pathlib import Path
from typing import Any


def _project_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    # scripts/buho_mlff_worker.py -> raiz del repo
    return Path(__file__).resolve().parents[1]


def _ensure_importable(root: Path) -> None:
    src = root / "src"
    for entry in (str(src), str(root)):
        if entry not in sys.path:
            sys.path.insert(0, entry)


#: Nombre del paquete en PyPI cuando no coincide con el del modulo.
_DIST = {"sklearn": "scikit-learn"}


def _versions() -> dict[str, str]:
    import importlib
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _dist_version

    out: dict[str, str] = {}
    for mod in ("torch", "matgl", "pymatgen", "ase", "numpy", "pandas", "sklearn"):
        try:
            m = importlib.import_module(mod)
        except Exception as exc:  # noqa: BLE001 - se reporta, no se propaga
            out[mod] = f"MISSING ({type(exc).__name__})"
            continue
        version = getattr(m, "__version__", None)
        if not version:
            # pymatgen ya no expone __version__; sin este fallback el wizard
            # enseñaba "?" para un paquete que estaba perfectamente instalado.
            try:
                version = _dist_version(_DIST.get(mod, mod))
            except PackageNotFoundError:
                version = "?"
        out[mod] = str(version)
    return out


def _missing(versions: dict[str, str]) -> list[str]:
    return [name for name, ver in versions.items() if ver.startswith("MISSING")]


# ── Preflight ─────────────────────────────────────────────────────────────────


def preflight(root: Path) -> dict[str, Any]:
    _ensure_importable(root)
    versions = _versions()
    # ase/numpy/pandas/sklearn hacen falta para construir estructuras y para
    # importar el paquete ml_surrogate; torch/matgl/pymatgen para predecir.
    criticos = [n for n in ("torch", "matgl", "pymatgen", "ase") if n in _missing(versions)]
    if criticos:
        return {
            "status": "error",
            "error": f"Faltan modulos en el entorno MLFF: {', '.join(criticos)}",
            "remediation": "Ejecuta 'buho setup install mlff' para crear/reparar el entorno.",
            "versions": versions,
            "python": sys.executable,
        }

    # Importar de verdad: `find_spec` no detecta una rueda de torch rota, que es
    # justo el fallo que aparece cuando alguien mezcla numpy 1.x y 2.x.
    try:
        with contextlib.redirect_stdout(sys.stderr):
            from ml_surrogate.gnn_predictor import GNNPredictor  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "error": f"El entorno MLFF no puede importar GNNPredictor: {type(exc).__name__}: {exc}",
            "remediation": "Suele ser un choque de versiones de numpy. 'buho setup install mlff --repair'.",
            "versions": versions,
            "python": sys.executable,
        }

    return {
        "status": "ok",
        "versions": versions,
        "python": sys.executable,
        "project_root": str(root),
    }


# ── Prediccion ────────────────────────────────────────────────────────────────


def _finite(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(out) else out


def predict(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    _ensure_importable(root)

    raw_candidates = payload.get("candidates") or []
    config = payload.get("config") or {}
    if not raw_candidates:
        return {"status": "ok", "results": []}

    with contextlib.redirect_stdout(sys.stderr):
        from pymatgen.io.ase import AseAtomsAdaptor

        from buho.generator.heuristic_generator import GeneratedCandidate
        from buho.structure.build_abx3 import ABX3StructureBuilder
        from ml_surrogate.gnn_predictor import GNNPredictor

        builder = ABX3StructureBuilder(config, random_seed=config.get("random_seed", 42))
        gnn = GNNPredictor(device=str(payload.get("device") or "cpu"))

        results: list[dict[str, Any]] = []
        for raw in raw_candidates:
            cid = str(raw.get("candidate_id", ""))
            try:
                candidate = GeneratedCandidate.from_dict(raw)
            except Exception as exc:  # noqa: BLE001
                results.append({"candidate_id": cid, "error": f"candidato invalido: {exc}"})
                continue

            try:
                atoms, meta = builder.build(candidate, out_dir=None, export=False)
                origen = "pseudoatom" if meta.get("molecular_A_placeholder") else "cubic"
                structure = AseAtomsAdaptor.get_structure(atoms)
            except Exception as exc:  # noqa: BLE001
                results.append(
                    {"candidate_id": cid, "error": f"no se pudo construir la estructura: {exc}"}
                )
                continue

            try:
                res = gnn.predict(structure, structure_source=origen)
            except Exception as exc:  # noqa: BLE001
                results.append({"candidate_id": cid, "error": f"{type(exc).__name__}: {exc}"})
                continue

            results.append(
                {
                    "candidate_id": cid,
                    "Eg_gnn_eV": _finite(res.Eg_eV),
                    "Eform_megnet_eV_atom": _finite(res.Eform_megnet_eV_atom),
                    "Eform_m3gnet_eV_atom": _finite(res.Eform_m3gnet_eV_atom),
                    "structure_source": res.structure_source,
                    "error": None,
                }
            )

    return {"status": "ok", "results": results}


# ── Entrada ───────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Worker MLFF/GNN de BUHO.")
    parser.add_argument("--preflight-only", action="store_true",
                        help="Comprueba el entorno y sale sin predecir.")
    parser.add_argument("--stdin", action="store_true",
                        help="Lee el lote JSON de stdin.")
    parser.add_argument("--project-root", default=None,
                        help="Raiz del repo (por defecto, la del propio script).")
    args = parser.parse_args(argv)

    root = _project_root(args.project_root)

    try:
        if args.preflight_only:
            out = preflight(root)
        elif args.stdin:
            raw = sys.stdin.read()
            try:
                payload = json.loads(raw) if raw.strip() else {}
            except json.JSONDecodeError as exc:
                out = {"status": "error", "error": f"lote JSON invalido: {exc}"}
            else:
                out = predict(root, payload)
        else:
            out = {"status": "error", "error": "Usa --preflight-only o --stdin."}
    except Exception as exc:  # noqa: BLE001 - la respuesta SIEMPRE es JSON
        out = {
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(limit=6),
        }

    sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return 0 if out.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
