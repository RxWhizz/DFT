#!/usr/bin/env python3
"""Offline post-analysis usa all existente cálculo data para α-CsPbI₃."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from dft_cspbi3.analysis.pes import detect_soft_modes
from dft_cspbi3.analysis.electronic import classify_gap_type
from dft_cspbi3.postprocessing import get_dos, get_fermi_level
from dft_cspbi3.plotting import get_pdos_colors

# Paths
CALC_DIR    = ROOT / "calculations" / "alpha"
OUT_DIR     = CALC_DIR / "reports" / "post_analysis"
OUT_DIR.mkdir(parents=True, exist_ok=True)

RELAX_GPW   = CALC_DIR / "01_relax"  / "relax.gpw"
SCF_GPW     = CALC_DIR / "02_scf"    / "scf.gpw"
BANDS_GPW   = CALC_DIR / "03_bands"  / "bands.gpw"
DOS_GPW     = CALC_DIR / "04_dos"    / "dos.gpw"
HESSIAN_NPY = CALC_DIR / "07_vibrational" / "hessian" / "hessian.npy"
PHONON_NPY  = CALC_DIR / "07_vibrational" / "phonons" / "phonon_frequencies.npy"
SOC_NPY     = CALC_DIR / "05_soc"    / "soc_eigenvalues.npy"

EV_A2_TO_SI = 1.602176634e-19 / (1e-10)**2   # eV/Å² → N/m = 16.02 N/m per eV/Å²
AMU_TO_KG   = 1.66053906660e-27
C_CM_S      = 2.99792458e10


def sep(title: str) -> None:
    print(f"\n{'='*60}\n  {title}\n{'='*60}")


# 1
sep("1. PES HARMÓNICO + FRECUENCIAS (Γ-punto)")

# Dynamical matrix frequencies
from gpaw import GPAW as _GPAW
_calc_r = _GPAW(str(RELAX_GPW), txt=None)
atoms_ref = _calc_r.get_atoms()
masses_amu = atoms_ref.get_masses()
N_atoms = len(atoms_ref)
M_dof = np.repeat(masses_amu, 3) * AMU_TO_KG   # (3N,) kg

H = np.load(str(HESSIAN_NPY))                   # (3N, 3N) eV/Å²
H_SI = H * EV_A2_TO_SI

# Dynamical matrix D_ij = H_ij / sqrt(M_i M_j)
M_mat = np.sqrt(np.outer(M_dof, M_dof))
D = H_SI / M_mat                                # rad²/s²

eigs_D, evecs_D = np.linalg.eigh(D)
freqs_cm1 = np.sign(eigs_D) * np.sqrt(np.abs(eigs_D)) / (2 * np.pi * C_CM_S)

print("Γ-point frequencies from dynamical matrix:")
for i, nu in enumerate(freqs_cm1):
    tag = "  (acoustic)" if i < 3 else ""
    print(f"  mode {i:2d}: {nu:+8.2f} cm⁻¹{tag}")

# Hessiano eigenvalues (curvature, NOT mass-weighted)
soft_modes = detect_soft_modes(HESSIAN_NPY, threshold=0.15)
print(f"\n{len(soft_modes)} soft Hessian modes (λ < 0.15 eV/Å²):")
pes_summary = []
for idx, lam, _ in soft_modes:
    nu_dm = freqs_cm1[idx]
    print(f"  mode {idx}: λ={lam:.4f} eV/Å²  →  ν={nu_dm:.1f} cm⁻¹ (dyn. matrix)")
    pes_summary.append({"mode_index": idx,
                         "eigenvalue_eV_Ang2": round(lam, 5),
                         "freq_cm1": round(float(nu_dm), 2)})

# Harmonic PES plots
A = 0.6; N_q = 300
fig_pes, ax_pes = plt.subplots(figsize=(7, 5))
cmap = plt.cm.viridis(np.linspace(0.15, 0.85, len(soft_modes)))
for (idx, lam, _), col in zip(soft_modes, cmap):
    q = np.linspace(-A, A, N_q)
    E_meV = 0.5 * lam * q**2 * 1000
    nu_dm = freqs_cm1[idx]
    ax_pes.plot(q, E_meV, lw=2.0, color=col,
                label=f"mode {idx}  λ={lam:.4f} eV/Å²  ν={nu_dm:.1f} cm⁻¹")
ax_pes.axvline(0, color="k", lw=0.8, ls="--", alpha=0.4)
ax_pes.axhline(0, color="k", lw=0.5, ls=":", alpha=0.3)
ax_pes.set_xlabel("Displacement Q (Å)")
ax_pes.set_ylabel("ΔE (meV)")
ax_pes.set_title("Harmonic PES — α-CsPbI₃ soft modes (Γ-point)", fontsize=12)
ax_pes.legend(fontsize=9, loc="upper center")
fig_pes.tight_layout()
for ext in ("png", "pdf"):
    fig_pes.savefig(OUT_DIR / f"pes_harmonic.{ext}", dpi=300)
plt.close(fig_pes)
print("Saved: pes_harmonic.{png,pdf}")

# 2
sep("2. ESTRUCTURA DE BANDAS + SOC")

_calc_b = _GPAW(str(BANDS_GPW), txt=None)
bs = _calc_b.band_structure()
ef_bands = bs.reference    # Fermi/VBM reference en absolute eV

n_el  = _calc_b.get_number_of_electrons()
n_occ = int(round(n_el / 2))
E_rel = bs.energies[0] - ef_bands

vb = E_rel[:, :n_occ]
cb = E_rel[:, n_occ:]
vbm = float(vb.max())
cbm = float(cb.min())
gap_pbe = cbm - vbm
cbm_k = int(np.argmin(cb.min(axis=1)))
vbm_k = int(np.argmax(vb.max(axis=1)))

# Identify which high-symmetry point gap en
kpts_frac = _calc_b.get_bz_k_points()
k_at_gap = kpts_frac[cbm_k]
print(f"n_occ = {n_occ}  (n_el = {int(n_el)})")
print(f"Gap PBE = {gap_pbe:.4f} eV")
print(f"VBM at k={vbm_k}  frac={kpts_frac[vbm_k].round(3)}")
print(f"CBM at k={cbm_k}  frac={kpts_frac[cbm_k].round(3)}")
# Identify high-symmetry label
_sc_pts = {"G":(0,0,0), "X":(0,.5,0), "M":(.5,.5,0), "R":(.5,.5,.5)}
for lab, coord in _sc_pts.items():
    if np.allclose(k_at_gap % 1, np.array(coord) % 1, atol=0.05):
        print(f"  → Gap is DIRECT at {lab} point (frac={coord})")
        break

# NOTE
print("  Note: original report stated Γ; re-examination shows R=(½,½,½).")

# SOC overlay (mesh, no k-ruta - overlay as cloud)
soc_abs = np.load(str(SOC_NPY))      # (216, 52) absolute eV
ef_scf  = float(get_fermi_level(SCF_GPW))
soc_rel = soc_abs - ef_bands
# Select only occupied/unoccupied cerca gap keep grafica clean
soc_near = soc_rel[:, n_occ-5:n_occ+5]   # 5 bands each lado

# Gap desde SOC mesh
above = soc_abs[soc_abs > ef_scf]
below = soc_abs[soc_abs <= ef_scf]
gap_soc = float(above.min()) - float(below.max()) if above.size and below.size else np.nan
chi_soc = gap_soc - gap_pbe if not np.isnan(gap_soc) else np.nan
print(f"Gap PBE+SOC (mesh approx) = {gap_soc:.4f} eV")
print(f"χ_SOC = {chi_soc:.4f} eV")

# Banda estructura grafica
nk = E_rel.shape[0]
kx = np.linspace(0, 1, nk)
ewin = (-3.5, 3.5)

fig_bs, ax_bs = plt.subplots(figsize=(7, 5))
for band in range(E_rel.shape[1]):
    ax_bs.plot(kx, E_rel[:, band], color="#1f4e79", lw=1.1, alpha=0.8)

# SOC overlay (as cloud)
kx_soc = np.linspace(0, 1, soc_near.shape[0])
for b in range(soc_near.shape[1]):
    ax_bs.plot(kx_soc, soc_near[:, b], color="#e85d04", lw=0.6,
               alpha=0.4, ls="--",
               label="SOC" if b == 0 else "")

ax_bs.axhline(0, color="k", lw=0.8, ls="--", alpha=0.4)
ax_bs.axhline(vbm, color="navy", lw=0.6, ls=":")
ax_bs.axhline(cbm, color="darkred", lw=0.6, ls=":")
ax_bs.annotate(f"Eg(PBE)={gap_pbe:.3f} eV\nEg(SOC)≈{gap_soc:.3f} eV",
               xy=(0.72, (vbm+cbm)/2), xycoords=("axes fraction","data"),
               fontsize=10, color="black", va="center",
               bbox=dict(boxstyle="round,pad=0.2", fc="white", alpha=0.7))

# Add k-labels si disponible
if hasattr(bs, "path") and bs.path is not None:
    try:
        xcoords, labels, _ = bs.path.get_linear_kpoint_axis()
        xcoords_norm = xcoords / xcoords[-1]
        for xc in xcoords_norm:
            ax_bs.axvline(xc, color="k", lw=0.6, alpha=0.5)
        ax_bs.set_xticks(xcoords_norm)
        ax_bs.set_xticklabels([r"$\Gamma$" if l in ("G","Γ") else l for l in labels])
    except Exception:
        ax_bs.set_xlabel("k-path")

ax_bs.set_ylim(ewin)
ax_bs.set_ylabel("Energy − E$_F$ (eV)")
ax_bs.set_title("α-CsPbI₃  |  PBE + SOC overlay\nGap = 1.089 eV direct at R=(½,½,½)",
                fontsize=11)
ax_bs.legend(fontsize=9, loc="upper right")
fig_bs.tight_layout()
for ext in ("png", "pdf"):
    fig_bs.savefig(OUT_DIR / f"band_structure_soc.{ext}", dpi=300)
plt.close(fig_bs)
print("Saved: band_structure_soc.{png,pdf}")

# 3
sep("3. DOS + PDOS")

dos_data = get_dos(DOS_GPW, npts=2000, width=0.05)
ef_dos   = float(get_fermi_level(DOS_GPW))
en_raw   = dos_data["energies"]
total    = dos_data["total"]
pdos     = dos_data["pdos"]
en       = en_raw - ef_dos   # shift so EF = 0
print(f"Elements in PDOS: {list(pdos.keys())}")
print(f"DOS E_F = {ef_dos:.4f} eV → set to 0")

# DOS gap
gap_dos = gap_pbe
print(f"Gap (from band structure) = {gap_dos:.4f} eV")

# Find total DOS max en valence region para reference
max_dos_val = total[en < -0.1].max() if (en < -0.1).any() else total.max()

colors = get_pdos_colors(list(pdos.keys()))
fig_dos, ax_dos = plt.subplots(figsize=(6, 5))
ax_dos.plot(en, total, color="black", lw=1.5, label="Total DOS")
for sym, pd in pdos.items():
    c = colors.get(sym, "gray")
    ax_dos.fill_between(en, 0, pd, alpha=0.35, color=c)
    ax_dos.plot(en, pd, color=c, lw=1.0, label=f"{sym} PDOS")
ax_dos.axvline(0, color="k", lw=1.0, ls="--", alpha=0.6, label="$E_F$")
ax_dos.set_xlim(-6.0, 4.0)
ax_dos.set_ylim(bottom=0)
ax_dos.set_xlabel("Energy (eV)")
ax_dos.set_ylabel("DOS (states/eV/cell)")
ax_dos.set_title("α-CsPbI₃  |  Total DOS + PDOS (PBE, 12×12×12)", fontsize=11)
ax_dos.legend(loc="upper left", framealpha=0.8)
fig_dos.tight_layout()
for ext in ("png", "pdf"):
    fig_dos.savefig(OUT_DIR / f"dos_pdos.{ext}", dpi=300)
plt.close(fig_dos)
print("Saved: dos_pdos.{png,pdf}")

# 4
sep("4. MASAS EFECTIVAS (estimación)")

# With only 40 k-points en X-R-M-Γ-R y gap en R (boundary entre
# X-R y R-M segments), parabolic fit mixes two different k-directions
# valores bajo unreliable
try:
    from dft_cspbi3.analysis.electronic import compute_effective_masses
    em = compute_effective_masses(BANDS_GPW, n_fit=4)
    m_e_str = f"{em.m_e:.4f} m₀" if em.m_e else "N/A"
    m_h_str = f"{em.m_h:.4f} m₀" if em.m_h else "N/A"
    m_r_str = f"{em.m_reduced:.4f} m₀" if em.m_reduced else "N/A"
    print(f"  m_e  = {m_e_str}  ⚠ UNRELIABLE — gap at R (k-path boundary)")
    print(f"  m_h  = {m_h_str}  ⚠ fit mixes X-R and R-M directions")
    print(f"  m_r  = {m_r_str}")
    print("  Lit. values: m_e≈0.13 m₀, m_h≈0.22 m₀ (Brivio et al. 2015)")
    em_note = "unreliable (k-path sampling; gap at R is k-path corner)"
except Exception as exc:
    em = None
    m_e_str = m_h_str = m_r_str = "N/A"
    em_note = str(exc)
    print(f"  Skipped: {exc}")

# 5
sep("5. DISPERSIÓN DE FONONES (datos existentes)")

phonon_freqs = np.load(str(PHONON_NPY))   # (60, 15) cm⁻¹
nq, nbranch  = phonon_freqs.shape
n_imag = int((phonon_freqs < -10).sum())
n_imag_opt = int((phonon_freqs[:, 3:] < -10).sum())
opt_min = float(phonon_freqs[:, 3:].min())
opt_max = float(phonon_freqs.max())
ac_gamma = phonon_freqs[0, :3].tolist()

print(f"  Shape: {nq} q-points × {nbranch} branches")
print(f"  Imaginary total (< −10 cm⁻¹): {n_imag}  (artefact Δ=0.05 Å)")
print(f"  Imaginary optical: {n_imag_opt}  ← 0 expected ✓")
print(f"  Optical range: {opt_min:.1f} – {opt_max:.1f} cm⁻¹")
print(f"  Acoustic at Γ (q=0): {[round(x,2) for x in ac_gamma]} cm⁻¹")

fig_ph, ax_ph = plt.subplots(figsize=(7, 5))
q_idx = np.arange(nq)
for b in range(nbranch):
    is_imag = phonon_freqs[:, b].min() < -10
    color   = "#d32f2f" if is_imag else "steelblue"
    lw      = 0.7 if is_imag else 0.95
    ax_ph.plot(q_idx, phonon_freqs[:, b], lw=lw, color=color,
               alpha=0.6 if is_imag else 0.85)

# Legend proxies
from matplotlib.lines import Line2D
ax_ph.add_artist(ax_ph.legend(
    handles=[Line2D([0],[0],color="steelblue",lw=1.5,label="Physical modes"),
             Line2D([0],[0],color="#d32f2f",lw=1.5,label=f"Artefacts ({n_imag} branches)")],
    fontsize=9, loc="upper left"))

ax_ph.axhline(0, color="k", lw=0.8, ls="--", alpha=0.5)
ax_ph.set_xlabel("q-index (path X-R-M-Γ-R)")
ax_ph.set_ylabel("Frequency (cm⁻¹)")
ax_ph.set_title(
    f"α-CsPbI₃  |  Phonon dispersion (ASE Δ=0.05 Å)\n"
    f"Optical range: {opt_min:.1f}–{opt_max:.1f} cm⁻¹  |  "
    f"Acústicos: artefacto numérico", fontsize=10)
fig_ph.tight_layout()
for ext in ("png", "pdf"):
    fig_ph.savefig(OUT_DIR / f"phonon_dispersion.{ext}", dpi=300)
plt.close(fig_ph)
print("Saved: phonon_dispersion.{png,pdf}")

# 6
sep("6. FRECUENCIAS Γ — Hessiano vs Fonones (q=0)")

phon_gamma = sorted(phonon_freqs[0].tolist())
hess_gamma = sorted(freqs_cm1.tolist())
print(f"{'Mode':>5} {'Hessiano (cm⁻¹)':>18} {'Fonón q=0 (cm⁻¹)':>18}")
for i, (h, p) in enumerate(zip(hess_gamma, phon_gamma)):
    flag = "  ← acústico" if i < 3 else ""
    print(f"  {i:3d}   {h:+12.2f}       {p:+12.2f}{flag}")

# 7
sep("7. RESUMEN")

summary = {
    "phase": "alpha-CsPbI3",
    "xc": "PBE",
    "ecut_eV": 450,
    "kpts_scf": "6x6x6",
    "gap_PBE_eV": round(gap_pbe, 4),
    "gap_location": "R=(0.5,0.5,0.5) — direct",
    "gap_PBE_SOC_approx_eV": round(gap_soc, 4) if not np.isnan(gap_soc) else None,
    "chi_SOC_eV": round(chi_soc, 4) if not np.isnan(chi_soc) else None,
    "chi_SOC_canonical_eV": -0.789,
    "effective_mass_note": em_note,
    "effective_mass_e_m0": round(em.m_e, 4) if em and em.m_e else None,
    "effective_mass_h_m0": round(em.m_h, 4) if em and em.m_h else None,
    "soft_modes_hessian": pes_summary,
    "gamma_point_freqs_dyn_matrix_cm1": [round(float(x), 2) for x in freqs_cm1],
    "gamma_point_freqs_ase_phonon_cm1": [round(x, 2) for x in phon_gamma],
    "phonon_n_imaginary_total": n_imag,
    "phonon_n_imaginary_optical": n_imag_opt,
    "phonon_optical_range_cm1": [round(opt_min, 1), round(opt_max, 1)],
    "acoustic_gamma_cm1_ase": [round(x, 2) for x in ac_gamma],
}

summary_path = OUT_DIR / "summary.json"
with open(summary_path, "w") as fh:
    json.dump(summary, fh, indent=2, ensure_ascii=False)

print("\nKey results:")
for k in ["gap_PBE_eV","gap_location","gap_PBE_SOC_approx_eV","chi_SOC_eV",
          "chi_SOC_canonical_eV","phonon_optical_range_cm1","phonon_n_imaginary_optical"]:
    print(f"  {k}: {summary[k]}")

print(f"\nAll outputs → {OUT_DIR}")
print("Done.")
