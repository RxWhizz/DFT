"""Formation enthalpy ΔHf for ABX3 perovskites from binary reference energies.

ΔHf = E(CsPbI₃) - E(CsI) - E(PbI₂)   [eV per formula unit]

Negative ΔHf → thermodynamically stable w.r.t. binary decomposition.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
from ase import Atoms

logger = logging.getLogger(__name__)


@dataclass
class FormationEnthalpyResult:
    """Formation enthalpy from binary references."""

    delta_Hf_eV: float                    # ΔHf per formula unit
    E_perovskite_eV: float                # DFT total energy of perovskite (per f.u.)
    E_binary_A_eV: float                  # DFT total energy of AX binary (per f.u.)
    E_binary_B_eV: float                  # DFT total energy of BX2 binary (per f.u.)
    binary_A_label: str = "CsI"
    binary_B_label: str = "PbI₂"
    stable: Optional[bool] = None         # True if ΔHf < 0
    flags: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.stable = self.delta_Hf_eV < 0

    @property
    def summary(self) -> str:
        status = "STABLE" if self.stable else "UNSTABLE"
        return f"ΔHf = {self.delta_Hf_eV:+.3f} eV/f.u. → {status} vs binary decomposition"


def formation_enthalpy(
    E_perovskite_per_fu: float,
    E_binary_A_per_fu: float,
    E_binary_B_per_fu: float,
    binary_A_label: str = "CsI",
    binary_B_label: str = "PbI₂",
) -> FormationEnthalpyResult:
    """Compute ΔHf per formula unit.

    ΔHf/f.u. = E(CsPbI₃) - E(CsI) - E(PbI₂)

    Args:
        E_perovskite_per_fu: DFT total energy of the perovskite per formula unit (eV).
        E_binary_A_per_fu: DFT total energy of AX binary per formula unit (eV).
        E_binary_B_per_fu: DFT total energy of BX₂ binary per formula unit (eV).

    Returns:
        FormationEnthalpyResult.
    """
    delta_Hf = E_perovskite_per_fu - E_binary_A_per_fu - E_binary_B_per_fu
    result = FormationEnthalpyResult(
        delta_Hf_eV=delta_Hf,
        E_perovskite_eV=E_perovskite_per_fu,
        E_binary_A_eV=E_binary_A_per_fu,
        E_binary_B_eV=E_binary_B_per_fu,
        binary_A_label=binary_A_label,
        binary_B_label=binary_B_label,
    )
    logger.info("Formation enthalpy: %s", result.summary)
    return result


# ---------------------------------------------------------------------------
# Reference structure builders
# ---------------------------------------------------------------------------


def build_CsI_CsCl() -> Atoms:
    """Build CsI in the CsCl structure (B2, Pm-3m). a₀ = 4.567 Å, Cs-I = 3.96 Å.

    This is the ambient-pressure stable phase of CsI.
    Cs at (0,0,0), I at (0.5,0.5,0.5) — 2 atoms, 1 f.u.
    """
    from ase.build import bulk
    return bulk("CsI", crystalstructure="cesiumchloride", a=4.567)


def build_PbI2_cdl2() -> Atoms:
    """Build PbI₂ CdI₂-type (P-3m1, hexagonal) unit cell.

    Pb at (0,0,0); I at (1/3, 2/3, ±z) with z = 0.235.
    a = 4.558 Å, c = 6.986 Å — 3 atoms per f.u.
    """
    a, c = 4.558, 6.986
    z_I = 0.235

    # Hexagonal primitive cell: angle between a1 and a2 is 120°.
    # Using cos(60°) here was a bug — it gives 60° and puts periodic I images
    # at only ~2.24 Å from Pb instead of the correct ~3.10 Å.
    cell = np.array([
        [a, 0, 0],
        [a * np.cos(np.radians(120)), a * np.sin(np.radians(120)), 0],
        [0, 0, c],
    ])
    # In fractional coords of the hexagonal cell:
    # Pb: (0, 0, 0)
    # I1: (1/3, 2/3, z)
    # I2: (2/3, 1/3, -z)  = (2/3, 1/3, 1-z) in [0,1)
    scaled_positions = np.array([
        [0.0, 0.0, 0.0],          # Pb
        [1/3, 2/3, z_I],           # I
        [2/3, 1/3, 1 - z_I],       # I
    ])
    positions = scaled_positions @ cell

    atoms = Atoms(
        symbols=["Pb", "I", "I"],
        positions=positions,
        cell=cell,
        pbc=True,
    )
    return atoms


def compute_binary_energies(
    work_dir: Path,
    factory,
) -> dict[str, float]:
    """Run SCF single-points for CsI and PbI₂ reference structures.

    Uses the CsI B2 (CsCl-type) structure and PbI₂ CdI₂-type structure,
    both at their ambient-condition stable polymorphs.

    k-grids are scaled to maintain the same real-space k-point density as
    the perovskite SCF (typically 6×6×6 for a ~6.3 Å cubic cell):
      - CsI (B2, a≈4.57 Å, V≈95 Å³):  10×10×10
      - PbI₂ (hexagonal, V≈126 Å³):    8×8×6

    Args:
        work_dir: Directory to write GPAW output files.
        factory: GPAWCalculatorFactory instance (uses its xc/ecut settings).

    Returns:
        Dict with keys "CsI_per_fu" and "PbI2_per_fu" (eV per formula unit).
    """
    from gpaw import GPAW

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    # (builder_fn, n_atoms_per_fu, k-grid sized for volume-matched k-density)
    configs = [
        ("CsI",  build_CsI_CsCl,  2, [10, 10, 10]),
        ("PbI2", build_PbI2_cdl2, 3, [8,  8,  6 ]),
    ]

    energies: dict[str, float] = {}

    for label, builder, n_atoms_per_fu, kgrid in configs:
        gpw_out = work_dir / f"{label}.gpw"
        txt_out = work_dir / f"{label}.txt"

        if gpw_out.exists():
            calc = GPAW(str(gpw_out), txt=None)
            e_total = calc.get_potential_energy()
            n_atoms = len(calc.get_atoms())
            calc.__del__()
        else:
            atoms = builder()
            calc = factory.create(
                "scf",
                txt=str(txt_out),
                params_override={"kpts": {"size": kgrid, "gamma": True}},
            )
            atoms.calc = calc
            e_total = atoms.get_potential_energy()
            calc.write(str(gpw_out))
            n_atoms = len(atoms)

        n_fu = n_atoms / n_atoms_per_fu
        energies[f"{label}_per_fu"] = e_total / n_fu
        logger.info("%s: E = %.4f eV/f.u. (kgrid %s)", label, energies[f"{label}_per_fu"], kgrid)

    return energies
