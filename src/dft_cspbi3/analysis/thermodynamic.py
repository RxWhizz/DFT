"""Entalpía formación ΔHf."""

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
    """Entalpía formación ΔHf."""

    delta_Hf_eV: float
    E_perovskite_eV: float                # DFT total energía perovskita (per f.u.)
    E_binary_A_eV: float                  # DFT total energía AX binary (per f.u.)
    E_binary_B_eV: float                  # DFT total energía BX2 binary (per f.u.)
    binary_A_label: str = "CsI"
    binary_B_label: str = "PbI₂"
    stable: Optional[bool] = None         # verdadero si ΔHf < 0
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
    """Calcula ΔHf por f.u."""
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


# Reference estructura builders


def build_CsI_CsCl() -> Atoms:
    """Construye CsI tipo CsCl."""
    from ase.build import bulk
    return bulk("CsI", crystalstructure="cesiumchloride", a=4.567)


def build_PbI2_cdl2() -> Atoms:
    """Construye PbI₂ tipo CdI₂."""
    a, c = 4.558, 6.986
    z_I = 0.235

    # Hexagonal primitive celda
    # Usa cos(60°) here was bug - it gives 60° y puts periodic I images
    # en only ~2.24 Å desde Pb instead correct ~3.10 Å
    cell = np.array([
        [a, 0, 0],
        [a * np.cos(np.radians(120)), a * np.sin(np.radians(120)), 0],
        [0, 0, c],
    ])
    # In fractional coords hexagonal celda:
    # Pb
    # I1
    # I2
    scaled_positions = np.array([
        [0.0, 0.0, 0.0],
        [1/3, 2/3, z_I],
        [2/3, 1/3, 1 - z_I],
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
    """Ejecuta SCF CsI/PbI2 referencia."""
    from gpaw import GPAW

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    # (builder_fn, n_atoms_per_fu, k-grid sized para volume-matched k-densidad)
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
