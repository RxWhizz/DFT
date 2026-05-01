"""Structural geometry analysis for ABX3 halide perovskites.

Computes Goldschmidt tolerance factor, octahedral factor, and BX6
octahedral distortion metrics from ASE Atoms objects.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from ase import Atoms

logger = logging.getLogger(__name__)

# Shannon ionic radii (Å) — Shannon 1976 Acta Cryst A32:751
IONIC_RADII = {
    "Cs":  {"CN12": 1.74, "CN6": 1.67},
    "MA":  {"CN12": 2.17, "CN6": 2.17},
    "FA":  {"CN12": 2.53, "CN6": 2.53},
    "Rb":  {"CN12": 1.61, "CN6": 1.52},
    "K":   {"CN12": 1.64, "CN6": 1.38},
    "Pb":  {"CN6": 1.19},
    "Sn":  {"CN6": 1.10},
    "Ge":  {"CN6": 0.73},
    "I":   {"CN6": 2.20},
    "Br":  {"CN6": 1.96},
    "Cl":  {"CN6": 1.81},
}


@dataclass
class StructuralMetrics:
    """Geometric stability and distortion metrics for ABX3 perovskite."""

    tolerance_factor: float
    octahedral_factor: float
    mean_bx_bond_Ang: Optional[float] = None
    bx_bond_variance: Optional[float] = None
    mean_bxb_angle_deg: Optional[float] = None
    tilt_angle_deg: Optional[float] = None
    flags: list[str] = field(default_factory=list)

    @property
    def tolerance_ok(self) -> bool:
        return 0.80 <= self.tolerance_factor <= 1.00

    @property
    def octahedral_ok(self) -> bool:
        return 0.44 <= self.octahedral_factor <= 0.90

    @property
    def structurally_stable(self) -> bool:
        return self.tolerance_ok and self.octahedral_ok

    @property
    def summary(self) -> str:
        status = "STABLE" if self.structurally_stable else "UNSTABLE"
        return (
            f"{status} | t={self.tolerance_factor:.3f} "
            f"({'OK' if self.tolerance_ok else 'OUT'}), "
            f"μ={self.octahedral_factor:.3f} "
            f"({'OK' if self.octahedral_ok else 'OUT'})"
        )


def goldschmidt_tolerance(r_A: float, r_B: float, r_X: float) -> float:
    """t = (r_A + r_X) / (√2 (r_B + r_X))."""
    return (r_A + r_X) / (2 ** 0.5 * (r_B + r_X))


def octahedral_factor(r_B: float, r_X: float) -> float:
    """μ = r_B / r_X."""
    return r_B / r_X


def analyze_perovskite_geometry(
    atoms: Atoms,
    A_species: str = "Cs",
    B_species: str = "Pb",
    X_species: str = "I",
) -> StructuralMetrics:
    """Compute structural stability metrics for an ABX3 perovskite.

    Args:
        atoms: Relaxed ASE Atoms (unit cell or supercell).
        A_species, B_species, X_species: Element symbols.

    Returns:
        StructuralMetrics with t, μ, and distortion metrics.
    """
    flags: list[str] = []

    r_A = IONIC_RADII.get(A_species, {}).get("CN12")
    r_B = IONIC_RADII.get(B_species, {}).get("CN6")
    r_X = IONIC_RADII.get(X_species, {}).get("CN6")

    missing = [s for s, r in zip([A_species, B_species, X_species], [r_A, r_B, r_X]) if r is None]
    if missing:
        flags.append(f"MISSING_IONIC_RADII:{missing}")
        r_A = r_A or 1.74
        r_B = r_B or 1.19
        r_X = r_X or 2.20

    t = goldschmidt_tolerance(r_A, r_B, r_X)
    mu = octahedral_factor(r_B, r_X)

    bx_bond_mean = bx_bond_var = bxb_angle_mean = tilt = None
    try:
        B_idx = [i for i, s in enumerate(atoms.get_chemical_symbols()) if s == B_species]
        X_idx = [i for i, s in enumerate(atoms.get_chemical_symbols()) if s == X_species]
        pos = atoms.get_positions()
        cell = atoms.cell

        if B_idx and X_idx:
            all_bx, all_bxb = [], []
            for ib in B_idx:
                dists = [(float(_mic_dist(pos[ib], pos[ix], cell)), ix) for ix in X_idx]
                dists.sort()
                nn6 = dists[:6]
                all_bx.extend(d for d, _ in nn6)
                for i1, (_, ix1) in enumerate(nn6):
                    v1 = _mic_vec(pos[ib], pos[ix1], cell)
                    for _, (_, ix2) in enumerate(nn6[i1+1:], i1+1):
                        v2 = _mic_vec(pos[ib], pos[ix2], cell)
                        cos_a = np.clip(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)), -1, 1)
                        angle = float(np.degrees(np.arccos(cos_a)))
                        if angle > 140:
                            all_bxb.append(angle)

            bx_bond_mean = float(np.mean(all_bx))
            bx_bond_var = float(np.var(all_bx))
            if all_bxb:
                bxb_angle_mean = float(np.mean(all_bxb))
                tilt = float(180.0 - bxb_angle_mean)
    except Exception as exc:
        flags.append(f"DISTORTION_FAILED:{exc}")
        logger.warning("Distortion analysis failed: %s", exc)

    result = StructuralMetrics(
        tolerance_factor=t,
        octahedral_factor=mu,
        mean_bx_bond_Ang=bx_bond_mean,
        bx_bond_variance=bx_bond_var,
        mean_bxb_angle_deg=bxb_angle_mean,
        tilt_angle_deg=tilt,
        flags=flags,
    )
    if not result.tolerance_ok:
        result.flags.append(f"TOLERANCE_OUT_OF_RANGE:t={t:.3f}")
    if not result.octahedral_ok:
        result.flags.append(f"OCTAHEDRAL_OUT_OF_RANGE:mu={mu:.3f}")

    logger.info("Structural metrics: %s", result.summary)
    return result


def _mic_dist(p1: np.ndarray, p2: np.ndarray, cell) -> float:
    diff = p2 - p1
    frac = np.linalg.solve(cell.T, diff)
    frac -= np.round(frac)
    return float(np.linalg.norm(cell.T @ frac))


def _mic_vec(origin: np.ndarray, target: np.ndarray, cell) -> np.ndarray:
    diff = target - origin
    frac = np.linalg.solve(cell.T, diff)
    frac -= np.round(frac)
    return cell.T @ frac
