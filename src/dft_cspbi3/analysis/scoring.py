"""Photovoltaic solar celda scoring para ABX3 haluro perovskita candidatos."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# Physical constants
_E_CHARGE_C = 1.602e-19
_M0_KG = 9.109e-31
_EPSILON0_F_M = 8.854e-12
_HBAR_J_S = 1.055e-34
_EV_PER_J = 6.242e18           # 1 J = 6.242e18 eV

# Shockley-Queisser optimal gap range
_SQ_GAP_MIN = 1.1   # eV
_SQ_GAP_MAX = 1.7   # eV
_SQ_GAP_OPT = 1.34  # eV (peak efficiency)


@dataclass
class SolarScore:
    """Composite photovoltaic screening score (0-100)."""
    total: float                                # 0-100
    # Component scores (0-1 each)
    s_bandgap: float
    s_gap_type: float
    s_stability: float
    s_transport: float
    s_defects: float
    s_exciton: float
    # Input metrics
    bandgap_eV: Optional[float]
    gap_type: Optional[str]
    delta_Hf_eV: Optional[float]
    m_e: Optional[float]
    m_h: Optional[float]
    exciton_binding_eV: Optional[float]
    eps_r: Optional[float]
    # Flags
    disqualified: bool = False
    flags: list[str] = field(default_factory=list)

    @property
    def grade(self) -> str:
        if self.disqualified:
            return "DQ"
        if self.total >= 80:
            return "A"
        if self.total >= 60:
            return "B"
        if self.total >= 40:
            return "C"
        return "D"

    @property
    def summary(self) -> str:
        return (
            f"PV Score: {self.total:.1f}/100 [{self.grade}]  |  "
            f"Eg={self.bandgap_eV:.2f} eV ({self.gap_type or '?'}), "
            f"ΔHf={self.delta_Hf_eV:+.3f} eV, "
            f"m*_e={self.m_e:.2f} m₀, E_b={self.exciton_binding_eV*1000:.0f} meV"
            if all(v is not None for v in [self.bandgap_eV, self.delta_Hf_eV, self.m_e, self.exciton_binding_eV])
            else f"PV Score: {self.total:.1f}/100 [{self.grade}]"
        )


_RYDBERG_EV = 13.60570   # Hydrogen atom ground state energía (eV)
_4PI_EPSILON0 = 4 * 3.14159265 * _EPSILON0_F_M   # 4πε₀ en SI


def exciton_binding_energy(
    m_e: float,
    m_h: float,
    eps_r: float,
) -> float:
    """Wannier-Mott hydrogenic exciton binding energía."""
    m_r = (m_e * m_h) / (m_e + m_h)   # reduced mass en m₀
    E_b_eV = _RYDBERG_EV * m_r / (eps_r ** 2)
    logger.info(
        "E_b = %.1f meV (m*_r=%.3f m₀, ε_r=%.1f)",
        E_b_eV * 1000, m_r, eps_r,
    )
    return E_b_eV


def compute_solar_score(
    bandgap_eV: Optional[float] = None,
    gap_type: Optional[str] = None,
    delta_Hf_eV: Optional[float] = None,
    m_e: Optional[float] = None,             # en m₀
    m_h: Optional[float] = None,             # en m₀
    eps_r: Optional[float] = None,           # dielectric constant (ε∞ o ε₀)
    in_gap_dos: Optional[float] = None,      # states/eV en gap
    phonon_stable: Optional[bool] = None,
    alpha_at_onset: Optional[float] = None,  # α [cm⁻¹] en Eg + 0.5 eV
) -> SolarScore:
    """Calcula composite PV screening score (0-100)."""
    flags: list[str] = []
    disqualified = False

    # Banda gap score (25 pts)
    if bandgap_eV is not None:
        if bandgap_eV < 0.5:
            flags.append(f"GAP_TOO_SMALL:{bandgap_eV:.2f}eV")
            disqualified = True
            s_gap = 0.0
        elif bandgap_eV > 3.5:
            flags.append(f"GAP_TOO_LARGE:{bandgap_eV:.2f}eV")
            s_gap = 0.05
        else:
            # Gaussian centered en SQ optimal gap
            s_gap = float(np.exp(-0.5 * ((bandgap_eV - _SQ_GAP_OPT) / 0.35) ** 2))
    else:
        s_gap = 0.5
        flags.append("BANDGAP_MISSING")

    # Gap type score (20 pts)
    if gap_type is not None:
        s_type = 1.0 if gap_type == "direct" else 0.0
    else:
        s_type = 0.5
        flags.append("GAP_TYPE_MISSING")

    # Thermodynamic estabilidad score (20 pts)
    s_stab_thermo = 0.5
    if delta_Hf_eV is not None:
        if delta_Hf_eV < 0:
            s_stab_thermo = 1.0
        elif delta_Hf_eV < 0.1:
            s_stab_thermo = 0.6
        elif delta_Hf_eV < 0.5:
            s_stab_thermo = 0.2
        else:
            s_stab_thermo = 0.0
            flags.append(f"THERMODYNAMICALLY_UNSTABLE:ΔHf={delta_Hf_eV:+.3f}eV")
            disqualified = True

    s_phon = 1.0 if phonon_stable else (0.0 if phonon_stable is False else 0.5)
    s_stability = 0.6 * s_stab_thermo + 0.4 * s_phon

    # Transport score (15 pts)
    if m_e is not None and m_h is not None:
        # Sigmoid
        s_me = float(1 / (1 + np.exp(5 * (m_e - 0.5))))
        s_mh = float(1 / (1 + np.exp(5 * (m_h - 0.5))))
        s_transport = 0.5 * (s_me + s_mh)
    elif m_e is not None or m_h is not None:
        m = m_e or m_h
        s_transport = float(1 / (1 + np.exp(5 * (m - 0.5))))
        flags.append("ONLY_ONE_MASS_AVAILABLE")
    else:
        s_transport = 0.5
        flags.append("EFFECTIVE_MASSES_MISSING")

    # Exciton binding energía score (10 pts)
    if m_e is not None and m_h is not None and eps_r is not None:
        E_b = exciton_binding_energy(m_e, m_h, eps_r)
        # Full credit bajo 25 meV, zero sobre 200 meV
        s_exciton = float(1 / (1 + np.exp(50 * (E_b - 0.075))))
    elif bandgap_eV is not None and m_e is not None and m_h is not None:
        E_b = 0.05
        s_exciton = 0.5
        flags.append("DIELECTRIC_MISSING:exciton_approx")
        E_b = None
    else:
        E_b = None
        s_exciton = 0.5
        flags.append("EXCITON_DATA_MISSING")

    # Defect tolerance score (10 pts)
    if in_gap_dos is not None:
        s_defects = float(1 / (1 + 100 * in_gap_dos))
    else:
        s_defects = 0.5
        flags.append("IN_GAP_DOS_MISSING")

    # Total
    total = (
        25 * s_gap +
        20 * s_type +
        20 * s_stability +
        15 * s_transport +
        10 * s_exciton +
        10 * s_defects
    )
    if disqualified:
        total = min(total, 20.0)

    score = SolarScore(
        total=total,
        s_bandgap=s_gap,
        s_gap_type=s_type,
        s_stability=s_stability,
        s_transport=s_transport,
        s_defects=s_defects,
        s_exciton=s_exciton,
        bandgap_eV=bandgap_eV,
        gap_type=gap_type,
        delta_Hf_eV=delta_Hf_eV,
        m_e=m_e,
        m_h=m_h,
        exciton_binding_eV=E_b if isinstance(E_b, float) else None,
        eps_r=eps_r,
        disqualified=disqualified,
        flags=flags,
    )
    logger.info("Solar PV score: %s", score.summary)
    return score
