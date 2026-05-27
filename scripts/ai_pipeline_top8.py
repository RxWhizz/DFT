#!/usr/bin/env python3
"""Pipeline AI para los top-8 perovskitas — refactorizado a GNN puro (MATGL).

Equivalencias DFT ↔ AI (sin heurísticos):
  AI-01: Relajación geométrica MACE-MP-0 (FIRE + FrechetCellFilter)
  AI-02: Bandgap GNN — MEGNet-BandGap-mfi-MP-2019.4.1
  AI-03: Score GNN UCB — GNNAcquisition (band_score_GNN + stab_score_GNN + ucb_bonus)
  AI-04: Energía de formación — MEGNet-Eform + M3GNet-Eform (ensemble, incertidumbre)

Eliminado (heurísticos):
  B_BASE + X_SHIFT (Eg semi-empírico)
  Goldschmidt t como función de adquisición
  Corrección SOC empírica (AI-05)
  Kane, Penn, Tauc-Lorentz (en ai_spectra_top8.py)

Salidas:
  calculations/top8_r2scan/ai_predictions.json
  calculations/top8_r2scan/figures_ai/compare_eg_gnn_dft.png
  calculations/top8_r2scan/figures_ai/compare_geometry.png
  calculations/top8_r2scan/figures_ai/gnn_scores_ranking.png
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, "/home/luis-ochoa/Documents/Vscode/py/hts-perovskite")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from ml_surrogate.gnn_predictor import GNNPredictor
from ml_surrogate.structure_builder import PerovskiteStructureBuilder
from ml_surrogate.bayes_optimizer import GNNAcquisition

TOP8 = ROOT / "calculations" / "top8_r2scan"
OUT_JSON = TOP8 / "ai_predictions.json"
OUT_FIGS = TOP8 / "figures_ai"
OUT_FIGS.mkdir(parents=True, exist_ok=True)

TOP8_MATS: dict[str, dict] = {
    "CsSnI3":  {"A": "Cs", "B": "Sn", "X": "I"},
    "MASnI3":  {"A": "MA", "B": "Sn", "X": "I"},
    "FASnI3":  {"A": "FA", "B": "Sn", "X": "I"},
    "FASnBr3": {"A": "FA", "B": "Sn", "X": "Br"},
    "CsPbI3":  {"A": "Cs", "B": "Pb", "X": "I"},
    "MAPbI3":  {"A": "MA", "B": "Pb", "X": "I"},
    "FAPbI3":  {"A": "FA", "B": "Pb", "X": "I"},
    "FAPbBr3": {"A": "FA", "B": "Pb", "X": "Br"},
}

DFT_EG: dict[str, float] = {
    "CsSnI3": 1.359, "MASnI3": 1.584, "FASnI3": 0.771, "FASnBr3": 1.115,
    "CsPbI3": 1.483, "MAPbI3": 2.054, "FAPbI3": 0.982, "FAPbBr3": 1.079,
}
DFT_METHOD: dict[str, str] = {
    "CsSnI3": "r²SCAN+U+SOC", "MASnI3": "r²SCAN+U+SOC",
    "FASnI3": "r²SCAN+U+SOC", "FASnBr3": "r²SCAN+U+SOC",
    "CsPbI3": "PBE+scissor",  "MAPbI3": "PBE+scissor",
    "FAPbI3": "PBE+scissor",  "FAPbBr3": "PBE+scissor",
}
EXP_EG: dict[str, float | None] = {
    "CsSnI3": 1.30, "MASnI3": None, "FASnI3": None, "FASnBr3": None,
    "CsPbI3": 1.73, "MAPbI3": 1.55, "FAPbI3": 1.48, "FAPbBr3": 2.23,
}

# ─── AI-01: MACE-MP-0 relajación geométrica ──────────────────────────────────

def step_mace(atoms, mat: str) -> dict:
    try:
        from mace.calculators import mace_mp
        from ase.optimize import FIRE
        from ase.filters import FrechetCellFilter

        t0 = time.time()
        calc = mace_mp(model="small", dispersion=False,
                       default_dtype="float32", device="cpu")
        a = atoms.copy()
        a.calc = calc
        FIRE(FrechetCellFilter(a), logfile=None).run(fmax=0.05, steps=300)
        elapsed = time.time() - t0

        lengths = a.cell.lengths()
        dft_len = atoms.cell.lengths()
        fmax_val = float(np.max(np.abs(a.get_forces())))
        print(f"  [AI-01] {mat}: a={lengths[0]:.3f} Å (Δ={lengths[0]-dft_len[0]:+.3f}), "
              f"fmax={fmax_val:.4f}, {elapsed:.0f} s")
        return {
            "a_mace_A":  round(float(lengths[0]), 4),
            "b_mace_A":  round(float(lengths[1]), 4),
            "c_mace_A":  round(float(lengths[2]), 4),
            "a_dft_A":   round(float(dft_len[0]), 4),
            "delta_a_A": round(float(lengths[0] - dft_len[0]), 4),
            "E_mace_eV": round(float(a.get_potential_energy()), 4),
            "fmax":      round(fmax_val, 5),
            "converged": fmax_val < 0.1,
            "time_mace_s": round(elapsed, 1),
            "_relaxed_atoms": a,
        }
    except Exception as exc:
        print(f"  [AI-01] {mat}: ERROR — {exc}")
        return {"error_mace": str(exc), "_relaxed_atoms": atoms}


# ─── AI-02 + AI-03 + AI-04: GNN prediction (MEGNet / M3GNet) ─────────────────

def step_gnn(atoms, mat: str, predictor: GNNPredictor,
             acquisition: GNNAcquisition) -> dict:
    try:
        from pymatgen.io.ase import AseAtomsAdaptor
        struct = AseAtomsAdaptor.get_structure(atoms)
        source = "gpw"
    except Exception as exc:
        print(f"  [GNN]   {mat}: pymatgen conversion failed — {exc}")
        return {"error_gnn": str(exc)}

    try:
        t0 = time.time()
        res = predictor.predict(struct, source)
        elapsed = time.time() - t0

        score = acquisition.score_one(mat, res)

        ef_str = f"{res.Eform_eV_atom:.4f}" if res.Eform_eV_atom is not None else "N/A"
        std_str = (f" ± {res.Eform_std_eV_atom:.4f}"
                   if res.Eform_std_eV_atom is not None else "")
        print(f"  [AI-02] {mat}: Eg_GNN={res.Eg_eV:.4f} eV  [{source}]")
        print(f"  [AI-04] {mat}: Eform={ef_str}{std_str} eV/atom")
        print(f"  [AI-03] {mat}: band={score.band_score:.4f}  "
              f"stab={score.stab_score:.4f}  ucb={score.ucb_bonus:.4f}  "
              f"total={score.total_score:.4f}  [{elapsed:.1f} s]")
        if res.model_warnings:
            for w in res.model_warnings:
                print(f"           WARN: {w}")

        out: dict = {
            "Eg_gnn_eV":              round(res.Eg_eV, 4),
            "Eform_megnet_eV_atom":   (round(res.Eform_megnet_eV_atom, 4)
                                       if res.Eform_megnet_eV_atom is not None else None),
            "Eform_m3gnet_eV_atom":   (round(res.Eform_m3gnet_eV_atom, 4)
                                       if res.Eform_m3gnet_eV_atom is not None else None),
            "Eform_gnn_eV_atom":      (round(res.Eform_eV_atom, 4)
                                       if res.Eform_eV_atom is not None else None),
            "Eform_gnn_std_eV_atom":  (round(res.Eform_std_eV_atom, 4)
                                       if res.Eform_std_eV_atom is not None else None),
            "gnn_struct_source":      source,
            "in_pv_window":           res.in_pv_window,
            "is_stable_heuristic":    res.is_stable,
            "band_score_gnn":         score.band_score,
            "stab_score_gnn":         score.stab_score,
            "ucb_bonus_gnn":          score.ucb_bonus,
            "gnn_score":              score.total_score,
            "model_warnings":         res.model_warnings,
            "time_gnn_s":             round(elapsed, 1),
        }
        return out
    except Exception as exc:
        print(f"  [GNN]   {mat}: prediction failed — {exc}")
        return {"error_gnn": str(exc)}


# ─── Main pipeline ───────────────────────────────────────────────────────────

def main() -> None:
    predictor = GNNPredictor(device="cpu")
    acquisition = GNNAcquisition(beta=1.0)
    builder = PerovskiteStructureBuilder()

    # Preload GNN models once before the loop
    predictor._preload_all()

    results: dict[str, dict] = {}

    print("\n" + "=" * 65)
    print("PIPELINE AI — top-8 perovskitas (GNN puro, sin heurísticos)")
    print("=" * 65)

    for mat, cfg in TOP8_MATS.items():
        A, B, X = cfg["A"], cfg["B"], cfg["X"]
        print(f"\n{'─'*50}\n=== {mat} ===")

        res: dict = {"material": mat, "A": A, "B": B, "X": X}

        # Load DFT structure (for MACE relaxation starting point)
        atoms_dft = None
        try:
            from ase.io import read as ase_read
            mat_dir = TOP8 / mat
            for gpw_rel in [
                "01_relax_sym/relax_sym.gpw",
                "01_relax/relax.gpw",
                "06_r2scan/r2scan.gpw",
                "06_r2scan/u_scan/u_scan_U2p50.gpw",
            ]:
                gpw = mat_dir / gpw_rel
                if gpw.exists():
                    atoms_dft = ase_read(str(gpw))
                    print(f"  [load]  {mat}: {gpw.name}, {len(atoms_dft)} atoms")
                    break
        except Exception as exc:
            print(f"  [load]  {mat}: ERROR — {exc}")

        if atoms_dft is None:
            # Build structure from scratch for GNN (no MACE relaxation)
            print(f"  [load]  {mat}: no GPW — building from composition for GNN only")
            try:
                struct, src = builder.build(A, B, X, mat=mat)
                gnn_res = predictor.predict(struct, src)
                score = acquisition.score_one(mat, gnn_res)
                res.update({
                    "Eg_gnn_eV": round(gnn_res.Eg_eV, 4),
                    "gnn_score": score.total_score,
                    "gnn_struct_source": src,
                    "Eg_dft_eV": DFT_EG.get(mat),
                    "dft_method": DFT_METHOD.get(mat),
                    "Eg_exp_eV": EXP_EG.get(mat),
                })
                results[mat] = res
            except Exception as exc:
                print(f"  ERROR: {exc}")
                results[mat] = {**res, "error": str(exc)}
            continue

        # AI-01: MACE relaxation
        mace_res = step_mace(atoms_dft, mat)
        relaxed_atoms = mace_res.pop("_relaxed_atoms", atoms_dft)
        res.update(mace_res)

        # AI-02 + AI-03 + AI-04: GNN on relaxed geometry
        res.update(step_gnn(relaxed_atoms, mat, predictor, acquisition))

        # Reference values
        res["Eg_dft_eV"]  = DFT_EG.get(mat)
        res["dft_method"] = DFT_METHOD.get(mat)
        res["Eg_exp_eV"]  = EXP_EG.get(mat)

        results[mat] = res

        print(f"  → Eg_GNN={res.get('Eg_gnn_eV', 'N/A'):.4f}  "
              f"Eform={res.get('Eform_gnn_eV_atom', 'N/A')}  "
              f"GNN_score={res.get('gnn_score', 'N/A'):.4f}  "
              f"Eg_DFT={res.get('Eg_dft_eV', 'N/A'):.3f} eV")

    # ── Save JSON ────────────────────────────────────────────────────────────

    def _serialize(v):
        if isinstance(v, (np.integer,)):   return int(v)
        if isinstance(v, (np.floating,)):  return float(v)
        if isinstance(v, (np.bool_,)):     return bool(v)
        if isinstance(v, np.ndarray):      return v.tolist()
        return v

    out = {
        k: {kk: _serialize(vv) for kk, vv in v.items() if not kk.startswith("_")}
        for k, v in results.items()
    }
    OUT_JSON.write_text(json.dumps(out, indent=2))
    print(f"\nJSON → {OUT_JSON}")

    # ── Figures ──────────────────────────────────────────────────────────────
    _plot_eg_comparison(results)
    _plot_geometry_comparison(results)
    _plot_gnn_scores(results, acquisition)


# ─── Figures ─────────────────────────────────────────────────────────────────

def _plot_eg_comparison(results: dict) -> None:
    mats = list(results.keys())
    x = np.arange(len(mats))
    w = 0.22

    eg_gnn = [results[m].get("Eg_gnn_eV", np.nan) for m in mats]
    eg_dft = [results[m].get("Eg_dft_eV", np.nan) for m in mats]
    eg_exp = [results[m].get("Eg_exp_eV") or np.nan  for m in mats]

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.bar(x - w, eg_gnn, w*1.8, label="MEGNet-BandGap (GNN, AI-02)",
           color="#e67e22", alpha=0.85)
    ax.bar(x + w, eg_dft, w*1.8, label="DFT (r²SCAN+U+SOC / PBE+scissor)",
           color="#27ae60", alpha=0.85)
    for i, eg in enumerate(eg_exp):
        if not np.isnan(eg):
            ax.scatter(x[i] + 2.5*w, eg, marker="*", s=140, color="#c0392b",
                       zorder=5, label="Experimental" if i == 0 else "")

    ax.axhline(1.1, color="gray", lw=0.7, ls="--", alpha=0.5)
    ax.axhline(1.8, color="gray", lw=0.7, ls="--", alpha=0.5)
    ax.text(7.6, 1.1, "SQ min", fontsize=7, color="gray", va="bottom")
    ax.text(7.6, 1.8, "SQ max", fontsize=7, color="gray", va="bottom")
    ax.set_xticks(x)
    ax.set_xticklabels(mats, rotation=30, ha="right", fontsize=10)
    ax.set_ylabel("$E_g$ (eV)", fontsize=12)
    ax.set_title("Bandgap: MEGNet-BandGap GNN vs DFT vs Experimental\n"
                 "(sin heurísticos — MEGNet entrenado en Materials Project PBE)", fontsize=10)
    ax.legend(fontsize=9, loc="upper right")
    ax.set_ylim(0, 3.5)
    ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    out = OUT_FIGS / "compare_eg_gnn_dft.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Figura → {out}")


def _plot_geometry_comparison(results: dict) -> None:
    mats = [m for m in results if "a_mace_A" in results[m]]
    if not mats:
        return

    a_dft  = [results[m]["a_dft_A"]  for m in mats]
    a_mace = [results[m]["a_mace_A"] for m in mats]
    delta  = [results[m]["delta_a_A"] for m in mats]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))
    x = np.arange(len(mats)); w = 0.35
    ax1.bar(x - w/2, a_dft,  w, label="DFT", color="#27ae60", alpha=0.85)
    ax1.bar(x + w/2, a_mace, w, label="MACE-MP-0 (AI-01)", color="#e67e22", alpha=0.85)
    ax1.set_xticks(x); ax1.set_xticklabels(mats, rotation=30, ha="right", fontsize=9)
    ax1.set_ylabel("a (Å)"); ax1.set_title("Parámetro de celda: DFT vs MACE")
    ax1.legend(fontsize=9); ax1.grid(axis="y", alpha=0.2); ax1.set_ylim(5, 7)

    ax2.bar(x, delta, color=["#c0392b" if d > 0 else "#2980b9" for d in delta], alpha=0.85)
    ax2.axhline(0, color="black", lw=0.8)
    ax2.set_xticks(x); ax2.set_xticklabels(mats, rotation=30, ha="right", fontsize=9)
    ax2.set_ylabel("Δa = a_MACE − a_DFT (Å)")
    ax2.set_title("Error geométrico MACE-MP-0 vs DFT"); ax2.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    out = OUT_FIGS / "compare_geometry.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Figura → {out}")


def _plot_gnn_scores(results: dict, acquisition: GNNAcquisition) -> None:
    from ml_surrogate.gnn_predictor import GNNResult

    pairs = []
    for mat, r in results.items():
        if "Eg_gnn_eV" not in r:
            continue
        gr = GNNResult(
            Eg_eV=r["Eg_gnn_eV"],
            Eform_megnet_eV_atom=None,
            Eform_m3gnet_eV_atom=None,
            Eform_eV_atom=r.get("Eform_gnn_eV_atom"),
            Eform_std_eV_atom=r.get("Eform_gnn_std_eV_atom"),
            structure_source=r.get("gnn_struct_source", ""),
        )
        pairs.append((mat, gr))

    ranked = acquisition.rank([m for m, _ in pairs], [r for _, r in pairs])

    mats_ord = [s.material for s in ranked]
    x = np.arange(len(mats_ord))
    band  = [s.band_score  for s in ranked]
    stab  = [s.stab_score  for s in ranked]
    bonus = [s.ucb_bonus   for s in ranked]
    total = [s.total_score for s in ranked]

    fig, ax = plt.subplots(figsize=(10, 5))
    w = 0.2
    ax.bar(x - 1.5*w, band,  w, label="band_score (Eg→PV)", color="#3498db", alpha=0.85)
    ax.bar(x - 0.5*w, stab,  w, label="stab_score (Eform)", color="#27ae60", alpha=0.85)
    ax.bar(x + 0.5*w, bonus, w, label="ucb_bonus (Eform std)", color="#e67e22", alpha=0.85)
    ax.bar(x + 1.5*w, total, w, label="GNN score total", color="#9b59b6", alpha=0.85)
    ax.set_xticks(x)
    ax.set_xticklabels(mats_ord, rotation=30, ha="right", fontsize=10)
    ax.set_ylabel("Score [0–3]", fontsize=11)
    ax.set_title("Ranking GNN — UCB sin heurísticos\n"
                 "band_score(MEGNet-Eg) + stab_score(Eform) + ucb_bonus(Eform std)", fontsize=10)
    ax.legend(fontsize=8.5); ax.set_ylim(0, 2.5); ax.grid(axis="y", alpha=0.2)
    for i, s in enumerate(ranked):
        ax.text(x[i] + 1.5*w, s.total_score + 0.04, f"{s.total_score:.2f}",
                ha="center", fontsize=7.5, color="#7d3c98")
    fig.tight_layout()
    out = OUT_FIGS / "gnn_scores_ranking.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Figura → {out}")


if __name__ == "__main__":
    main()
