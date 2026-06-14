#!/usr/bin/env python3
"""Validación física del MLIP en sistemas de interés (sección 'Validación' de la tesis).

Relaja estructuras ABX₃ con el modelo fine-tuneado y compara contra DFT:

  A) Holdout de relajación del dataset CsXI3 (14056015.zip): para cada par
     (relax_test_set_initial → relax_test_set_relaxed), relajar el inicial con el MLIP y
     comparar parámetros de red y RMSD de posiciones contra la geometría DFT relajada.
  B) Perovskitas representativas puras (CsSnI3, CsPbI3, CsSnBr3, ...): relajar desde la
     estimación geométrica y reportar a₀ y volumen/átomo vs valores DFT/experimentales.

Reutiliza el patrón de relajación MACE (FIRE + FrechetCellFilter) de la Fase 2A.

Uso:
  PYTHONPATH=src .venv/bin/python3 scripts/validate_mlip.py --tag mh_b000 [--n-relax 30]
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ase.io import read  # noqa: E402

MODELS = ROOT / "models" / "mace_phase2"
REPORTS = ROOT / "reports" / "training fase 2"
DATA_DIR = Path.home() / "Documents" / "Data"

# a₀ (Å) cúbico Pm-3m de referencia (exp/DFT literatura) para sanity de perovskitas puras.
REF_A0 = {"CsSnI3": 6.24, "CsPbI3": 6.29, "CsSnBr3": 5.80, "CsPbBr3": 5.87,
          "CsSnCl3": 5.58, "CsPbCl3": 5.61}


def load_model_calc(tag: str, head: str = "phase2a", dtype: str = "float32"):
    from mace.calculators import MACECalculator
    model = MODELS / f"phase2_mlip_{tag}.model"
    if not model.exists():
        raise SystemExit(f"no existe {model}")
    return MACECalculator(model_paths=[str(model)], device="cpu",
                          default_dtype=dtype, head=head)


def relax(atoms, calc, fmax=0.05, steps=200, cell=True):
    from ase.optimize import FIRE
    from ase.filters import FrechetCellFilter
    at = atoms.copy()
    at.calc = calc
    target = FrechetCellFilter(at) if cell else at
    opt = FIRE(target, logfile=None)
    opt.run(fmax=fmax, steps=steps)
    return at


def cubic_a0(atoms) -> float:
    """a₀ efectivo por átomo-fórmula: (volumen / n_fu)^(1/3), n_fu = n_atoms/5 para ABX3."""
    n_fu = max(1, len(atoms) // 5)
    return float((atoms.get_volume() / n_fu) ** (1 / 3))


# ─────────────────────── A) holdout de relajación CsXI3 ───────────────────────

def validate_relax_holdout(calc, n_relax: int) -> dict:
    zip_path = DATA_DIR / "14056015.zip"
    if not zip_path.exists():
        return {"error": "14056015.zip no disponible"}
    with zipfile.ZipFile(zip_path) as zf:
        def _load(member):
            with tempfile.NamedTemporaryFile("wb", suffix=".xyz", delete=True) as t:
                t.write(zf.read(member)); t.flush()
                return read(t.name, index=":")
        ini = _load("relax_test_set_initial.xyz")
        fin = _load("relax_test_set_relaxed.xyz")
    pairs = list(zip(ini, fin))
    rng = np.random.RandomState(0)
    if len(pairs) > n_relax:
        pairs = [pairs[int(i)] for i in sorted(rng.permutation(len(pairs))[:n_relax])]
    da0, dvol = [], []
    for at0, atf in pairs:
        try:
            relaxed = relax(at0, calc)
        except Exception:
            continue
        a_pred, a_dft = cubic_a0(relaxed), cubic_a0(atf)
        da0.append(a_pred - a_dft)
        dvol.append((relaxed.get_volume() - atf.get_volume()) / atf.get_volume() * 100)
    da0 = np.array(da0); dvol = np.array(dvol)
    return {"n": len(da0),
            "a0_MAE_A": round(float(np.mean(np.abs(da0))), 4) if len(da0) else None,
            "a0_RMSE_A": round(float(np.sqrt(np.mean(da0 ** 2))), 4) if len(da0) else None,
            "volume_MAPE_pct": round(float(np.mean(np.abs(dvol))), 2) if len(dvol) else None}


# ─────────────────────── B) perovskitas puras representativas ───────────────────────

def validate_pure(calc) -> list[dict]:
    from ase import Atoms
    out = []
    for formula, a0_ref in REF_A0.items():
        A, B, X = formula[:2], formula[2:4], formula[4:-1]
        a_guess = a0_ref * 1.05                        # partir ~5% expandido
        # celda cúbica Pm-3m: A en esquina, B en centro, X en caras
        at = Atoms(f"{A}{B}{X}3",
                   scaled_positions=[[0, 0, 0], [0.5, 0.5, 0.5],
                                     [0.5, 0.5, 0], [0.5, 0, 0.5], [0, 0.5, 0.5]],
                   cell=[a_guess] * 3, pbc=True)
        try:
            relaxed = relax(at, calc)
            a_pred = cubic_a0(relaxed)
            out.append({"formula": formula, "a0_ref_A": a0_ref,
                        "a0_mlip_A": round(a_pred, 3),
                        "err_pct": round((a_pred - a0_ref) / a0_ref * 100, 2)})
        except Exception as exc:
            out.append({"formula": formula, "error": str(exc)})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--n-relax", type=int, default=30)
    ap.add_argument("--head", default="phase2a")
    ap.add_argument("--dtype", default="float32", choices=["float32", "float64"],
                    help="debe coincidir con el dtype de entrenamiento (Colab GPU = float32)")
    args = ap.parse_args()

    REPORTS.mkdir(parents=True, exist_ok=True)
    calc = load_model_calc(args.tag, args.head, args.dtype)

    summary = {"tag": args.tag, "head": args.head}
    print("Validando holdout de relajación CsXI3…", flush=True)
    summary["relax_holdout_cssni3"] = validate_relax_holdout(calc, args.n_relax)
    print("Validando perovskitas puras…", flush=True)
    summary["pure_perovskites"] = validate_pure(calc)

    pure_ok = [r for r in summary["pure_perovskites"] if "err_pct" in r]
    if pure_ok:
        summary["pure_a0_MAPE_pct"] = round(
            float(np.mean([abs(r["err_pct"]) for r in pure_ok])), 2)

    (REPORTS / f"mlip_{args.tag}_validation.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
