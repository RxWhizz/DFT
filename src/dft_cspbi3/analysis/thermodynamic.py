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


def build_CsI_rocksalt() -> Atoms:
    """Build CsI rock salt (Fm-3m) unit cell. a₀ = 4.567 Å.

    Cs at (0,0,0), I at (0.5,0.5,0.5) — 2 atoms per f.u.
    """
    from ase.build import bulk
    return bulk("CsI", crystalstructure="rocksalt", a=4.567)


def build_PbI2_cdl2() -> Atoms:
    """Build PbI₂ CdI₂-type (P-3m1, hexagonal) unit cell.

    Pb at (0,0,0); I at (1/3, 2/3, ±z) with z = 0.235.
    a = 4.558 Å, c = 6.986 Å — 3 atoms per f.u.
    """
    a, c = 4.558, 6.986
    z_I = 0.235

    cell = np.array([
        [a, 0, 0],
        [a * np.cos(np.radians(60)), a * np.sin(np.radians(60)), 0],
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

    Args:
        work_dir: Directory to write GPAW output files.
        factory: GPAWCalculatorFactory instance (uses its config for xc/ecut).

    Returns:
        Dict with keys "CsI_per_fu" and "PbI2_per_fu" (eV per formula unit).
    """
    from gpaw import GPAW

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    energies: dict[str, float] = {}

    for label, builder, n_atoms_per_fu in [
        ("CsI", build_CsI_rocksalt, 2),
        ("PbI2", build_PbI2_cdl2, 3),
    ]:
        gpw_out = work_dir / f"{label}.gpw"
        txt_out = work_dir / f"{label}.txt"

        if gpw_out.exists():
            calc = GPAW(str(gpw_out))
            e_total = calc.get_potential_energy()
            atoms = calc.get_atoms()
            calc.__del__()
        else:
            atoms = builder()
            calc = factory.create("scf", txt=str(txt_out))
            atoms.calc = calc
            e_total = atoms.get_potential_energy()
            calc.write(str(gpw_out))

        energies[f"{label}_per_fu"] = e_total / (len(atoms) / n_atoms_per_fu) if len(atoms) > n_atoms_per_fu else e_total
        logger.info("%s: E = %.4f eV/f.u.", label, energies[f"{label}_per_fu"])

    return energies
