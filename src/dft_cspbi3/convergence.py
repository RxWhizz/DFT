"""Convergence tests for plane-wave cutoff (Ecut) and k-point sampling."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd
from ase import Atoms
from gpaw import GPAW, PW

from .calculator_factory import GPAWCalculatorFactory

logger = logging.getLogger(__name__)


def test_encut(
    values: Sequence[float],
    atoms: Atoms,
    base_params: dict | None = None,
    work_dir: Path = Path("./convergence_encut"),
    txt_prefix: str = "encut",
) -> pd.DataFrame:
    """Run single-point SCF calculations at each plane-wave cutoff.

    Args:
        values: List of cutoff energies in eV, e.g. [300, 350, 400, 450, 500, 550].
        atoms: ASE Atoms object (relaxed or initial geometry).
        base_params: Extra GPAW kwargs to merge into each calculation.
        work_dir: Root directory for per-ecut subdirectories.
        txt_prefix: Prefix for GPAW output text files.

    Returns:
        DataFrame with columns ['ecut_eV', 'energy_eV', 'energy_per_atom_eV',
                                  'delta_meV_per_atom'].
    """
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    base_params = base_params or {}
    natoms = len(atoms)
    records = []

    for ecut in values:
        ecut_dir = work_dir / f"ecut_{int(ecut):04d}"
        ecut_dir.mkdir(exist_ok=True)
        logger.info("Running SCF at Ecut = %g eV", ecut)

        kwargs = {
            "mode": PW(ecut),
            "xc": "PBEsol",
            "kpts": {"size": [6, 6, 6], "gamma": True},
            "convergence": {"energy": 1e-6},
            "txt": str(ecut_dir / f"{txt_prefix}_{int(ecut)}.txt"),
        }
        kwargs.update(base_params)

        calc = GPAW(**kwargs)
        atoms_copy = atoms.copy()
        atoms_copy.calc = calc
        energy = atoms_copy.get_potential_energy()
        records.append({"ecut_eV": float(ecut), "energy_eV": energy})

    df = pd.DataFrame(records).sort_values("ecut_eV").reset_index(drop=True)
    df["energy_per_atom_eV"] = df["energy_eV"] / natoms
    # Delta relative to highest cutoff (most converged reference)
    e_ref = df["energy_per_atom_eV"].iloc[-1]
    df["delta_meV_per_atom"] = (df["energy_per_atom_eV"] - e_ref) * 1000.0
    return df


def test_kpoints(
    meshes: Sequence[list[int]],
    atoms: Atoms,
    base_params: dict | None = None,
    work_dir: Path = Path("./convergence_kpts"),
    ecut: float = 450.0,
    txt_prefix: str = "kpts",
) -> pd.DataFrame:
    """Run single-point SCF calculations at each k-point mesh.

    Args:
        meshes: List of [Nx, Ny, Nz] grids, e.g. [[4,4,4],[6,6,6],[8,8,8],[10,10,10]].
        atoms: ASE Atoms object.
        base_params: Extra GPAW kwargs.
        work_dir: Root directory.
        ecut: Plane-wave cutoff to use (fixed while varying k-mesh).

    Returns:
        DataFrame with columns ['kx','ky','kz','nkpts_total','energy_eV',
                                  'energy_per_atom_eV','delta_meV_per_atom'].
    """
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    base_params = base_params or {}
    natoms = len(atoms)
    records = []

    for mesh in meshes:
        kx, ky, kz = mesh
        kdir = work_dir / f"k{kx}x{ky}x{kz}"
        kdir.mkdir(exist_ok=True)
        logger.info("Running SCF at k-mesh %dx%dx%d", kx, ky, kz)

        kwargs = {
            "mode": PW(ecut),
            "xc": "PBEsol",
            "kpts": {"size": [kx, ky, kz], "gamma": True},
            "convergence": {"energy": 1e-6},
            "txt": str(kdir / f"{txt_prefix}_{kx}x{ky}x{kz}.txt"),
        }
        kwargs.update(base_params)

        calc = GPAW(**kwargs)
        atoms_copy = atoms.copy()
        atoms_copy.calc = calc
        energy = atoms_copy.get_potential_energy()
        nkpts = kx * ky * kz
        records.append({"kx": kx, "ky": ky, "kz": kz, "nkpts_total": nkpts, "energy_eV": energy})

    df = pd.DataFrame(records).sort_values("nkpts_total").reset_index(drop=True)
    df["energy_per_atom_eV"] = df["energy_eV"] / natoms
    e_ref = df["energy_per_atom_eV"].iloc[-1]
    df["delta_meV_per_atom"] = (df["energy_per_atom_eV"] - e_ref) * 1000.0
    return df


def find_converged_value(
    df: pd.DataFrame,
    param_col: str = "ecut_eV",
    threshold_meV: float = 1.0,
) -> float | None:
    """Return the smallest parameter value where |ΔE| < threshold_meV/atom.

    The delta is measured relative to the largest (most converged) value in df.

    Returns:
        The converged parameter value, or None if convergence is not reached.
    """
    converged = df[df["delta_meV_per_atom"].abs() < threshold_meV]
    if converged.empty:
        logger.warning("Convergence threshold %.1f meV/atom not reached", threshold_meV)
        return None
    return float(converged[param_col].iloc[0])


def run_both(
    atoms: Atoms,
    config_path: str | Path | None = None,
    work_dir: Path = Path("./convergence"),
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run both Ecut and k-points convergence tests.

    Uses cutoff values and k-meshes from default_params.yaml.

    Returns:
        Tuple of (df_ecut, df_kpoints).
    """
    factory = GPAWCalculatorFactory(config_path) if config_path else GPAWCalculatorFactory()
    cfg = factory.config

    ecut_values = cfg["cutoff"].get("convergence_range", [300, 350, 400, 450, 500, 550])
    kpt_meshes = [[n, n, n] for n in [4, 6, 8, 10]]

    df_ecut = test_encut(
        ecut_values,
        atoms,
        work_dir=Path(work_dir) / "encut",
    )
    df_kpts = test_kpoints(
        kpt_meshes,
        atoms,
        work_dir=Path(work_dir) / "kpoints",
        ecut=cfg["cutoff"].get("pw_ecut", 450),
    )
    return df_ecut, df_kpts
