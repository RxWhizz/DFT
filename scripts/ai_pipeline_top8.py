#!/usr/bin/env python3
"""Pipeline AI para los top-8 perovskitas — pasos AI-01 a AI-04 (metodología §12).

Tabla de equivalencias DFT ↔ AI:
  AI-02: Eg semi-empírico (B_BASE + X_SHIFT) + factor de tolerancia Goldschmidt t
  AI-01: Relajación geométrica MACE-MP-0 (FIRE + FrechetCellFilter)
  AI-04: Predicción de bandgap con MEGNet-MP (proxy de ALIGNN-FC; ALIGNN roto por DGL)
  AI-03: Score AINAGENT (prescreening Bayesiano — AI score semi-empírico)

Salidas:
  calculations/top8_r2scan/ai_predictions.json
  calculations/top8_r2scan/figures/compare_ai_dft.png
  calculations/top8_r2scan/figures/compare_geometry.png
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")

# AINAGENT en path
sys.path.insert(0, "/home/luis-ochoa/Documents/Vscode/py/AI")
sys.path.insert(0, "/home/luis-ochoa/Documents/Vscode/py/hts-perovskite")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
TOP8 = ROOT / "calculations" / "top8_r2scan"
OUT_JSON = TOP8 / "ai_predictions.json"
OUT_FIGS = TOP8 / "figures_ai"
OUT_FIGS.mkdir(parents=True, exist_ok=True)

# ─── Parámetros del modelo (§12.3 metodología) ────────────────────────────

B_BASE = {"Pb": 1.5, "Sn": 1.3, "Ge": 2.0}
X_SHIFT = {"I": 0.0, "Br": 0.3, "Cl": 0.6}

# Radios iónicos Shannon (1976) + Kieslich (2014) para MA/FA
R_A = {"Cs": 1.88, "Rb": 1.72, "MA": 2.17, "FA": 2.53}
R_B = {"Pb": 1.19, "Sn": 1.18, "Ge": 0.73}
R_X = {"I": 2.20, "Br": 1.96, "Cl": 1.81}

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

# Resultados DFT de esta sesión (referencia)
DFT_EG = {
    "CsSnI3": 1.359, "MASnI3": 1.584, "FASnI3": 0.771, "FASnBr3": 1.115,
    "CsPbI3": 1.483, "MAPbI3": 2.054, "FAPbI3": 0.982, "FAPbBr3": 1.079,
}
DFT_METHOD = {
    "CsSnI3": "r²SCAN+U+SOC", "MASnI3": "r²SCAN+U+SOC",
    "FASnI3": "r²SCAN+U+SOC", "FASnBr3": "r²SCAN+U+SOC",
    "CsPbI3": "PBE+scissor",  "MAPbI3": "PBE+scissor",
    "FAPbI3": "PBE+scissor",  "FAPbBr3": "PBE+scissor",
}
EXP_EG: dict[str, float | None] = {
    "CsSnI3": 1.30, "MASnI3": None, "FASnI3": None, "FASnBr3": None,
    "CsPbI3": 1.73, "MAPbI3": 1.55, "FAPbI3": 1.48, "FAPbBr3": 2.23,
}

# ─── AI-05: Corrección SOC empírica desde literatura ─────────────────────
# ΔEg_SOC por par (A, B) en eV — derivado de:
#   Even et al. Phys. Rev. Lett. 109, 166805 (2013)  → Pb SOC splitting
#   Brivio et al. Phys. Rev. B 89, 155204 (2014)     → MAPbI3
#   Mosconi et al. J. Phys. Chem. C 117, 13902 (2013)→ Sn perovskitas
#   Filip & Giustino Phys. Chem. Chem. Phys. 18, 9884 (2016) → FA dilución
# Nota: ΔEg_SOC es negativo (SOC reduce el gap).
# Para catión FA el CBM mezcla orbital FA-π* con B-site-p → efecto SOC diluido.
SOC_SHIFT: dict[tuple, float] = {
    ("Cs", "Pb"): -0.50,
    ("MA", "Pb"): -0.55,
    ("FA", "Pb"): -0.20,
    ("Cs", "Sn"): -0.25,
    ("MA", "Sn"): -0.22,
    ("FA", "Sn"): -0.08,
}

# ─── AI-02: Semi-empírico ─────────────────────────────────────────────────

def step_semiempirical(mat: str) -> dict:
    cfg = TOP8_MATS[mat]
    A, B, X = cfg["A"], cfg["B"], cfg["X"]
    eg = B_BASE[B] + X_SHIFT[X]
    t = (R_A[A] + R_X[X]) / (np.sqrt(2) * (R_B[B] + R_X[X]))
    # AI score: penaliza si Eg fuera de [1.1, 1.8] eV y t fuera de [0.80, 1.05]
    eg_score = max(0.0, 1.0 - abs(eg - 1.45) / 0.35)
    t_score  = max(0.0, 1.0 - abs(t - 0.9) / 0.15)
    ai_score = round(eg_score * t_score * 2.0, 4)
    print(f"  [AI-02] {mat}: Eg_semi={eg:.2f} eV, t={t:.4f}, AI_score={ai_score:.4f}")
    return {
        "Eg_semi_eV": round(eg, 3),
        "tolerance_t": round(float(t), 4),
        "ai_score_02": ai_score,
    }


# ─── Carga de estructuras desde archivos DFT ──────────────────────────────

def load_atoms(mat: str):
    from ase.io import read
    mat_dir = TOP8 / mat
    for gpw in [
        mat_dir / "01_relax_sym" / "relax_sym.gpw",
        mat_dir / "01_relax" / "relax.gpw",
        mat_dir / "06_r2scan" / "r2scan.gpw",
        mat_dir / "06_r2scan" / "u_scan" / "u_scan_U2p50.gpw",
    ]:
        if gpw.exists():
            try:
                atoms = read(str(gpw))
                lengths = atoms.cell.lengths()
                print(f"  [load]  {mat}: {gpw.name}, {len(atoms)} átomos, "
                      f"a={lengths[0]:.3f} Å")
                return atoms
            except Exception:
                pass
    raise RuntimeError(f"No se encontró estructura legible para {mat}")


# ─── AI-01: MACE-MP-0 relajación geométrica ───────────────────────────────

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
        opt = FIRE(FrechetCellFilter(a), logfile=None)
        opt.run(fmax=0.05, steps=300)
        elapsed = time.time() - t0

        lengths = a.cell.lengths()
        fmax_val = float(np.max(np.abs(a.get_forces())))
        energy = float(a.get_potential_energy())
        converged = fmax_val < 0.1

        # Variación vs geometría DFT inicial
        dft_lengths = atoms.cell.lengths()
        delta_a = float(lengths[0]) - float(dft_lengths[0])

        print(f"  [AI-01] {mat}: a={lengths[0]:.3f} Å (Δ={delta_a:+.3f}), "
              f"fmax={fmax_val:.4f}, {elapsed:.0f} s")
        return {
            "a_mace_A":   round(float(lengths[0]), 4),
            "b_mace_A":   round(float(lengths[1]), 4),
            "c_mace_A":   round(float(lengths[2]), 4),
            "a_dft_A":    round(float(dft_lengths[0]), 4),
            "delta_a_A":  round(delta_a, 4),
            "E_mace_eV":  round(energy, 4),
            "fmax":       round(fmax_val, 5),
            "converged":  converged,
            "time_s":     round(elapsed, 1),
            "_relaxed_atoms": a,   # para MEGNet
        }
    except Exception as exc:
        print(f"  [AI-01] {mat}: ERROR — {exc}")
        return {"error": str(exc), "_relaxed_atoms": atoms}


# ─── AI-04: MEGNet bandgap (proxy de ALIGNN-FC) ───────────────────────────

_megnet = None

def _get_megnet():
    global _megnet
    if _megnet is None:
        import matgl
        import matgl.layers._graph_convolution_pyg as gcm

        # Patch versión: matgl 3.0.1 broadcast bug con checkpoint antiguo
        _orig = gcm._broadcast_to_nodes
        def _fixed(sf, nb, nn):
            while sf.dim() > 2:
                sf = sf.squeeze(0)
            return _orig(sf, nb, nn)
        gcm._broadcast_to_nodes = _fixed

        _megnet = matgl.load_model("MEGNet-BandGap-mfi-MP-2019.4.1")
    return _megnet


def step_megnet(atoms, mat: str) -> dict:
    try:
        import torch
        from pymatgen.io.ase import AseAtomsAdaptor

        model = _get_megnet()
        struct = AseAtomsAdaptor.get_structure(atoms)
        # state=2: insulator (mfi: metal=0, ferromagnet=1, insulator=2)
        eg = float(model.predict_structure(struct, state_attr=torch.tensor([[2]])))
        print(f"  [AI-04] {mat}: Eg_MEGNet = {eg:.3f} eV")
        return {"Eg_megnet_eV": round(eg, 4)}
    except Exception as exc:
        print(f"  [AI-04] {mat}: ERROR — {exc}")
        return {"Eg_megnet_eV": None, "error_megnet": str(exc)}


# ─── AI-03: Score AINAGENT (evaluación directa sin Bayesian loop) ─────────

def step_ainagent_score(mat: str) -> dict:
    """Score AI equivalente al que daría MaterialEvaluationNode de AINAGENT."""
    # Calculado con las mismas fórmulas de hts/candidate_space.py
    cfg = TOP8_MATS[mat]
    A, B, X = cfg["A"], cfg["B"], cfg["X"]
    eg_semi = B_BASE[B] + X_SHIFT[X]
    t = (R_A[A] + R_X[X]) / (np.sqrt(2) * (R_B[B] + R_X[X]))

    # Score basado en ventana fotovoltaica óptima [1.1, 1.8] eV y t ~ [0.80, 1.05]
    eg_in_window = 1.1 <= eg_semi <= 1.8
    t_in_range = 0.80 <= t <= 1.05

    # physics.band score: función gaussiana centrada en 1.45 eV (centro de ventana PV)
    band_score = np.exp(-0.5 * ((eg_semi - 1.45) / 0.35) ** 2)
    # physics.gold score: factor de tolerancia — pico en t=0.9
    gold_score = np.exp(-0.5 * ((t - 0.9) / 0.12) ** 2)

    # AI score combinado (rango [0, 2])
    ai_score = float(band_score + gold_score)

    print(f"  [AI-03] {mat}: band={band_score:.3f}, gold={gold_score:.3f}, "
          f"AI_score={ai_score:.3f}")
    return {
        "band_score":   round(float(band_score), 4),
        "gold_score":   round(float(gold_score), 4),
        "ai_score_03":  round(ai_score, 4),
        "eg_in_pv_window": eg_in_window,
        "t_in_range":   t_in_range,
    }


# ─── AI-05: Corrección SOC empírica ──────────────────────────────────────

def step_soc_empirical(mat: str, eg_semi: float, eg_megnet: float | None) -> dict:
    """Aplica ΔEg_SOC empírico (literatura) sobre Eg_semi y Eg_MEGNet.

    Eg_semi fue calibrado contra valores experimentales que ya incluyen SOC
    implícitamente, por lo que Eg_semi_soc sirve de referencia comparativa.
    Eg_megnet_soc es la corrección principal: MEGNet no fue entrenado con SOC.
    """
    A = TOP8_MATS[mat]["A"]
    B = TOP8_MATS[mat]["B"]
    delta = SOC_SHIFT.get((A, B), 0.0)

    eg_semi_soc   = round(eg_semi + delta, 4)
    eg_megnet_soc = round(eg_megnet + delta, 4) if eg_megnet is not None else None

    print(f"  [AI-05] {mat}: ΔEg_SOC={delta:+.2f} eV  "
          f"Eg_semi_SOC={eg_semi_soc:.3f}  "
          f"Eg_MEGNet_SOC={eg_megnet_soc}")
    return {
        "delta_soc_eV":    delta,
        "Eg_semi_soc_eV":  eg_semi_soc,
        "Eg_megnet_soc_eV": eg_megnet_soc,
        "soc_source":      f"({A},{B}): Even2013/Brivio2014/Filip2016",
    }


# ─── Main pipeline ────────────────────────────────────────────────────────

def main() -> None:
    results: dict[str, dict] = {}

    print("\n" + "=" * 60)
    print("PIPELINE AI — top-8 perovskitas")
    print("=" * 60)

    for mat in TOP8_MATS:
        print(f"\n{'─'*50}")
        print(f"=== {mat} ===")

        res: dict = {"material": mat, **TOP8_MATS[mat]}

        # AI-02: semi-empírico
        res.update(step_semiempirical(mat))

        # AI-03: score AINAGENT
        res.update(step_ainagent_score(mat))

        # Cargar estructura DFT como punto de partida
        try:
            atoms_dft = load_atoms(mat)
        except Exception as exc:
            print(f"  ERROR cargando estructura: {exc}")
            results[mat] = res
            continue

        # AI-01: MACE-MP-0 relajación
        mace_res = step_mace(atoms_dft, mat)
        relaxed_atoms = mace_res.pop("_relaxed_atoms", atoms_dft)
        res.update(mace_res)

        # AI-04: MEGNet sobre geometría relajada por MACE
        res.update(step_megnet(relaxed_atoms, mat))

        # AI-05: Corrección SOC empírica desde literatura
        res.update(step_soc_empirical(
            mat,
            eg_semi=res["Eg_semi_eV"],
            eg_megnet=res.get("Eg_megnet_eV"),
        ))

        # Referencia DFT y experimental
        res["Eg_dft_eV"]    = DFT_EG.get(mat)
        res["dft_method"]   = DFT_METHOD.get(mat)
        res["Eg_exp_eV"]    = EXP_EG.get(mat)

        results[mat] = res
        print(f"  → Eg_semi={res['Eg_semi_eV']:.2f} | "
              f"Eg_semi_SOC={res['Eg_semi_soc_eV']:.3f} | "
              f"Eg_MEGNet_SOC={res.get('Eg_megnet_soc_eV')} | "
              f"Eg_DFT={res['Eg_dft_eV']:.3f} eV")

    # Guardar JSON (sin atoms internos)
    def _to_python(v):
        if isinstance(v, (np.integer,)):   return int(v)
        if isinstance(v, (np.floating,)):  return float(v)
        if isinstance(v, (np.bool_,)):     return bool(v)
        if isinstance(v, np.ndarray):      return v.tolist()
        return v

    out = {k: {kk: _to_python(vv) for kk, vv in v.items() if not kk.startswith("_")}
           for k, v in results.items()}
    OUT_JSON.write_text(json.dumps(out, indent=2))
    print(f"\nJSON guardado → {OUT_JSON}")

    # Generar figuras
    _plot_eg_comparison(results)
    _plot_geometry_comparison(results)
    _plot_ai_scores(results)


# ─── Figuras ──────────────────────────────────────────────────────────────

def _plot_eg_comparison(results: dict) -> None:
    """Barras de Eg para cada método vs material, incluyendo corrección SOC (AI-05)."""
    mats = list(results.keys())
    x = np.arange(len(mats))
    w = 0.17

    eg_semi      = [results[m].get("Eg_semi_eV", np.nan)      for m in mats]
    eg_semi_soc  = [results[m].get("Eg_semi_soc_eV", np.nan)  for m in mats]
    eg_megnet_soc= [results[m].get("Eg_megnet_soc_eV") or np.nan for m in mats]
    eg_dft       = [results[m].get("Eg_dft_eV", np.nan)       for m in mats]
    eg_exp       = [results[m].get("Eg_exp_eV") or np.nan      for m in mats]

    fig, ax = plt.subplots(figsize=(12, 5.5))

    ax.bar(x - 1.5*w, eg_semi,       w, label="Semi-emp (AI-02)", color="#5b8dd9", alpha=0.85)
    ax.bar(x - 0.5*w, eg_semi_soc,   w, label="Semi-emp+SOC (AI-05)", color="#2471a3", alpha=0.85)
    ax.bar(x + 0.5*w, eg_megnet_soc, w, label="MEGNet+SOC (AI-04+05)", color="#e67e22", alpha=0.85)
    ax.bar(x + 1.5*w, eg_dft,        w, label="DFT (r²SCAN+U+SOC / PBE+scissor)", color="#27ae60", alpha=0.85)

    for i, eg in enumerate(eg_exp):
        if not np.isnan(eg):
            ax.scatter(x[i] + 2.3*w, eg, marker="*", s=130, color="#c0392b",
                       zorder=5, label="Experimental" if i == 0 else "")

    ax.set_xticks(x)
    ax.set_xticklabels(mats, rotation=30, ha="right", fontsize=10)
    ax.set_ylabel("$E_g$ (eV)", fontsize=12)
    ax.set_title("Comparativa Bandgap: AI vs AI+SOC vs DFT vs Experimental\n"
                 "Corrección SOC (AI-05): Even 2013, Brivio 2014, Filip 2016", fontsize=11)
    ax.legend(fontsize=8.5, loc="upper right")
    ax.axhline(1.1, color="gray", lw=0.7, ls="--", alpha=0.5)
    ax.axhline(1.8, color="gray", lw=0.7, ls="--", alpha=0.5)
    ax.text(7.55, 1.1, "SQ min", fontsize=7, color="gray", va="bottom")
    ax.text(7.55, 1.8, "SQ max", fontsize=7, color="gray", va="bottom")
    ax.set_ylim(0, 3.5)
    ax.grid(axis="y", alpha=0.2)

    fig.tight_layout()
    out = OUT_FIGS / "compare_eg_ai_dft.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Figura guardada → {out}")


def _plot_geometry_comparison(results: dict) -> None:
    """Parámetros de celda DFT vs MACE-MP-0."""
    mats = [m for m in results if "a_mace_A" in results[m]]
    if not mats:
        return

    a_dft  = [results[m]["a_dft_A"]  for m in mats]
    a_mace = [results[m]["a_mace_A"] for m in mats]
    delta  = [results[m]["delta_a_A"] for m in mats]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))

    x = np.arange(len(mats))
    w = 0.35
    ax1.bar(x - w/2, a_dft,  w, label="DFT (PBEsol+D3)", color="#27ae60", alpha=0.85)
    ax1.bar(x + w/2, a_mace, w, label="MACE-MP-0 (AI-01)", color="#e67e22", alpha=0.85)
    ax1.set_xticks(x); ax1.set_xticklabels(mats, rotation=30, ha="right", fontsize=9)
    ax1.set_ylabel("a (Å)", fontsize=11)
    ax1.set_title("Parámetro de celda: DFT vs MACE", fontsize=10)
    ax1.legend(fontsize=9); ax1.grid(axis="y", alpha=0.2)
    ax1.set_ylim(5, 7)

    colors = ["#c0392b" if d > 0 else "#2980b9" for d in delta]
    ax2.bar(x, delta, color=colors, alpha=0.85)
    ax2.axhline(0, color="black", lw=0.8)
    ax2.set_xticks(x); ax2.set_xticklabels(mats, rotation=30, ha="right", fontsize=9)
    ax2.set_ylabel("Δa = a_MACE − a_DFT (Å)", fontsize=11)
    ax2.set_title("Error geométrico MACE-MP-0 vs DFT", fontsize=10)
    ax2.grid(axis="y", alpha=0.2)

    fig.tight_layout()
    out = OUT_FIGS / "compare_geometry.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Figura guardada → {out}")


def _plot_ai_scores(results: dict) -> None:
    """Ranking AI (score AINAGENT) vs solar score DFT."""
    mats = list(results.keys())
    x = np.arange(len(mats))
    ai_scores = [results[m].get("ai_score_03", 0) for m in mats]

    # Normalizar DFT Eg a solar score indicativo (ventana [1.1,1.8] eV)
    def _sq_efficiency(eg):
        if eg is None or np.isnan(eg):
            return 0
        if 1.1 <= eg <= 1.8:
            return 1.0 - abs(eg - 1.35) / 0.45
        return max(0, 0.3 - abs(eg - 1.45) * 0.2)

    dft_sq = [_sq_efficiency(results[m].get("Eg_dft_eV")) for m in mats]
    dft_sq_norm = [s / max(dft_sq) * 2.0 for s in dft_sq]

    fig, ax = plt.subplots(figsize=(9, 4.5))
    w = 0.35
    ax.bar(x - w/2, ai_scores,    w, label="AI score (AINAGENT, AI-03)", color="#9b59b6", alpha=0.85)
    ax.bar(x + w/2, dft_sq_norm,  w, label="Solar score DFT (normalizado)", color="#27ae60", alpha=0.85)
    ax.set_xticks(x)
    ax.set_xticklabels(mats, rotation=30, ha="right", fontsize=10)
    ax.set_ylabel("Score [0–2]", fontsize=11)
    ax.set_title("Ranking AI (AINAGENT) vs Solar Score DFT\n"
                 "R_blend = 0.3·AI + 0.7·DFT  (learning loop, AI-06)", fontsize=10)
    ax.legend(fontsize=9)
    ax.set_ylim(0, 2.2)
    ax.grid(axis="y", alpha=0.2)

    # R_blend annotation
    r_blend = [0.3 * a + 0.7 * d for a, d in zip(ai_scores, dft_sq_norm)]
    for i, rb in enumerate(r_blend):
        ax.text(x[i], rb + 0.05, f"{rb:.2f}", ha="center", fontsize=7.5, color="#c0392b")

    fig.tight_layout()
    out = OUT_FIGS / "ai_scores_ranking.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Figura guardada → {out}")


if __name__ == "__main__":
    main()
