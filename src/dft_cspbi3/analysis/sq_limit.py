"""Shockley-Queisser detailed balance PV efficiency from DFT optical data.

Würfel formulation:
  A(E, d) = 1 − exp(−α(E) × d)
  J_sc = q × ∫ φ_AM1.5G(E) × A(E, d) dE               [mA/cm²]
  J₀   = q × (2π n² / h³c²) × ∫ E² × A(E,d) × exp(−E/kT) dE
  V_oc = (kT/q) × ln(J_sc / J₀ + 1)
  u_oc = q V_oc / (k_B T)
  FF   = (u_oc − ln(u_oc + 0.72)) / (u_oc + 1)   [Green 1982]
  PCE  = J_sc × V_oc × FF / P_in   (P_in = 100 mW/cm²)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .optical import OpticalResult
from .optical_device import beer_lambert_profile

logger = logging.getLogger(__name__)

# Physical constants
_Q_C        = 1.602176634e-19   # C
_KB_EV      = 8.617333262e-5    # eV/K
_H_EV_S     = 4.135667696e-15   # eV·s
_C_CM_S     = 2.99792458e10     # cm/s
_PIN_MW_CM2 = 100.0             # mW/cm²  (AM1.5G)

# ASTM G173-03 AM1.5G spectral irradiance in the wavelength domain.
# Source: ASTM G173-03 Table 1 (global tilt, selected wavelengths).
# Units: wavelength [nm], spectral irradiance [W/m²/nm].
# Converted to photon flux [photons/cm²/s/eV] on demand via _am15g_photon_flux().
_ASTM_NM = np.array([
    280, 300, 320, 340, 360, 380, 400, 420, 440, 460, 480, 500,
    520, 540, 560, 580, 600, 620, 640, 660, 680, 700, 720, 740,
    760, 780, 800, 830, 860, 900, 940, 980, 1020, 1080, 1160, 1240,
    1320, 1400, 1500, 1600, 1700, 1800, 2000, 2200, 2400, 3000, 4000,
], dtype=float)
_ASTM_WM2_NM = np.array([
    0.0000, 0.0041, 0.0289, 0.300,  0.190,  0.250,  0.490,  0.890,
    1.020,  1.000,  1.470,  1.625,  1.490,  1.470,  1.440,  1.310,
    1.560,  1.500,  1.490,  1.440,  1.420,  1.323,  1.120,  1.110,
    0.860,  1.050,  0.929,  0.870,  0.820,  0.659,  0.400,  0.460,
    0.270,  0.240,  0.440,  0.330,  0.210,  0.050,  0.200,  0.240,
    0.189,  0.138,  0.080,  0.060,  0.022,  0.004,  0.000,
], dtype=float)


def _am15g_photon_flux(omega_w: np.ndarray) -> np.ndarray:
    """Interpolate ASTM G173-03 AM1.5G photon flux onto omega_w [eV] grid.

    Converts the wavelength-domain spectral irradiance I(λ) [W/m²/nm] to
    photon flux φ(E) [photons/cm²/s/eV]:
      I_eV(E) = I_nm(λ) × |dλ/dE| = I_nm(λ) × λ² / 1240  [W/m²/eV]
      φ(E) = I_eV(E) / (E × q)  × 1e-4  [photons/cm²/s/eV]
    """
    _HC_EV_NM = 1239.84  # eV·nm  (h × c)
    # Convert wavelength table to energy [eV]
    e_tbl = _HC_EV_NM / _ASTM_NM            # eV, increasing λ → decreasing E
    # Convert irradiance W/m²/nm → W/m²/eV: multiply by |dλ/dE| = λ²/hc = λ²/(hc)
    i_ev_tbl = _ASTM_WM2_NM * _ASTM_NM**2 / _HC_EV_NM   # W/m²/eV
    # Sort by increasing energy for interpolation
    sort_idx = np.argsort(e_tbl)
    e_sorted = e_tbl[sort_idx]
    i_sorted = i_ev_tbl[sort_idx]
    # Photon flux [photons/cm²/s/eV]: I_eV / (E × q) × 1e-4 [m²/cm²]
    e_safe = np.where(e_sorted > 0, e_sorted, 1.0)
    phi_sorted = i_sorted / (e_safe * _Q_C) * 1e-4
    return np.interp(omega_w, e_sorted, phi_sorted, left=0.0, right=0.0)


def _sq_metrics(
    jsc_A: float,
    j0_A: float,
    T_K: float,
) -> tuple[float, float, float, float]:
    """Return (voc_V, ff, pce_pct, u_oc) from J_sc and J₀ [A/cm²]."""
    kT = _KB_EV * T_K
    if j0_A <= 0 or jsc_A <= 0:
        return 0.0, 0.0, 0.0, 0.0
    voc_V = kT * np.log(jsc_A / j0_A + 1.0)
    u_oc = voc_V / kT
    if u_oc <= 0.72:
        ff = 0.0
    else:
        ff = (u_oc - np.log(u_oc + 0.72)) / (u_oc + 1.0)
    # PCE [%]: J_sc [mA/cm²] × V_oc [V] × FF / P_in [mW/cm²] × 100
    # Since mA × V = mW, dividing by P_in [mW/cm²] gives fraction; ×100 → percent
    pce_pct = jsc_A * 1e3 * voc_V * ff / _PIN_MW_CM2 * 100.0
    return float(voc_V), float(ff), float(pce_pct), float(u_oc)


@dataclass
class SQResult:
    """Detailed Shockley-Queisser result for a given film thickness."""

    thickness_nm: float
    jsc_mA_cm2: float
    j0_mA_cm2: float
    voc_V: float
    ff: float
    pce_pct: float
    jsc_sq_ideal: float         # SQ J_sc for infinite-thickness step absorber [mA/cm²]
    pce_sq_ideal: float         # SQ PCE for infinite-thickness [%]
    generation_x: np.ndarray    # G(z) [photons/cm³/s], shape (n_x,)
    x_cm: np.ndarray            # depth axis [cm]
    thickness_scan: Optional[list]  # [(d_nm, jsc_mA_cm2, pce_pct), ...] or None
    flags: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        return (
            f"SQ(d={self.thickness_nm:.0f}nm): "
            f"J_sc={self.jsc_mA_cm2:.2f} mA/cm², "
            f"V_oc={self.voc_V:.3f} V, "
            f"FF={self.ff:.3f}, "
            f"PCE={self.pce_pct:.1f}%  "
            f"[SQ ideal: {self.pce_sq_ideal:.1f}%]"
        )


def compute_sq_limit(
    opt_result: OpticalResult,
    thickness_nm: float = 500.0,
    T_K: float = 300.0,
    n_x: int = 300,
    thickness_scan_nm: Optional[list] = None,
    onset_eV_override: Optional[float] = None,
) -> SQResult:
    """Compute detailed-balance SQ efficiency from DFT α(ω).

    Args:
        opt_result: OpticalResult from load_optical_result().
        thickness_nm: Film thickness for primary calculation [nm].
        T_K: Device temperature [K].
        n_x: Depth grid points for G(z) profile.
        thickness_scan_nm: Optional list of thicknesses for efficiency sweep.
        onset_eV_override: If given, zero out absorptance below this energy.
            Use this to apply the HSE06-corrected bandgap when the optical data
            was computed at the PBE level (avoids artificially large J_sc/J₀).

    Returns:
        SQResult with J_sc, J₀, V_oc, FF, PCE, G(z), and optional thickness scan.
    """
    flags: list[str] = []
    omega_w = opt_result.frequencies_eV
    alpha_w = opt_result.absorption_cm1

    if onset_eV_override is not None:
        flags.append(f"ONSET_OVERRIDE:{onset_eV_override:.3f}eV")

    kT = _KB_EV * T_K
    # h³c² [eV³·s·cm²]:  h [eV·s]³ × c [cm/s]²  →  units: eV³·s³ × cm²/s² = eV³·s·cm²
    h3c2 = _H_EV_S**3 * _C_CM_S**2
    prefactor_j0 = 2.0 * np.pi / h3c2   # 1/(eV³·s·cm²)

    # n² = ε∞ for Würfel J₀ (low-frequency dielectric constant)
    n_sq = float(opt_result.eps_inf) if opt_result.eps_inf is not None else 6.0
    if n_sq <= 0:
        n_sq = 1.0
        flags.append("EPS_INF_INVALID:using_n2=1")

    phi_w = _am15g_photon_flux(omega_w)

    # Effective onset: use override if given (HSE06-corrected gap), else from data
    eff_onset = onset_eV_override if onset_eV_override is not None else opt_result.absorption_onset_eV
    onset_mask = (omega_w >= eff_onset) if eff_onset is not None else np.ones(len(omega_w), bool)

    # ---- Primary calculation ------------------------------------------------
    thickness_cm = thickness_nm * 1e-7
    absorptance_w = (1.0 - np.exp(-alpha_w * thickness_cm)) * onset_mask

    # J_sc [A/cm²]
    jsc_A = _Q_C * float(np.trapezoid(phi_w * absorptance_w, omega_w))

    # J₀ [A/cm²] — guard exp overflow: E/kT up to 6/0.026 ≈ 230
    exp_term = np.exp(-np.clip(omega_w / kT, 0.0, 700.0))
    j0_A = (_Q_C * prefactor_j0 * n_sq
            * float(np.trapezoid(omega_w**2 * absorptance_w * exp_term, omega_w)))

    voc_V, ff, pce_pct, _ = _sq_metrics(jsc_A, j0_A, T_K)
    jsc_mA = jsc_A * 1e3
    j0_mA  = j0_A  * 1e3

    logger.info(
        "SQ(d=%.0f nm): J_sc=%.2f mA/cm², J₀=%.3e mA/cm², "
        "V_oc=%.3f V, FF=%.3f, PCE=%.1f%%",
        thickness_nm, jsc_mA, j0_mA, voc_V, ff, pce_pct,
    )

    # ---- G(z) generation profile -------------------------------------------
    dev = beer_lambert_profile(
        omega_w, alpha_w, thickness_cm,
        n_x=n_x,
        onset_eV=eff_onset,
    )

    # ---- Classical SQ ideal (step function at Eg, infinite thickness) -------
    Eg = onset_eV_override if onset_eV_override is not None else opt_result.absorption_onset_eV
    if Eg is None:
        fallback_mask = alpha_w > 1e3
        Eg = float(omega_w[fallback_mask][0]) if fallback_mask.any() else 1.0
        flags.append("EG_FROM_ALPHA_1E3")

    omega_ideal = np.linspace(0.0, 10.0, 10000)
    phi_ideal = _am15g_photon_flux(omega_ideal)
    step_abs  = (omega_ideal >= Eg).astype(float)

    jsc_ideal_A = _Q_C * float(np.trapezoid(phi_ideal * step_abs, omega_ideal))
    exp_ideal   = np.exp(-np.clip(omega_ideal / kT, 0.0, 700.0))
    j0_ideal_A  = (_Q_C * prefactor_j0
                   * float(np.trapezoid(omega_ideal**2 * step_abs * exp_ideal, omega_ideal)))
    voc_ideal, ff_ideal, pce_ideal, _ = _sq_metrics(jsc_ideal_A, j0_ideal_A, T_K)

    logger.info(
        "SQ ideal (Eg=%.2f eV): J_sc=%.2f mA/cm², V_oc=%.3f V, FF=%.3f, PCE=%.1f%%",
        Eg, jsc_ideal_A * 1e3, voc_ideal, ff_ideal, pce_ideal,
    )

    # ---- Thickness scan -----------------------------------------------------
    scan_list = None
    if thickness_scan_nm:
        scan_list = []
        for d_nm in thickness_scan_nm:
            d_cm = float(d_nm) * 1e-7
            abs_scan = (1.0 - np.exp(-alpha_w * d_cm)) * onset_mask
            jsc_s = _Q_C * float(np.trapezoid(phi_w * abs_scan, omega_w))
            j0_s  = (_Q_C * prefactor_j0 * n_sq
                     * float(np.trapezoid(omega_w**2 * abs_scan * exp_term, omega_w)))
            _, _, pce_s, _ = _sq_metrics(jsc_s, j0_s, T_K)
            scan_list.append((float(d_nm), float(jsc_s * 1e3), float(pce_s)))

    return SQResult(
        thickness_nm=float(thickness_nm),
        jsc_mA_cm2=float(jsc_mA),
        j0_mA_cm2=float(j0_mA),
        voc_V=float(voc_V),
        ff=float(ff),
        pce_pct=float(pce_pct),
        jsc_sq_ideal=float(jsc_ideal_A * 1e3),
        pce_sq_ideal=float(pce_ideal),
        generation_x=dev.generation_rate,
        x_cm=dev.x_cm,
        thickness_scan=scan_list,
        flags=flags,
    )
