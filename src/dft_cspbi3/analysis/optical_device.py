"""Optical dispositivo simulation."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# AM1.5G photon flux densidad dN/dω [photons/cm²/s/eV] desde irradiance tabla
# Derived as I_AM1.5G(eV) / (eV × q) para mismo 18-point tabla usado en óptico.py
_AM15G_EV = np.array([
    0.31, 0.50, 0.75, 1.00, 1.25, 1.50, 1.75,
    2.00, 2.25, 2.50, 2.75, 3.00, 3.25, 3.50,
    3.75, 4.00, 4.25, 4.50,
])
_Q_EV = 1.602e-19          # J per eV
# Irradiance en W/m² per eV → convert photons/cm²/s/eV
_AM15G_WATT_M2 = np.array([
      8,   52,  180,  430,  650,  740,  750,
    680,  600,  520,  440,  360,  270,  190,
    120,   70,   35,   12,
], dtype=float)
# [W/m²/eV] / [J/photon] → [photons/m²/s/eV] → [photons/cm²/s/eV] × 1e-4
_AM15G_FLUX = _AM15G_WATT_M2 / (_AM15G_EV * _Q_EV) * 1e-4


@dataclass
class DeviceOpticsResult:
    """Optical dispositivo simulation salida."""

    thickness_cm: float
    x_cm: np.ndarray
    generation_rate: np.ndarray       # G(x) [photons/cm³/s]
    absorbed_photon_flux: float       # ∫G(x)dx [photons/cm²/s]
    incident_photon_flux: float       # total AM1.5G flux sobre onset [photons/cm²/s]
    optical_efficiency: float         # η_opt = absorbed / incident ∈ [0,1]
    jsc_limit_mA_cm2: float           # J_sc assuming IQE=1 [mA/cm²]
    flags: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        return (
            f"Device optics: d={self.thickness_cm*1e4:.0f} nm, "
            f"η_opt={self.optical_efficiency:.3f}, "
            f"J_sc(limit)={self.jsc_limit_mA_cm2:.2f} mA/cm²"
        )


def _photon_flux_am15g(omega_w: np.ndarray) -> np.ndarray:
    """Interpolate AM1.5G photon flux [photons/cm²/s/eV] onto omega_w grid."""
    return np.interp(omega_w, _AM15G_EV, _AM15G_FLUX, left=0.0, right=0.0)


def beer_lambert_profile(
    omega_w: np.ndarray,
    alpha_w: np.ndarray,
    thickness_cm: float,
    n_x: int = 500,
    onset_eV: Optional[float] = None,
) -> DeviceOpticsResult:
    """Calcula generación rate profile G(x) via Beer-Lambert law."""
    flags: list[str] = []

    if onset_eV is None:
        onset_mask = alpha_w > 1e4
        onset_eV = float(omega_w[onset_mask][0]) if onset_mask.any() else float(omega_w[1])

    x_cm = np.linspace(0.0, thickness_cm, n_x)

    # AM1.5G photon flux per energía
    flux_w = _photon_flux_am15g(omega_w)   # [photons/cm²/s/eV]

    # Zero out sub-onset photons
    active = omega_w >= onset_eV
    flux_w = flux_w * active

    # G(x) = ∫ α(ω) × I₀(ω) × exp(−α(ω)×x) dω
    # I₀(ω) = flux densidad en x=0 [photons/cm²/s/eV]
    # Shape
    alpha_col = alpha_w[:, np.newaxis]     # (N_omega, 1)
    x_row = x_cm[np.newaxis, :]            # (1, N_x)
    # Intensity profile
    intensity_profile = flux_w[:, np.newaxis] * np.exp(-alpha_col * x_row)

    # dG/dx = α × I → integrate over ω usa trapezoidal rule
    # G(x) = ∫ α(ω) × I(x,ω) dω [photons/cm³/s]
    d_omega = np.gradient(omega_w)
    generation_profile = np.sum(
        alpha_col * intensity_profile * d_omega[:, np.newaxis],
        axis=0,
    )

    # Total absorbed photon flux [photons/cm²/s] = ∫G(x)dx
    absorbed_flux = float(np.trapezoid(generation_profile, x_cm))

    # Total incident flux sobre onset
    incident_flux = float(np.trapezoid(flux_w, omega_w))
    if incident_flux < 1.0:
        flags.append("ZERO_INCIDENT_FLUX: onset may be above AM1.5G range")
        incident_flux = max(incident_flux, 1.0)

    eta_opt = min(absorbed_flux / incident_flux, 1.0)

    # J_sc limit = q × absorbed_flux [mA/cm²], assuming IQE=1
    q_C = 1.602e-19
    jsc = absorbed_flux * q_C * 1e3   # A/cm² → mA/cm²

    result = DeviceOpticsResult(
        thickness_cm=thickness_cm,
        x_cm=x_cm,
        generation_rate=generation_profile,
        absorbed_photon_flux=absorbed_flux,
        incident_photon_flux=incident_flux,
        optical_efficiency=eta_opt,
        jsc_limit_mA_cm2=jsc,
        flags=flags,
    )
    logger.info("Beer-Lambert: %s", result.summary)
    return result


def multilayer_tmm_profile(
    omega_w: np.ndarray,
    layers: list[dict],
    n_x: int = 500,
    onset_eV: Optional[float] = None,
) -> DeviceOpticsResult:
    """Calcula G(x) usa coherent 2×2 Transfer Matrix Método."""
    flags: list[str] = ["TMM_COHERENT"]

    # Identify absorber layer (largest ∫α dω)
    integrals = [float(np.trapezoid(L["alpha"], omega_w)) for L in layers]
    abs_idx = int(np.argmax(integrals))
    absorber = layers[abs_idx]
    thickness_cm = float(absorber["d_cm"])

    if onset_eV is None:
        onset_mask = absorber["alpha"] > 1e4
        onset_eV = float(omega_w[onset_mask][0]) if onset_mask.any() else float(omega_w[1])

    active = omega_w >= onset_eV
    flux_w = _photon_flux_am15g(omega_w) * active

    # Proper coherent 2×2 TMM (normal incidence, TE=TM)
    # For each frequency
    # Fase thickness
    # ω en eV, ħc = 1.973e-5 eV·cm
    # Characteristic matrix:
    # Mⱼ = [[cos δⱼ, (i/ηⱼ) sin δⱼ],
    # [iηⱼ sin δⱼ, cos δⱼ ]] where ηⱼ = ñⱼ (normal incidence)
    # Reflection amplitude (η_inc = η_sub = 1, both air):
    # r = (m₁₁ + m₁₂ − m₂₁ − m₂₂) / (m₁₁ + m₁₂ + m₂₁ + m₂₂)
    # Power transmittance
    _HBAR_C_EV_CM = 1.97326980e-5   # eV·cm

    nw = len(omega_w)
    # Accumulate system matrix M = M₁ × M₂ ×
    M = np.zeros((nw, 2, 2), dtype=complex)
    M[:, 0, 0] = 1.0
    M[:, 1, 1] = 1.0

    for layer in layers:
        eta = layer["n"] + 1j * layer["k"]
        # Fase thickness
        delta = (omega_w / _HBAR_C_EV_CM) * eta * layer["d_cm"]
        cos_d = np.cos(delta)
        sin_d = np.sin(delta)
        # Layer matrix Mⱼ (vectorised over ω)
        Mj = np.zeros((nw, 2, 2), dtype=complex)
        Mj[:, 0, 0] = cos_d
        Mj[:, 0, 1] = (1j / eta) * sin_d
        Mj[:, 1, 0] = 1j * eta * sin_d
        Mj[:, 1, 1] = cos_d
        # Batch matrix multiply M = M × Mⱼ
        M = np.einsum("...ij,...jk->...ik", M, Mj)

    # Reflection y transmittance (η_inc = η_sub = 1)
    m11, m12, m21, m22 = M[:, 0, 0], M[:, 0, 1], M[:, 1, 0], M[:, 1, 1]
    r = (m11 + m12 - m21 - m22) / (m11 + m12 + m21 + m22)
    trans_w = np.clip(1.0 - np.abs(r) ** 2, 0.0, 1.0).real

    # Beer-Lambert inside absorber, scaled by TMM entrance transmittance
    x_cm = np.linspace(0.0, thickness_cm, n_x)
    alpha_col = absorber["alpha"][:, np.newaxis]
    intensity_profile = (flux_w * trans_w)[:, np.newaxis] * np.exp(-alpha_col * x_cm[np.newaxis, :])
    d_omega = np.gradient(omega_w)
    generation_profile = np.sum(
        alpha_col * intensity_profile * d_omega[:, np.newaxis], axis=0
    )

    absorbed_flux = float(np.trapezoid(generation_profile, x_cm))
    incident_flux = float(np.trapezoid(flux_w, omega_w))
    if incident_flux < 1.0:
        flags.append("ZERO_INCIDENT_FLUX")
        incident_flux = max(incident_flux, 1.0)

    eta_opt = min(absorbed_flux / incident_flux, 1.0)
    jsc = absorbed_flux * 1.602e-19 * 1e3

    result = DeviceOpticsResult(
        thickness_cm=thickness_cm,
        x_cm=x_cm,
        generation_rate=generation_profile,
        absorbed_photon_flux=absorbed_flux,
        incident_photon_flux=incident_flux,
        optical_efficiency=eta_opt,
        jsc_limit_mA_cm2=jsc,
        flags=flags,
    )
    logger.info("TMM: %s", result.summary)
    return result


def compute_device_optics(
    step_dir: Path,
    thickness_nm: float = 500.0,
    n_x: int = 500,
    use_tmm: bool = False,
) -> Optional[DeviceOpticsResult]:
    """Carga óptico.npy archivos desde step_dir y calcula dispositivo óptica."""
    step_dir = Path(step_dir)
    omega_path = step_dir / "optical_frequencies.npy"
    alpha_path = step_dir / "absorption_cm1.npy"

    if not omega_path.exists() or not alpha_path.exists():
        logger.warning("Optical .npy files not found in %s — skipping device optics", step_dir)
        return None

    omega_w = np.load(str(omega_path))
    alpha_w = np.load(str(alpha_path))
    thickness_cm = thickness_nm * 1e-7

    if use_tmm:
        n_path = step_dir / "n_omega.npy"
        k_path = step_dir / "k_omega.npy"
        if n_path.exists() and k_path.exists():
            n_w = np.load(str(n_path))
            k_w = np.load(str(k_path))
            layers = [{"alpha": alpha_w, "n": n_w, "k": k_w, "d_cm": thickness_cm}]
            result = multilayer_tmm_profile(omega_w, layers, n_x=n_x)
        else:
            logger.warning("n_omega.npy/k_omega.npy missing — falling back to Beer-Lambert")
            result = beer_lambert_profile(omega_w, alpha_w, thickness_cm, n_x=n_x)
    else:
        result = beer_lambert_profile(omega_w, alpha_w, thickness_cm, n_x=n_x)

    # Guarda salidas
    np.save(str(step_dir / "device_generation_rate.npy"), result.generation_rate)
    np.save(str(step_dir / "device_x_cm.npy"), result.x_cm)

    return result
