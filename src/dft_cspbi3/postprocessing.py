"""Extract band gaps, DOS, and band structures from GPAW checkpoint files."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


def get_bandgap(gpw_file: str | Path, soc: bool = False) -> float:
    """Return the fundamental band gap (eV) from a GPAW .gpw file.

    Args:
        gpw_file: Path to GPAW checkpoint file.
        soc: If True, apply perturbative SOC first.

    Returns:
        Band gap in eV (LUMO − HOMO at their respective k-points).
    """
    from gpaw import GPAW

    calc = GPAW(str(gpw_file))

    if soc:
        return get_soc_bandgap(gpw_file)

    homo, lumo = calc.get_homo_lumo()
    gap = lumo - homo
    logger.info("Band gap (no SOC): %.4f eV", gap)
    return float(gap)


def get_soc_bandgap(gpw_file: str | Path) -> float:
    """Return the band gap with perturbative SOC correction.

    Uses gpaw.spinorbit.spinorbit_eigenvalues() to apply SOC to the
    collinear eigenvalues stored in a .gpw file.

    Returns:
        SOC-corrected band gap in eV.
    """
    from gpaw import GPAW
    from gpaw.spinorbit import soc_eigenstates

    calc = GPAW(str(gpw_file))
    result = soc_eigenstates(str(gpw_file))
    e_kn = result.eigenvalues()

    # e_kn shape: (nkpts, nbands) — energies relative to Fermi level
    ef = calc.get_fermi_level()
    nelectrons = int(round(calc.get_number_of_electrons()))
    nvalence = nelectrons // 2  # spin-degenerate; SOC doubles bands

    # SOC bands sorted per k-point
    occupied = e_kn[:, :nelectrons]
    unoccupied = e_kn[:, nelectrons:]

    vbm = float(occupied.max())
    cbm = float(unoccupied.min())
    gap = cbm - vbm
    logger.info("SOC band gap: %.4f eV (VBM=%.4f, CBM=%.4f)", gap, vbm, cbm)
    return gap


def get_dos(
    gpw_file: str | Path,
    npts: int = 2000,
    width: float = 0.05,
) -> dict:
    """Compute total and projected DOS from a GPAW .gpw file.

    Returns:
        Dict with keys 'energies', 'total', and per-element PDOS arrays.
    """
    from ase.dft.dos import DOS
    from gpaw import GPAW

    calc = GPAW(str(gpw_file))
    dos = DOS(calc, npts=npts, width=width)

    energies = dos.get_energies()
    total = dos.get_dos()

    atoms = calc.get_atoms()
    symbols = atoms.get_chemical_symbols()
    unique_symbols = list(dict.fromkeys(symbols))

    pdos: dict[str, np.ndarray] = {}
    for sym in unique_symbols:
        indices = [i for i, s in enumerate(symbols) if s == sym]
        # Sum PDOS over all atoms of this element (spin=0 for non-spin-polarised)
        atom_dos = np.zeros(npts)
        for idx in indices:
            try:
                atom_dos += dos.get_dos(spin=0, atom=idx)
            except Exception:
                pass
        pdos[sym] = atom_dos

    return {
        "energies": energies,
        "total": total,
        "pdos": pdos,
    }


def get_band_structure(gpw_file: str | Path):
    """Return an ASE BandStructure object from a bands .gpw checkpoint.

    The returned object can be passed directly to plotting.plot_band_structure().
    """
    from gpaw import GPAW

    calc = GPAW(str(gpw_file))
    bs = calc.band_structure()
    return bs


def get_homo_lumo(gpw_file: str | Path) -> tuple[float, float]:
    """Return (HOMO, LUMO) energies in eV."""
    from gpaw import GPAW

    calc = GPAW(str(gpw_file))
    homo, lumo = calc.get_homo_lumo()
    return float(homo), float(lumo)


def get_fermi_level(gpw_file: str | Path) -> float:
    """Return the Fermi level in eV."""
    from gpaw import GPAW

    calc = GPAW(str(gpw_file))
    return float(calc.get_fermi_level())


def get_total_energy(gpw_file: str | Path) -> float:
    """Return the total DFT energy in eV."""
    from gpaw import GPAW

    calc = GPAW(str(gpw_file))
    return float(calc.get_potential_energy())


def extract_summary(gpw_file: str | Path, soc: bool = False) -> dict:
    """Extract a summary dictionary of key properties from a .gpw file."""
    from gpaw import GPAW

    calc = GPAW(str(gpw_file))
    atoms = calc.get_atoms()

    summary = {
        "gpw_file": str(gpw_file),
        "formula": atoms.get_chemical_formula(),
        "natoms": len(atoms),
        "volume_ang3": float(atoms.get_volume()),
        "total_energy_eV": float(calc.get_potential_energy()),
        "fermi_level_eV": float(calc.get_fermi_level()),
    }

    try:
        homo, lumo = calc.get_homo_lumo()
        summary["homo_eV"] = float(homo)
        summary["lumo_eV"] = float(lumo)
        summary["bandgap_eV"] = float(lumo - homo)
    except Exception as exc:
        logger.warning("Could not extract HOMO/LUMO: %s", exc)

    if soc:
        try:
            summary["bandgap_soc_eV"] = get_soc_bandgap(gpw_file)
        except Exception as exc:
            logger.warning("Could not compute SOC gap: %s", exc)

    return summary
