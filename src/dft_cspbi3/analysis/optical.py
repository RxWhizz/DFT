"""Optical absorption spectrum via GPAW linear response (RPA/TDDFT).

Computes:
  ε₁(ω), ε₂(ω) — real and imaginary parts of the dielectric function
  n(ω), k(ω)    — refractive index and extinction coefficient
  α(ω)          — absorption coefficient [cm⁻¹]
  onset         — absorption onset energy (first ω where α > threshold)
  AM1.5G score  — visible-range absorption weighted by solar irradiance

GPAW response module: gpaw.response.df.DielectricFunction
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# α(ω) [cm⁻¹] = (ω / ħc) × ε₂(ω) / n(ω)   with ω in eV
_C_CM_PER_S = 2.998e10
_HBAR_EV_S  = 6.582e-16

# ASTM G173-03 AM1.5G — representative 18-point table, 0.31–4.50 eV [W/m²/eV]
# Derived from the standard wavelength table (280–4000 nm) using E = hc/λ.
_AM15G_EV = np.array([
    0.31, 0.50, 0.75, 1.00, 1.25, 1.50, 1.75,
    2.00, 2.25, 2.50, 2.75, 3.00, 3.25, 3.50,
    3.75, 4.00, 4.25, 4.50,
])
_AM15G_WATT = np.array([
      8,   52,  180,  430,  650,  740,  750,
    680,  600,  520,  440,  360,  270,  190,
    120,   70,   35,   12,
], dtype=float)

# Normalisation reference: mean irradiance over the AM1.5G range [W/m²/eV]
_AM15G_NORM = float(np.trapezoid(_AM15G_WATT, _AM15G_EV))


@dataclass
class OpticalResult:
    """Optical dielectric function and absorption spectrum."""

    frequencies_eV: np.ndarray          # photon energy axis (eV)
    eps1: np.ndarray                     # Re(ε(ω))
    eps2: np.ndarray                     # Im(ε(ω))
    absorption_cm1: np.ndarray           # α(ω) in cm⁻¹
    n_omega: np.ndarray                  # Re(√ε) — refractive index
    k_omega: np.ndarray                  # Im(√ε) — extinction coefficient
    absorption_onset_eV: Optional[float] # onset energy (α > threshold)
    eps_inf: Optional[float]             # ε₁(ω→0)
    alpha_at_eV: dict                    # α [cm⁻¹] at {1.5, 2.0, 2.5, 3.0} eV
    visible_absorption_score: Optional[float]  # AM1.5G-weighted integral, [0,1]
    scissor_eV: Optional[float]          # eshift applied to conduction bands
    flags: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        eps_str   = f"ε∞={self.eps_inf:.3f}"   if self.eps_inf   is not None else "ε∞=N/A"
        onset_str = f"onset={self.absorption_onset_eV:.2f} eV" if self.absorption_onset_eV else "onset=N/A"
        sc_str    = f"scissor={self.scissor_eV:+.3f} eV" if self.scissor_eV else "scissor=none"
        score_str = f"AM1.5G score={self.visible_absorption_score:.3f}" if self.visible_absorption_score is not None else ""
        parts = [eps_str, onset_str, sc_str]
        if score_str:
            parts.append(score_str)
        return "Optical: " + ", ".join(parts)


def _am15g_score(omega_w: np.ndarray, alpha_w: np.ndarray, onset_eV: Optional[float]) -> float:
    """AM1.5G-weighted absorption score normalised to [0, 1].

    Integrates α(ω) × I_AM1.5G(ω) over ω ≥ onset and divides by a reference
    α_ref = 1×10⁵ cm⁻¹ × ∫I_AM1.5G dω so that a material with α = 10⁵ cm⁻¹
    everywhere above onset scores 1.0.
    """
    irr_w = np.interp(omega_w, _AM15G_EV, _AM15G_WATT, left=0.0, right=0.0)
    if onset_eV is not None:
        mask = omega_w >= onset_eV
    else:
        mask = np.zeros(len(omega_w), dtype=bool)
    numerator = float(np.trapezoid(alpha_w * irr_w * mask, omega_w))
    denominator = _AM15G_NORM * 1e5   # reference: α_ref × ∫I dω
    return min(numerator / denominator, 1.0) if denominator > 0 else 0.0


def compute_optical_spectrum(
    scf_gpw: str | Path,
    step_dir: Path,
    omega_max_eV: float = 6.0,
    d_omega_eV: float = 0.025,
    eta_eV: float = 0.1,
    onset_threshold_cm1: float = 1e4,
    scissor_eV: Optional[float] = None,
    alpha_sample_eV: tuple = (1.5, 2.0, 2.5, 3.0),
) -> OpticalResult:
    """Compute the optical dielectric function using GPAW's linear response.

    Uses the Random Phase Approximation (RPA) to compute ε(ω) at q→0.
    Reads from an existing SCF .gpw and performs a non-self-consistent response
    calculation — typically 1–4 h for a 5-atom cell with a 6×6×6 k-mesh.

    Args:
        scf_gpw: Path to converged SCF .gpw checkpoint.
        step_dir: Directory for output files.
        omega_max_eV: Maximum photon energy (eV).
        d_omega_eV: Frequency step (eV).
        eta_eV: Lorentzian broadening (eV).
        onset_threshold_cm1: α threshold defining absorption onset.
        scissor_eV: Rigid conduction-band shift (eshift) in eV. Auto-detected
            from HSE06 vs PBE gap in _run_optical; None = no correction.
        alpha_sample_eV: Energies at which to report α explicitly.

    Returns:
        OpticalResult with ε(ω), n(ω), k(ω), α(ω), and PV metrics.
    """
    step_dir = Path(step_dir)
    step_dir.mkdir(parents=True, exist_ok=True)
    flags: list[str] = []

    omega_w = np.arange(0.0, omega_max_eV + d_omega_eV, d_omega_eV)

    try:
        from gpaw.response.df import DielectricFunction

        df_kwargs: dict = dict(
            calc=str(scf_gpw),
            frequencies=omega_w,
            eta=eta_eV,
            hilbert=False,   # linear freq array requires hilbert=False (NonLinearFrequencyDescriptor needed otherwise)
            txt=str(step_dir / "optical.txt"),
        )
        if scissor_eV is not None:
            df_kwargs["eshift"] = float(scissor_eV)
            flags.append(f"SCISSOR:{scissor_eV:+.3f}eV")

        df = DielectricFunction(**df_kwargs)

        eps1_w, eps2_w = df.get_dielectric_function(
            xc="RPA",
            q_c=[0, 0, 0],
            filename=str(step_dir / "dielectric_function.csv"),
        )

        eps1_w = np.asarray(eps1_w).real
        eps2_w = np.asarray(eps2_w).real

    except Exception as exc:
        flags.append(f"RPA_FAILED:{exc}")
        logger.warning("RPA dielectric function failed: %s", exc)
        zeros = np.zeros_like(omega_w)
        return OpticalResult(
            frequencies_eV=omega_w,
            eps1=np.ones_like(omega_w),
            eps2=zeros,
            absorption_cm1=zeros,
            n_omega=np.ones_like(omega_w),
            k_omega=zeros,
            absorption_onset_eV=None,
            eps_inf=None,
            alpha_at_eV={e: 0.0 for e in alpha_sample_eV},
            visible_absorption_score=None,
            scissor_eV=scissor_eV,
            flags=flags,
        )

    # n(ω) and k(ω) from complex refractive index √(ε₁ + i·ε₂)
    eps_complex = eps1_w + 1j * eps2_w
    sqrt_eps = np.sqrt(eps_complex)
    n_w = np.real(sqrt_eps)
    k_w = np.imag(sqrt_eps)

    # α(ω) [cm⁻¹] = (ω / ħc) × ε₂ / n  — guard against n→0 at ω=0
    n_safe = np.where(n_w < 1e-6, 1.0, n_w)
    alpha_w = (omega_w / (_HBAR_EV_S * _C_CM_PER_S)) * eps2_w / n_safe

    # Absorption onset
    onset_mask = alpha_w > onset_threshold_cm1
    onset_eV = float(omega_w[onset_mask][0]) if onset_mask.any() else None

    # ε∞: ε₁ at first non-zero frequency
    eps_inf = float(eps1_w[1]) if len(eps1_w) > 1 else None

    # α at requested discrete energies
    alpha_at_eV = {float(e): float(np.interp(e, omega_w, alpha_w)) for e in alpha_sample_eV}

    # AM1.5G-weighted visible absorption score
    score = _am15g_score(omega_w, alpha_w, onset_eV)

    # Save outputs
    np.save(str(step_dir / "optical_frequencies.npy"), omega_w)
    np.save(str(step_dir / "eps1.npy"),          eps1_w)
    np.save(str(step_dir / "eps2.npy"),          eps2_w)
    np.save(str(step_dir / "n_omega.npy"),        n_w)
    np.save(str(step_dir / "k_omega.npy"),        k_w)
    np.save(str(step_dir / "absorption_cm1.npy"), alpha_w)

    result = OpticalResult(
        frequencies_eV=omega_w,
        eps1=eps1_w,
        eps2=eps2_w,
        absorption_cm1=alpha_w,
        n_omega=n_w,
        k_omega=k_w,
        absorption_onset_eV=onset_eV,
        eps_inf=eps_inf,
        alpha_at_eV=alpha_at_eV,
        visible_absorption_score=score,
        scissor_eV=scissor_eV,
        flags=flags,
    )
    logger.info("Optical spectrum: %s", result.summary)
    return result


def load_optical_result(step_dir: Path) -> Optional[OpticalResult]:
    """Load a previously computed optical result from saved .npy files."""
    step_dir = Path(step_dir)
    omega_path = step_dir / "optical_frequencies.npy"
    if not omega_path.exists():
        return None

    omega_w = np.load(str(omega_path))
    eps1_w  = np.load(str(step_dir / "eps1.npy"))
    eps2_w  = np.load(str(step_dir / "eps2.npy"))
    alpha_w = np.load(str(step_dir / "absorption_cm1.npy"))

    n_path = step_dir / "n_omega.npy"
    k_path = step_dir / "k_omega.npy"
    if n_path.exists():
        n_w = np.load(str(n_path))
        k_w = np.load(str(k_path))
    else:
        sqrt_eps = np.sqrt(eps1_w + 1j * eps2_w)
        n_w = np.real(sqrt_eps)
        k_w = np.imag(sqrt_eps)

    onset_mask = alpha_w > 1e4
    onset_eV   = float(omega_w[onset_mask][0]) if onset_mask.any() else None
    eps_inf    = float(eps1_w[1]) if len(eps1_w) > 1 else None

    alpha_at_eV = {e: float(np.interp(e, omega_w, alpha_w)) for e in (1.5, 2.0, 2.5, 3.0)}
    score = _am15g_score(omega_w, alpha_w, onset_eV)

    return OpticalResult(
        frequencies_eV=omega_w,
        eps1=eps1_w,
        eps2=eps2_w,
        absorption_cm1=alpha_w,
        n_omega=n_w,
        k_omega=k_w,
        absorption_onset_eV=onset_eV,
        eps_inf=eps_inf,
        alpha_at_eV=alpha_at_eV,
        visible_absorption_score=score,
        scissor_eV=None,
    )
