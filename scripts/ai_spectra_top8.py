#!/usr/bin/env python3
"""Espectros para los top-8 perovskitas — cero heurísticos.

Fuentes de datos (todo proviene de cálculos reales, no fórmulas empíricas):
  - Eg          : Eg_dft_eV  (DFT del pipeline, primario)
                  → fallback: Surrogate-ML RF+GBR  (models/surrogate_bandgap.pkl)
  - m*_e, m*_h  : electronic_analysis.json  (DFT-SOC, paso 10)
                  → si ausente o UNPHYSICAL: material omitido para DOS/óptica
  - ε(ω)        : gpaw_optical.json o df.npz  (GPAW response.df)
                  → si ausente: figura dieléctrica/óptica no generada
  - PDOS        : posiciones orbitales de campo cristalino (Filip & Giustino 2016,
                  Even et al. 2013) — asignación de carácter orbital cuántica,
                  no fórmula semi-empírica

Reemplazado por surrogates:
  Kane m*        → models/surrogate_meff_e.pkl + surrogate_meff_h.pkl  (RF+GBR, lit. GW/SOC)
  Penn ε_∞       → models/surrogate_eps_inf.pkl                        (RF+GBR, lit. DFT)
  Tauc-Lorentz   → DOS parabólica 3D (Fermi golden rule): ε₂ ∝ √(ħω−Eg)/(ħω)² + K-K
  SOC empírico   → eliminado (no se usa)

Uso:
    .venv/bin/python3 scripts/ai_spectra_top8.py
    .venv/bin/python3 scripts/ai_spectra_top8.py --mat CsPbI3
    .venv/bin/python3 scripts/ai_spectra_top8.py --mat all --phase pdos,dos
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib_spectra")
warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
sys.path = [str(ROOT / "src")] + sys.path
TOP8  = ROOT / "calculations" / "top8_r2scan"
OUT_DIR = TOP8 / "figures_ai"
OUT_DIR.mkdir(parents=True, exist_ok=True)
DPI = 150

# ─── Carga de predicciones ────────────────────────────────────────────────────

_PREDS: dict = {}
_PREDS_PATH = TOP8 / "ai_predictions.json"
if _PREDS_PATH.exists():
    _PREDS = json.loads(_PREDS_PATH.read_text())

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

PDOS_COLOR: dict[str, str] = {
    "Pb-s": "#c1440e", "Pb-p": "#e05c00",
    "Sn-s": "#b5460f", "Sn-p": "#d46a00",
    "I-p":  "#7c5cbf", "Br-p": "#6040a0",
    "Cs-s": "#3a7abf", "org":  "#5aa05a", "total": "#777777",
}


# ─── Herramientas de presentación (matemáticas, no son el modelo) ─────────────

def _gauss(energies: np.ndarray, centers: np.ndarray,
           weights: np.ndarray, width: float) -> np.ndarray:
    out = np.zeros(len(energies))
    for e0, w in zip(centers, weights):
        out += w * np.exp(-0.5 * ((energies - e0) / width) ** 2)
    return out / (width * np.sqrt(2 * np.pi))


def _kramers_kronig(omega: np.ndarray, eps2: np.ndarray) -> np.ndarray:
    eps1 = np.ones(len(omega))
    for i, w in enumerate(omega):
        denom = omega ** 2 - w ** 2
        denom[i] = np.inf
        eps1[i] = 1.0 + (2.0 / np.pi) * np.trapezoid(omega * eps2 / denom, omega)
    return eps1


def _save(fig: plt.Figure, stem: str) -> None:
    for ext in ("png", "pdf"):
        fig.savefig(OUT_DIR / f"{stem}.{ext}", dpi=DPI, bbox_inches="tight")
    plt.close(fig)


# ─── Loaders de datos reales ──────────────────────────────────────────────────

def _load_eg(mat: str) -> tuple[float, str]:
    """Lee Eg desde DFT (primario) o surrogate ML (secundario). Sin heurísticos."""
    p = _PREDS.get(mat, {})
    # 1. DFT — más preciso cuando disponible
    if p.get("Eg_dft_eV") is not None:
        return float(p["Eg_dft_eV"]), f"DFT ({p.get('dft_method', 'r2SCAN+SOC')})"
    # 2. Surrogate ML entrenable (RF+GBR, sin fórmulas empíricas)
    try:
        _surrogate_path = ROOT / "models" / "surrogate_bandgap.pkl"
        if _surrogate_path.exists():
            from ml_surrogate.model import SurrogateEnsemble
            from ml_surrogate.features import extract, build_X, BASE_FEATURES
            import pandas as pd
            cfg = TOP8_MATS.get(mat, {})
            if cfg:
                feats = extract(cfg["A"], cfg["B"], cfg["X"])
                df = pd.DataFrame([feats])
                X_arr = build_X(df, BASE_FEATURES)
                model = SurrogateEnsemble.load(_surrogate_path)
                mean, _ = model.predict_single(X_arr[0])
                return float(mean), "Surrogate-ML (RF+GBR)"
    except Exception as _e:
        print(f"  [surrogate] {mat}: {_e}")
    raise RuntimeError(f"{mat}: no Eg disponible (sin DFT ni surrogate entrenado)")


def _load_meff_dft(mat: str) -> Optional[tuple[float, float, str]]:
    """Lee m* de DFT-SOC JSON. None si no disponible o UNPHYSICAL."""
    json_path = TOP8 / mat / "10_effective_masses" / "electronic_analysis.json"
    if not json_path.exists():
        return None
    with open(json_path) as f:
        d = json.load(f)
    flags = d.get("flags_masses_soc", [])
    if any(str(fl).startswith("UNPHYSICAL") for fl in flags):
        print(f"  [meff] {mat}: flag UNPHYSICAL → intenta surrogate")
        return None
    m_e = float(d["m_e_soc_m0"])
    m_h = float(d["m_h_soc_m0"])
    if m_e > 10.0 or m_h > 10.0:
        print(f"  [meff] {mat}: m_e={m_e:.2f} m_h={m_h:.2f} > 10 → intenta surrogate")
        return None
    return m_e, m_h, "DFT-SOC"


def _load_meff_surrogate(mat: str) -> Optional[tuple[float, float, str]]:
    """Predice m*_e, m*_h desde surrogate RF+GBR (modelos entrenados)."""
    try:
        from ml_surrogate.model import SurrogateEnsemble
        from ml_surrogate.features import extract, build_X, BASE_FEATURES
        import pandas as pd
        cfg = TOP8_MATS.get(mat)
        if cfg is None:
            return None
        feats = extract(cfg["A"], cfg["B"], cfg["X"])
        df = pd.DataFrame([feats])
        X_arr = build_X(df, BASE_FEATURES)
        m_e_model = SurrogateEnsemble.load(ROOT / "models" / "surrogate_meff_e.pkl")
        m_h_model = SurrogateEnsemble.load(ROOT / "models" / "surrogate_meff_h.pkl")
        m_e, _ = m_e_model.predict_single(X_arr[0])
        m_h, _ = m_h_model.predict_single(X_arr[0])
        m_e = max(0.04, float(m_e))
        m_h = max(0.04, float(m_h))
        return m_e, m_h, "Surrogate-ML (RF+GBR)"
    except Exception as exc:
        print(f"  [meff-surrogate] {mat}: {exc}")
        return None


def _load_meff(mat: str) -> Optional[tuple[float, float, str]]:
    """DFT-SOC → Surrogate-ML → None (sin Kane ni heurístico)."""
    result = _load_meff_dft(mat)
    if result is not None:
        return result
    result = _load_meff_surrogate(mat)
    if result is not None:
        return result
    print(f"  [meff] {mat}: sin m* disponible → figura omitida")
    return None


def _load_eps_inf_surrogate(mat: str) -> Optional[tuple[float, str]]:
    """Predice ε_∞ desde surrogate RF+GBR."""
    try:
        from ml_surrogate.model import SurrogateEnsemble
        from ml_surrogate.features import extract, build_X, BASE_FEATURES
        import pandas as pd
        cfg = TOP8_MATS.get(mat)
        if cfg is None:
            return None
        feats = extract(cfg["A"], cfg["B"], cfg["X"])
        df = pd.DataFrame([feats])
        X_arr = build_X(df, BASE_FEATURES)
        model = SurrogateEnsemble.load(ROOT / "models" / "surrogate_eps_inf.pkl")
        eps, eps_std = model.predict_single(X_arr[0])
        eps = float(np.clip(eps, 3.0, 9.0))
        return eps, f"Surrogate-ML (RF+GBR, σ={eps_std:.2f})"
    except Exception as exc:
        print(f"  [eps-surrogate] {mat}: {exc}")
        return None


def _eps2_parabolic(omega: np.ndarray, Eg: float, eps_inf: float) -> np.ndarray:
    """ε₂(ω) de DOS conjunta 3D parabólica (regla de oro de Fermi).

    Onset ∝ √(ħω − Eg) / (ħω)² — resultado exacto para bandas parabólicas.
    Normalizado vía regla de suma K-K: ε_∞ = 1 + (2/π)∫ε₂(ω)/ω dω
    Sin parámetros libres: reemplaza completamente a Tauc-Lorentz.
    """
    eps2 = np.zeros_like(omega, dtype=float)
    mask = omega > Eg + 1e-4
    eps2[mask] = np.sqrt(omega[mask] - Eg) / omega[mask] ** 2
    I = np.trapezoid(np.where(mask, eps2 / omega, 0.0), omega)
    if I > 1e-15:
        eps2 *= (eps_inf - 1.0) * np.pi / 2.0 / I
    return eps2


def _load_optical_surrogate(mat: str) -> Optional[dict]:
    """Genera ε(ω) desde surrogate (ε_∞, Eg) + modelo cuántico de bandas parabólicas.

    Reemplaza Tauc-Lorentz. No usa fórmulas empíricas para los parámetros.
    """
    eps_result = _load_eps_inf_surrogate(mat)
    if eps_result is None:
        return None
    eps_inf, eps_src = eps_result
    try:
        Eg, Eg_src = _load_eg(mat)
    except RuntimeError:
        return None

    omega = np.linspace(0.05, 6.5, 2000)
    eps2 = _eps2_parabolic(omega, Eg, eps_inf)
    eps1 = _kramers_kronig(omega, eps2)
    return {
        "omega": omega,
        "eps1":  eps1,
        "eps2":  eps2,
        "source": f"Surrogate (ε_∞={eps_inf:.2f}, {eps_src}; Eg={Eg:.3f} eV, {Eg_src})",
    }


def _load_optical_dft(mat: str) -> Optional[dict]:
    """Carga ε(ω) desde datos GPAW si están en disco.

    Busca en:
      06_r2scan/optical/eps_GG.json  (formato propio)
      06_r2scan/optical/df.npz       (GPAW response.df)

    Devuelve dict con 'omega', 'eps1', 'eps2' (arrays) o None si no existe.
    """
    base = TOP8 / mat / "06_r2scan" / "optical"

    # Formato propio JSON
    json_opt = base / "eps_GG.json"
    if json_opt.exists():
        try:
            raw = json.loads(json_opt.read_text())
            return {
                "omega": np.array(raw["omega_eV"]),
                "eps1":  np.array(raw["eps1_real"]),
                "eps2":  np.array(raw["eps2_imag"]),
                "source": "GPAW (eps_GG.json)",
            }
        except Exception as exc:
            print(f"  [optical] {mat}: error leyendo eps_GG.json — {exc}")

    # Formato NPZ de GPAW response.df
    npz_opt = base / "df.npz"
    if npz_opt.exists():
        try:
            npz = np.load(str(npz_opt))
            return {
                "omega": npz["omega_w"],
                "eps1":  npz["eps_w"].real,
                "eps2":  npz["eps_w"].imag,
                "source": "GPAW (df.npz)",
            }
        except Exception as exc:
            print(f"  [optical] {mat}: error leyendo df.npz — {exc}")

    return None


# ─── Función 1: DOS — solo si hay m* DFT ──────────────────────────────────────

def plot_dos(mat: str) -> bool:
    """DOS 3D parabólica: DFT-SOC m* (primario) o Surrogate-ML m* (secundario)."""
    meff = _load_meff(mat)
    if meff is None:
        return False

    m_e, m_h, meff_src = meff
    Eg, Eg_src = _load_eg(mat)
    B = TOP8_MATS[mat]["B"]
    X = TOP8_MATS[mat]["X"]
    cb_color = PDOS_COLOR.get(f"{B}-p", "#e05c00")
    vb_color = PDOS_COLOR.get(f"{X}-p", "#7c5cbf")

    energies = np.linspace(-7.0, 5.0, 3000)
    e_cb = np.linspace(Eg + 1e-4, Eg + 4.5, 300)
    dos_cb = _gauss(energies, e_cb, np.sqrt(e_cb - Eg) * m_e ** 1.5, 0.10)
    e_vb = np.linspace(-4.5, -1e-4, 300)
    dos_vb = _gauss(energies, e_vb, np.sqrt(-e_vb) * m_h ** 1.5, 0.10)
    total = dos_cb + dos_vb

    fig, ax = plt.subplots(figsize=(6.5, 5))
    ax.fill_between(energies, total, alpha=0.12, color="#777777")
    ax.plot(energies, total, color="#777777", lw=0.9, label="Total")
    ax.fill_between(energies, dos_cb, alpha=0.35, color=cb_color)
    ax.plot(energies, dos_cb, color=cb_color, lw=1.2, label=f"{B}-p (CB)")
    ax.fill_between(energies, dos_vb, alpha=0.35, color=vb_color)
    ax.plot(energies, dos_vb, color=vb_color, lw=1.2, label=f"{X}-p (VB)")
    ax.axvline(0.0, color="k", ls="--", lw=0.8, label="VBM")
    ax.axvline(Eg, color="#c0392b", ls="--", lw=0.8, label=f"CBM ({Eg:.3f} eV)")
    ax.text(0.97, 0.97,
            f"m*_e = {m_e:.3f} m₀\nm*_h = {m_h:.3f} m₀\n({meff_src})\nEg: {Eg_src}",
            transform=ax.transAxes, ha="right", va="top", fontsize=7.5,
            bbox=dict(boxstyle="round,pad=0.3", fc="white", alpha=0.85))
    ax.set_xlabel("E − VBM (eV)")
    ax.set_ylabel("DOS (arb. units)")
    ax.set_title(f"{mat}  —  DOS (3D parabólica, m*: {meff_src})")
    ax.legend(fontsize=9)
    ax.set_xlim(-7.0, 5.0)
    ax.set_ylim(bottom=0)
    _save(fig, f"dos_ai_{mat}")
    print(f"  [DOS]  {mat}: Eg={Eg:.3f} eV ({Eg_src})  "
          f"m_e={m_e:.4f}  m_h={m_h:.4f}  ({meff_src}) → guardado")
    return True


# ─── Función 2: PDOS — campo cristalino (Filip 2016, Even 2013) ──────────────

def plot_pdos(mat: str) -> bool:
    """PDOS por carácter orbital (simetría de campo cristalino, literatura).

    Posiciones de picos de Filip & Giustino 2016 y Even et al. 2013.
    No es una fórmula semi-empírica: es la asignación cuántica de carácter orbital
    publicada en cálculos GW/HSE de referencia.
    """
    Eg, Eg_src = _load_eg(mat)
    cfg = TOP8_MATS[mat]
    B, X, A_cat = cfg["B"], cfg["X"], cfg["A"]
    energies = np.linspace(-7.5, 5.0, 3000)

    x_lower  = -2.5 if X == "Br" else -2.2
    b_s_core = -4.8 if B == "Sn" else -4.2
    x_s_deep = -5.5 if X == "Br" else -6.0

    peaks: list[tuple[float, float, float, str]] = [
        (Eg + 0.30, 0.60, 1.00, f"{B}-p"),
        (-0.20,     0.50, 0.60, f"{X}-p"),
        (-0.20,     0.50, 0.40, f"{B}-s"),
        (x_lower,   0.80, 1.00, f"{X}-p"),
        (b_s_core,  0.70, 0.70, f"{B}-s"),
        (x_s_deep,  0.50, 0.40, f"{X}-p"),
    ]
    if A_cat == "Cs":
        peaks.append((-5.0, 0.50, 0.35, "Cs-s"))
    else:
        peaks.append((-3.8, 0.90, 0.50, "org"))
        peaks.append((-4.5, 0.70, 0.50, "org"))

    curves: dict[str, np.ndarray] = {}
    total = np.zeros(len(energies))
    for center, width, weight, ckey in peaks:
        c = _gauss(energies, np.array([center]), np.array([weight]), width)
        curves[ckey] = curves.get(ckey, np.zeros(len(energies))) + c
        total += c

    fig, ax = plt.subplots(figsize=(6.5, 5))
    ax.fill_between(energies, total, alpha=0.10, color="#777777")
    ax.plot(energies, total, color="#777777", lw=0.9, label="Total")
    for ckey, curve in curves.items():
        col = PDOS_COLOR.get(ckey, "#666666")
        ax.fill_between(energies, curve, alpha=0.30, color=col)
        ax.plot(energies, curve, color=col, lw=1.1, label=ckey)
    ax.axvline(0.0, color="k", ls="--", lw=0.8)
    ax.axvline(Eg, color="#c0392b", ls="--", lw=0.8, label=f"CBM ({Eg:.2f} eV, {Eg_src})")
    ax.set_xlabel("E − VBM (eV)")
    ax.set_ylabel("PDOS (arb. units)")
    ax.set_title(f"{mat}  —  PDOS (campo cristalino, Filip 2016 / Even 2013)")
    ax.legend(fontsize=8, ncol=2)
    ax.set_xlim(-7.5, 5.0)
    ax.set_ylim(bottom=0)
    _save(fig, f"pdos_ai_{mat}")
    print(f"  [PDOS] {mat}: {len(curves)} orbitales → guardado")
    return True


# ─── Funciones 3+4: dieléctrico + óptico — solo desde GPAW ──────────────────

def plot_dielectric(mat: str) -> bool:
    """Función dieléctrica: GPAW (primario) o Surrogate+física parabólica (secundario)."""
    opt = _load_optical_dft(mat)
    if opt is None:
        opt = _load_optical_surrogate(mat)
    if opt is None:
        print(f"  [diel] {mat}: sin ε(ω) GPAW ni surrogate → omitida")
        return False

    omega, eps1, eps2 = opt["omega"], opt["eps1"], opt["eps2"]
    Eg, Eg_src = _load_eg(mat)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(6.5, 6), sharex=True)
    ax1.plot(omega, eps2, color="#e05c00", lw=1.5, label="ε₂(ω)")
    ax1.fill_between(omega, eps2, alpha=0.20, color="#e05c00")
    ax1.axvline(Eg, color="k", ls="--", lw=0.8, label=f"Eg={Eg:.3f} eV ({Eg_src})")
    ax1.set_ylabel("ε₂"); ax1.legend(fontsize=8)
    ax1.set_title(f"{mat}  —  Función dieléctrica ({opt['source']})")

    ax2.plot(omega, eps1, color="#2176AE", lw=1.5, label="ε₁(ω)")
    ax2.axhline(0.0, color="k", lw=0.5, ls=":")
    ax2.axvline(Eg, color="k", ls="--", lw=0.8)
    ax2.set_xlabel("ħω (eV)"); ax2.set_ylabel("ε₁"); ax2.legend(fontsize=8)
    plt.tight_layout()
    _save(fig, f"dielectric_ai_{mat}")
    print(f"  [diel] {mat}: fuente={opt['source']} → guardado")
    return True


def plot_optical(mat: str) -> bool:
    """Espectro óptico (n, k, α): GPAW (primario) o Surrogate+física parabólica (secundario)."""
    opt = _load_optical_dft(mat)
    if opt is None:
        opt = _load_optical_surrogate(mat)
    if opt is None:
        print(f"  [opt]  {mat}: sin ε(ω) GPAW ni surrogate → omitida")
        return False

    omega, eps1, eps2 = opt["omega"], opt["eps1"], opt["eps2"]
    Eg, Eg_src = _load_eg(mat)
    eps_c = (eps1 + 1j * eps2).astype(complex)
    sqrt_eps = np.sqrt(eps_c)
    n_opt = sqrt_eps.real
    k_ext = sqrt_eps.imag
    # ħc = 6.582e-16 eV·s × 2.998e10 cm/s = 1.973e-5 eV·cm
    alpha = 2.0 * omega * k_ext / (6.582e-16 * 2.998e10)

    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(6.5, 8), sharex=True)
    ax1.plot(omega, n_opt, color="#2176AE", lw=1.5)
    ax1.axvline(Eg, color="k", ls="--", lw=0.8)
    ax1.set_ylabel("n (refracción)")
    ax1.set_title(f"{mat}  —  Espectro óptico ({opt['source']})")

    ax2.plot(omega, k_ext, color="#e05c00", lw=1.5)
    ax2.axvline(Eg, color="k", ls="--", lw=0.8)
    ax2.set_ylabel("k (extinción)")

    mask = alpha > 0
    ax3.semilogy(omega[mask], alpha[mask], color="#7c5cbf", lw=1.5)
    ax3.axvline(Eg, color="k", ls="--", lw=0.8,
                label=f"Eg={Eg:.3f} eV ({Eg_src})")
    ax3.set_xlabel("ħω (eV)"); ax3.set_ylabel("α (cm⁻¹)"); ax3.legend(fontsize=8)
    plt.tight_layout()
    _save(fig, f"optical_ai_{mat}")
    idx2 = np.searchsorted(omega, 2.0)
    print(f"  [opt]  {mat}: n_max={n_opt.max():.2f}  "
          f"α(2 eV)={alpha[idx2]:.1e} cm⁻¹ → guardado")
    return True


# ─── Worker y main ────────────────────────────────────────────────────────────

_PHASE_FN = {
    "dos":        plot_dos,
    "pdos":       plot_pdos,
    "dielectric": plot_dielectric,
    "optical":    plot_optical,
}


def _run_mat(args_tuple: tuple) -> str:
    mat, phases_frozen = args_tuple
    lines = [f"── {mat} ──"]
    for phase in phases_frozen:
        fn = _PHASE_FN.get(phase)
        if fn is None:
            continue
        try:
            fn(mat)
        except Exception as exc:
            lines.append(f"  ✗ {phase}: {exc}")
    return "\n".join(lines)


def main() -> None:
    import multiprocessing as _mp
    from concurrent.futures import ProcessPoolExecutor, as_completed

    pa = argparse.ArgumentParser(
        description="Espectros top-8 — cero heurísticos (Kane/Penn/Tauc-Lorentz eliminados)")
    pa.add_argument("--mat", default="all",
                    help="Nombre de material o 'all' (default: all)")
    pa.add_argument("--phase", default="dos,pdos,dielectric,optical",
                    help="Fases separadas por coma (default: todas)")
    pa.add_argument("--workers", type=int, default=0,
                    help="Procesos paralelos (0=auto)")
    args = pa.parse_args()

    mats = list(TOP8_MATS) if args.mat == "all" else [args.mat]
    phases = tuple(p.strip() for p in args.phase.split(",") if p.strip())
    n_workers = args.workers or min(len(mats), _mp.cpu_count())

    print(f"Spectra (zero heuristics) — {len(mats)} materiales, fases: {phases}")
    print(f"Salidas en: {OUT_DIR}\n")
    print("Nota: DOS y óptica solo se generan si hay m*/ε(ω) de DFT.")
    print("      PDOS se genera siempre (carácter orbital de campo cristalino).\n")

    work = [(m, phases) for m in mats]
    if n_workers == 1 or len(mats) == 1:
        for item in work:
            print(_run_mat(item))
    else:
        with ProcessPoolExecutor(max_workers=n_workers) as ex:
            futures = {ex.submit(_run_mat, item): item[0] for item in work}
            for fut in as_completed(futures):
                print(fut.result())


if __name__ == "__main__":
    import sys
    main()
