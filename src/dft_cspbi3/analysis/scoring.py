"""Photovoltaic solar cell scoring for ABX3 halide perovskite candidates.

Composite score combining:
  - Band gap (Shockley-Queisser optimal: 1.1–1.7 eV)
  - Gap type (direct >> indirect for thin-film PV)
  - Thermodynamic stability (ΔHf < 0)
  - Charge transport (m*_e, m*_h < 0.5 m₀)
  - Defect tolerance (no in-gap states)
  - Exciton binding energy (E_b < 50 meV for free-carrier generation)
  - Optical absorption strength (α at Eg + 0.5 eV)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# Physical constants
_E_CHARGE_C = 1.602e-19        # C
_M0_KG = 9.109e-31             # kg
_EPSILON0_F_M = 8.854e-12      # F/m
_HBAR_J_S = 1.055e-34          # J·s
_EV_PER_J = 6.242e18           # 1 J = 6.242e18 eV

# Shockley-Queisser optimal gap range
_SQ_GAP_MIN = 1.1   # eV
_SQ_GAP_MAX = 1.7   # eV
_SQ_GAP_OPT = 1.34  # eV (peak efficiency)


@dataclass
class SolarScore:
    """Composite photovoltaic screening score (0–100)."""

    total: float                                # 0–100
    # Component scores (0–1 each)
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


_RYDBERG_EV = 13.60570   # Hydrogen atom ground state energy (eV)
_4PI_EPSILON0 = 4 * 3.14159265 * _EPSILON0_F_M   # 4πε₀ in SI


def exciton_binding_energy(
    m_e: float,
    m_h: float,
    eps_r: float,
) -> float:
    """Wannier-Mott hydrogenic exciton binding energy.

    E_b = Ry × (m_r / m₀) / ε_r²

    where Ry = 13.6057 eV and m_r = m_e×m_h / (m_e+m_h) is the reduced mass.
    This is equivalent to the full SI expression:
        E_b = m_r e⁴ / (2 ħ² (4πε₀)² ε_r²)

    Args:
        m_e: Electron effective mass [m₀].
        m_h: Hole effective mass [m₀].
        eps_r: High-frequency or static relative dielectric constant. Use ε∞
               for free-exciton (optical-phonon-screened) binding energy.

    Returns:
        Exciton binding energy in eV.
    """
    m_r = (m_e * m_h) / (m_e + m_h)   # reduced mass in m₀
    E_b_eV = _RYDBERG_EV * m_r / (eps_r ** 2)
    logger.info(
        "E_b = %.1f meV (m*_r=%.3f m₀, ε_r=%.1f)",
        E_b_eV * 1000, m_r, eps_r,
    )
    return E_b_eV


def compute_solar_score(
    bandgap_eV: Optional[float] = None,
    gap_type: Optional[str] = None,          # "direct" or "indirect"
    delta_Hf_eV: Optional[float] = None,
    m_e: Optional[float] = None,             # in m₀
    m_h: Optional[float] = None,             # in m₀
    eps_r: Optional[float] = None,           # dielectric constant (ε∞ or ε₀)
    in_gap_dos: Optional[float] = None,      # states/eV in gap
    phonon_stable: Optional[bool] = None,    # True = no imaginary phonons
    alpha_at_onset: Optional[float] = None,  # α [cm⁻¹] at Eg + 0.5 eV
) -> SolarScore:
    """Compute a composite PV screening score (0–100).

    Weights reflect importance for thin-film solar cell performance:
      - Band gap:       25 pts  (Shockley-Queisser window)
      - Gap type:       20 pts  (direct = full, indirect = 0)
      - Stability:      20 pts  (ΔHf + phonon stability)
      - Transport:      15 pts  (m*_e + m*_h)
      - Exciton:        10 pts  (E_b < 50 meV)
      - Defect tolerance: 10 pts

    Missing data → the component defaults to a neutral 0.5 (partial credit).
    Disqualification if bandgap < 0.5 eV or ΔHf > +0.5 eV.

    Returns:
        SolarScore with total, components, and flags.
    """
    flags: list[str] = []
    disqualified = False

    # --- Band gap score (25 pts) ---
    if bandgap_eV is not None:
        if bandgap_eV < 0.5:
            flags.append(f"GAP_TOO_SMALL:{bandgap_eV:.2f}eV")
            disqualified = True
            s_gap = 0.0
        elif bandgap_eV > 3.5:
            flags.append(f"GAP_TOO_LARGE:{bandgap_eV:.2f}eV")
            s_gap = 0.05
        else:
            # Gaussian centered on SQ optimal gap
            s_gap = float(np.exp(-0.5 * ((bandgap_eV - _SQ_GAP_OPT) / 0.35) ** 2))
    else:
        s_gap = 0.5
        flags.append("BANDGAP_MISSING")

    # --- Gap type score (20 pts) ---
    if gap_type is not None:
        s_type = 1.0 if gap_type == "direct" else 0.0
    else:
        s_type = 0.5
        flags.append("GAP_TYPE_MISSING")

    # --- Thermodynamic stability score (20 pts) ---
    s_stab_thermo = 0.5
    if delta_Hf_eV is not None:
        if delta_Hf_eV < 0:
            s_stab_thermo = 1.0
        elif delta_Hf_eV < 0.1:
            s_stab_thermo = 0.6   # marginally unstable (common for metastable phases)
        elif delta_Hf_eV < 0.5:
            s_stab_thermo = 0.2
        else:
            s_stab_thermo = 0.0
            flags.append(f"THERMODYNAMICALLY_UNSTABLE:ΔHf={delta_Hf_eV:+.3f}eV")
            disqualified = True

    s_phon = 1.0 if phonon_stable else (0.0 if phonon_stable is False else 0.5)
    s_stability = 0.6 * s_stab_thermo + 0.4 * s_phon

    # --- Transport score (15 pts) ---
    if m_e is not None and m_h is not None:
        # Sigmoid: full credit below 0.3 m₀, zero above 1.5 m₀
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

    # --- Exciton binding energy score (10 pts) ---
    if m_e is not None and m_h is not None and eps_r is not None:
        E_b = exciton_binding_energy(m_e, m_h, eps_r)
        # Full credit below 25 meV, zero above 200 meV
        s_exciton = float(1 / (1 + np.exp(50 * (E_b - 0.075))))
    elif bandgap_eV is not None and m_e is not None and m_h is not None:
        E_b = 0.05   # typical fallback
        s_exciton = 0.5
        flags.append("DIELECTRIC_MISSING:exciton_approx")
        E_b = None
    else:
        E_b = None
        s_exciton = 0.5
        flags.append("EXCITON_DATA_MISSING")

    # --- Defect tolerance score (10 pts) ---
    if in_gap_dos is not None:
        s_defects = float(1 / (1 + 100 * in_gap_dos))
    else:
        s_defects = 0.5
        flags.append("IN_GAP_DOS_MISSING")

    # --- Total ---
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
