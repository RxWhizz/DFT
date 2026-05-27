#!/usr/bin/env python3
"""DOS, PDOS y función dieléctrica puramente AI para los top-8 perovskitas.

Modelos AI (sin GPAW, sin eigenvalores DFT):
  - DOS 3D parabólica: D(E) ∝ m*^(3/2)·√|E-Eborde| (Kane / DFT SOC)
  - m* efectivas: Modelo de Kane (m*_e = Eg/(Eg+P²), P²=20 eV)
  - PDOS: Posiciones orbitales de campo cristalino (Filip 2016, Even 2013)
  - ε₂(ω): Oscilador Tauc-Lorentz (Jellison-Modine 1996)
  - ε_∞: JARVIS-DFT-3D (CsPbI3, CsSnI3) / Penn fallback (MA/FA)

Herramientas matemáticas de presentación (NO son el contenido AI):
  - _gauss: ensanchamiento gaussiano de los picos
  - _kramers_kronig: ε₁ desde ε₂ vía transformada de Kramers-Kronig

Uso:
    .venv/bin/python3 scripts/ai_spectra_top8.py
    .venv/bin/python3 scripts/ai_spectra_top8.py --mat CsPbI3
    .venv/bin/python3 scripts/ai_spectra_top8.py --mat all --phase dos,pdos
"""
from __future__ import annotations

import argparse
import json
import os
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib_ai_spectra")
warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
TOP8 = ROOT / "calculations" / "top8_r2scan"
OUT_DIR = TOP8 / "figures_ai"
OUT_DIR.mkdir(parents=True, exist_ok=True)
DPI = 150

JARVIS_CACHE = TOP8 / "jarvis_eps_cache.json"

_AI_PREDS: dict = json.loads((TOP8 / "ai_predictions.json").read_text())

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

# JARVIS DFT-3D JIDs para inorgánicos cúbicos (Pm-3m).
# CsPbI3 no está en JARVIS-DFT-3D; CsSnI3 (JVASP-22675) tiene epsx='na'.
# Se mantienen para intento con fallback Penn si epsilon='na' o JID ausente.
JARVIS_JIDS: dict[str, str] = {
    "CsSnI3": "JVASP-22675",
}


# ---------------------------------------------------------------------------
# Herramientas matemáticas (auxiliares — NO son el contenido AI)
# ---------------------------------------------------------------------------

def _gauss(energies: np.ndarray, centers: np.ndarray,
           weights: np.ndarray, width: float) -> np.ndarray:
    out = np.zeros(len(energies))
    for e0, w in zip(centers, weights):
        out += w * np.exp(-0.5 * ((energies - e0) / width) ** 2)
    return out / (width * np.sqrt(2 * np.pi))


def _kramers_kronig(omega: np.ndarray, eps2: np.ndarray) -> np.ndarray:
    """ε₁(ω) = 1 + (2/π) P∫ ω'ε₂(ω')/(ω'²-ω²) dω'  vía trapecio."""
    eps1 = np.ones(len(omega))
    for i, w in enumerate(omega):
        denom = omega ** 2 - w ** 2
        denom[i] = np.inf
        integrand = omega * eps2 / denom
        eps1[i] = 1.0 + (2.0 / np.pi) * np.trapezoid(integrand, omega)
    return eps1


def _save(fig: plt.Figure, out_dir: Path, stem: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(out_dir / f"{stem}.{ext}", dpi=DPI, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# AI modelo: ε_∞ — JARVIS DFT-3D (inorgánicos) o Penn (fallback MA/FA)
# ---------------------------------------------------------------------------

def _penn_fallback(mat: str) -> tuple[float, str]:
    """Penn model: ε_∞ = clip(1 + (14/Eg)², 3.5, 7.0)."""
    Eg = _AI_PREDS[mat]["Eg_semi_soc_eV"]
    eps = float(np.clip(1.0 + (14.0 / Eg) ** 2, 3.5, 7.0))
    return eps, "Penn"


def _fetch_jarvis_eps(mat: str) -> tuple[float, str]:
    """Retorna (ε_∞, fuente). JARVIS DFT-3D para Cs-inorgánicos; Penn para MA/FA."""
    cache: dict = json.loads(JARVIS_CACHE.read_text()) if JARVIS_CACHE.exists() else {}
    if mat in cache:
        return cache[mat]["eps_inf"], cache[mat]["source"]

    jid = JARVIS_JIDS.get(mat)
    if jid is None:
        return _penn_fallback(mat)

    try:
        from jarvis.db.figshare import get_jid_data
        d = get_jid_data(jid=jid, dataset="dft_3d")
        # JARVIS usa 'epsx/epsy/epsz', no 'epsilon_x'
        ex = d.get("epsx", "na"); ey = d.get("epsy", "na"); ez = d.get("epsz", "na")
        if "na" in (str(ex), str(ey), str(ez)):
            raise ValueError(f"epsilon not computed in JARVIS for {jid}")
        ex, ey, ez = float(ex), float(ey), float(ez)
        eps_avg = round((ex + ey + ez) / 3.0, 3)
        src = f"JARVIS {jid}"
        cache[mat] = {"eps_inf": eps_avg, "source": src}
        JARVIS_CACHE.write_text(json.dumps(cache, indent=2))
        print(f"  [JARVIS] {mat}: ε_∞={eps_avg:.3f}  ε=({ex:.2f},{ey:.2f},{ez:.2f})")
        return eps_avg, src
    except Exception as e:
        print(f"  [JARVIS] {mat}: {e} → Penn fallback")
        return _penn_fallback(mat)


# ---------------------------------------------------------------------------
# AI modelo: masas efectivas Kane (Sn) o DFT SOC JSON (Pb válidos)
# ---------------------------------------------------------------------------

def _kane_mass(mat: str) -> tuple[float, float, str]:
    """Modelo Kane: m*_e = Eg/(Eg+P²), m*_h = 1.3·m*_e, P²=20 eV."""
    Eg = _AI_PREDS[mat]["Eg_semi_soc_eV"]
    P2 = 20.0
    m_e = Eg / (Eg + P2)
    m_h = 1.3 * m_e
    return m_e, m_h, "Kane"


def _load_meff(mat: str) -> tuple[float, float, str]:
    """Retorna (m_e, m_h, fuente). Kane para Sn y Pb-unphysical; DFT-SOC para Pb válidos."""
    if TOP8_MATS[mat]["B"] == "Sn":
        return _kane_mass(mat)

    json_path = TOP8 / mat / "10_effective_masses" / "electronic_analysis.json"
    if not json_path.exists():
        return _kane_mass(mat)

    with open(json_path) as f:
        d = json.load(f)

    if any(str(fl).startswith("UNPHYSICAL") for fl in d.get("flags_masses_soc", [])):
        print(f"  [meff] {mat}: flag UNPHYSICAL → Kane")
        return _kane_mass(mat)

    m_e = float(d["m_e_soc_m0"])
    m_h = float(d["m_h_soc_m0"])
    if m_e > 10.0 or m_h > 10.0:
        print(f"  [meff] {mat}: m_e={m_e:.2f} o m_h={m_h:.2f} > 10 → Kane")
        return _kane_mass(mat)

    return m_e, m_h, "DFT-SOC"


# ---------------------------------------------------------------------------
# AI modelo: ε₂(ω) — oscilador Tauc-Lorentz (Jellison-Modine 1996)
# ---------------------------------------------------------------------------

def _tauc_lorentz(omega: np.ndarray, Eg: float, E0: float,
                  C: float, A: float) -> np.ndarray:
    """ε₂ = A·E₀·C·(ħω−Eg)² / [ħω·((ħω²−E₀²)² + C²·ħω²)]  para ħω > Eg."""
    eps2 = np.zeros_like(omega)
    mask = omega > Eg
    hw = omega[mask]
    eps2[mask] = (A * E0 * C * (hw - Eg) ** 2
                  / (hw * ((hw ** 2 - E0 ** 2) ** 2 + C ** 2 * hw ** 2)))
    return eps2


# ---------------------------------------------------------------------------
# Función 1: DOS AI — 3D parabólica (modelo Kane / DFT SOC)
# ---------------------------------------------------------------------------

def plot_dos_ai(mat: str, out_dir: Path) -> None:
    Eg = _AI_PREDS[mat]["Eg_semi_soc_eV"]
    m_e, m_h, meff_src = _load_meff(mat)
    B = TOP8_MATS[mat]["B"]
    X = TOP8_MATS[mat]["X"]
    cb_color = PDOS_COLOR.get(f"{B}-p", "#e05c00")
    vb_color = PDOS_COLOR.get(f"{X}-p", "#7c5cbf")

    energies = np.linspace(-7.0, 5.0, 3000)

    # CB: D_c(E) ∝ (m*_e)^(3/2) · √(E - Eg)
    e_cb = np.linspace(Eg + 1e-4, Eg + 4.5, 300)
    dos_cb = _gauss(energies, e_cb, np.sqrt(e_cb - Eg) * m_e ** 1.5, 0.10)

    # VB: D_v(E) ∝ (m*_h)^(3/2) · √(-E)
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

    ax.axvline(0.0, color="k", ls="--", lw=0.8)
    ax.axvline(Eg, color="#c0392b", ls="--", lw=0.8)
    ax.text(0.97, 0.97,
            f"m*_e = {m_e:.3f} m₀\nm*_h = {m_h:.3f} m₀\n({meff_src})",
            transform=ax.transAxes, ha="right", va="top", fontsize=8,
            bbox=dict(boxstyle="round,pad=0.3", fc="white", alpha=0.8))
    ax.set_xlabel("E − VBM (eV)")
    ax.set_ylabel("DOS (arb. units)")
    ax.set_title(f"{mat}  —  DOS AI (3D parabólica)")
    ax.legend(fontsize=9)
    ax.set_xlim(-7.0, 5.0)
    ax.set_ylim(bottom=0)
    _save(fig, out_dir, f"dos_ai_{mat}")
    print(f"  [DOS]  {mat}: Eg={Eg:.3f} eV  m_e={m_e:.4f}  m_h={m_h:.4f}  ({meff_src})")


# ---------------------------------------------------------------------------
# Función 2: PDOS AI — campo cristalino (Filip 2016, Even 2013)
# ---------------------------------------------------------------------------

def plot_pdos_ai(mat: str, out_dir: Path) -> None:
    cfg = TOP8_MATS[mat]
    B, X, A_cat = cfg["B"], cfg["X"], cfg["A"]
    Eg = _AI_PREDS[mat]["Eg_semi_soc_eV"]
    energies = np.linspace(-7.5, 5.0, 3000)

    x_lower = -2.5 if X == "Br" else -2.2
    b_s_core = -4.8 if B == "Sn" else -4.2
    x_s_deep = -5.5 if X == "Br" else -6.0

    # (center_eV, width_eV, weight, color_key_in_PDOS_COLOR)
    peaks: list[tuple[float, float, float, str]] = [
        (Eg + 0.30, 0.60, 1.00, f"{B}-p"),  # B-p antibonding CB
        (-0.20,     0.50, 0.60, f"{X}-p"),  # X-p @ VBM
        (-0.20,     0.50, 0.40, f"{B}-s"),  # B-s @ VBM (hybridized)
        (x_lower,   0.80, 1.00, f"{X}-p"),  # X-p lower band
        (b_s_core,  0.70, 0.70, f"{B}-s"),  # B-s core
        (x_s_deep,  0.50, 0.40, f"{X}-p"),  # X-s deep
    ]
    if A_cat == "Cs":
        peaks.append((-5.0, 0.50, 0.35, "Cs-s"))
    else:
        peaks.append((-3.8, 0.90, 0.50, "org"))  # N-2p (MA/FA)
        peaks.append((-4.5, 0.70, 0.50, "org"))  # C-2p (MA/FA)

    # Accumulate by orbital type (one curve per color_key)
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
        color = PDOS_COLOR.get(ckey, "#666666")
        ax.fill_between(energies, curve, alpha=0.30, color=color)
        ax.plot(energies, curve, color=color, lw=1.1, label=ckey)

    ax.axvline(0.0, color="k", ls="--", lw=0.8)
    ax.axvline(Eg, color="#c0392b", ls="--", lw=0.8, label=f"CBM ({Eg:.2f} eV)")
    ax.set_xlabel("E − VBM (eV)")
    ax.set_ylabel("PDOS (arb. units)")
    ax.set_title(f"{mat}  —  PDOS AI (campo cristalino)")
    ax.legend(fontsize=8, ncol=2)
    ax.set_xlim(-7.5, 5.0)
    ax.set_ylim(bottom=0)
    _save(fig, out_dir, f"pdos_ai_{mat}")
    print(f"  [PDOS] {mat}: {len(curves)} tipos orbitales → guardado")


# ---------------------------------------------------------------------------
# Funciones 3+4: dieléctrico + óptico — Tauc-Lorentz + K-K + JARVIS/Penn
# ---------------------------------------------------------------------------

def _plot_dielectric_and_optical(mat: str, out_dir: Path, phases: set[str]) -> None:
    Eg = _AI_PREDS[mat]["Eg_semi_soc_eV"]
    E0 = 1.5 * Eg   # resonance energy
    C  = 0.5 * Eg   # Lorentz broadening
    A  = 40.0        # amplitude (eV) — da ε₂_max ≈ 8-12

    eps_inf, eps_src = _fetch_jarvis_eps(mat)

    omega = np.linspace(0.01, 6.0, 2000)
    eps2 = _tauc_lorentz(omega, Eg, E0, C, A)
    print(f"  [K-K]  {mat}: calculando Kramers-Kronig (2000 pts)...", flush=True)
    eps1 = _kramers_kronig(omega, eps2) + (eps_inf - 1.0)

    if "dielectric" in phases:
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(6.5, 6), sharex=True)

        ax1.plot(omega, eps2, color="#e05c00", lw=1.5, label="ε₂(ω)")
        ax1.fill_between(omega, eps2, alpha=0.20, color="#e05c00")
        ax1.axvline(Eg, color="k", ls="--", lw=0.8)
        ax1.set_ylabel("ε₂")
        ax1.legend(fontsize=9)
        ax1.set_title(f"{mat}  —  Función dieléctrica AI (Tauc-Lorentz)")

        ax2.plot(omega, eps1, color="#2176AE", lw=1.5, label="ε₁(ω)")
        ax2.axhline(0.0, color="k", lw=0.5, ls=":")
        ax2.axvline(Eg, color="k", ls="--", lw=0.8)
        ax2.text(0.97, 0.97, f"ε_∞ = {eps_inf:.2f}\n({eps_src})",
                 transform=ax2.transAxes, ha="right", va="top", fontsize=8,
                 bbox=dict(boxstyle="round,pad=0.3", fc="white", alpha=0.8))
        ax2.set_xlabel("ħω (eV)")
        ax2.set_ylabel("ε₁")
        ax2.legend(fontsize=9)
        plt.tight_layout()
        _save(fig, out_dir, f"dielectric_ai_{mat}")
        print(f"  [diel] {mat}: ε_∞={eps_inf:.3f} ({eps_src}) → guardado")

    if "optical" in phases:
        eps_complex = (eps1 + 1j * eps2).astype(complex)
        sqrt_eps = np.sqrt(eps_complex)
        n_opt = sqrt_eps.real
        k_ext = sqrt_eps.imag
        # α en cm⁻¹: ħ=6.582e-16 eV·s, c=2.998e10 cm/s → ħc=1.973e-5 eV·cm
        alpha = 2.0 * omega * k_ext / (6.582e-16 * 2.998e10)

        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(6.5, 8), sharex=True)

        ax1.plot(omega, n_opt, color="#2176AE", lw=1.5)
        ax1.axvline(Eg, color="k", ls="--", lw=0.8)
        ax1.set_ylabel("n (refracción)")
        ax1.set_title(f"{mat}  —  Espectro óptico AI (Tauc-Lorentz)")

        ax2.plot(omega, k_ext, color="#e05c00", lw=1.5)
        ax2.axvline(Eg, color="k", ls="--", lw=0.8)
        ax2.set_ylabel("k (extinción)")

        mask = alpha > 0
        ax3.semilogy(omega[mask], alpha[mask], color="#7c5cbf", lw=1.5)
        ax3.axvline(Eg, color="k", ls="--", lw=0.8)
        ax3.set_xlabel("ħω (eV)")
        ax3.set_ylabel("α (cm⁻¹)")

        plt.tight_layout()
        _save(fig, out_dir, f"optical_ai_{mat}")
        idx2 = np.searchsorted(omega, 2.0)
        print(f"  [opt]  {mat}: n_max={n_opt.max():.2f}  "
              f"α(2 eV)={alpha[idx2]:.1e} cm⁻¹ → guardado")


# ---------------------------------------------------------------------------
# Worker para paralelismo (debe ser función de módulo, no lambda)
# ---------------------------------------------------------------------------

def _run_mat(args_tuple: tuple) -> str:
    mat, phases_frozen = args_tuple
    phases = set(phases_frozen)
    out = [f"── {mat} ──"]
    try:
        if "dos" in phases:
            plot_dos_ai(mat, OUT_DIR)
        if "pdos" in phases:
            plot_pdos_ai(mat, OUT_DIR)
        if "dielectric" in phases or "optical" in phases:
            _plot_dielectric_and_optical(mat, OUT_DIR, phases)
        out.append(f"  ✓ {mat} completo")
    except Exception as e:
        out.append(f"  ✗ {mat} ERROR: {e}")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    import multiprocessing as _mp
    from concurrent.futures import ProcessPoolExecutor, as_completed

    parser = argparse.ArgumentParser(
        description="Espectros AI (DOS, PDOS, dieléctrico, óptico) para top-8 perovskitas.")
    parser.add_argument("--mat", default="all",
                        help="Nombre de material o 'all' (default: all)")
    parser.add_argument("--phase", default="dos,pdos,dielectric,optical",
                        help="Fases separadas por coma: dos,pdos,dielectric,optical")
    parser.add_argument("--workers", type=int, default=0,
                        help="Procesos paralelos (0=auto: min(8, n_cpu))")
    args = parser.parse_args()

    mats = list(TOP8_MATS) if args.mat == "all" else [args.mat]
    phases = frozenset(p.strip() for p in args.phase.split(","))
    n_workers = args.workers or min(len(mats), _mp.cpu_count())

    print(f"AI spectra — materiales: {mats}")
    print(f"Fases: {set(phases)}  |  workers: {n_workers}")
    print(f"Salidas en: {OUT_DIR}\n")

    # Pre-calentar JARVIS cache en proceso principal (evita descarga concurrente)
    for mat in mats:
        if mat in JARVIS_JIDS:
            _fetch_jarvis_eps(mat)

    work = [(m, phases) for m in mats]
    if n_workers == 1 or len(mats) == 1:
        for item in work:
            print(_run_mat(item))
    else:
        with ProcessPoolExecutor(max_workers=n_workers) as ex:
            futures = {ex.submit(_run_mat, item): item[0] for item in work}
            for fut in as_completed(futures):
                print(fut.result())

    total_figs = len(mats) * len(phases) * 2
    print(f"\nListo. {len(mats)} mat × {len(phases)} fases = {total_figs} archivos")


if __name__ == "__main__":
    main()
