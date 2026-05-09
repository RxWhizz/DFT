"""Valida aplicación SOC en GPAW."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# Physical plausibility bounds para CsPbI3-class systems (Pb 6p SOC)
_CHI_SOC_MIN = -1.5  # eV - upper bound en SOC reduction
_CHI_SOC_MAX = 0.0   # eV - SOC debe always reduce gap en Pb systems
_SPLIT_MIN_EV = 0.05 # eV - minimum detectable banda splitting


# Data class


@dataclass
class SOCReport:
    """Resultados desde SOC validación."""

    soc_applied: bool
    gap_no_soc_eV: Optional[float]
    gap_soc_eV: Optional[float]
    chi_soc_eV: Optional[float]         # Eg(SOC) - Eg(no-SOC)
    chi_soc_plausible: bool
    splitting_detected: bool
    spurious_magnetisation: bool
    n_kpts: int
    n_bands_soc: int
    flags: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return (
            self.soc_applied
            and self.chi_soc_plausible
            and self.splitting_detected
            and not self.spurious_magnetisation
            and not self.flags
        )


# Main validación function


def validate_soc(
    scf_gpw: str | Path,
    soc_eig_npy: str | Path,
    soc_spin_npy: str | Path,
    chi_soc_bounds: tuple[float, float] = (_CHI_SOC_MIN, _CHI_SOC_MAX),
) -> SOCReport:
    """Validate perturbative SOC cálculo stored as.npy arrays."""
    flags: list[str] = []
    soc_eig_npy = Path(soc_eig_npy)
    soc_spin_npy = Path(soc_spin_npy)

    # 1
    if not soc_eig_npy.exists():
        return SOCReport(
            soc_applied=False,
            gap_no_soc_eV=None,
            gap_soc_eV=None,
            chi_soc_eV=None,
            chi_soc_plausible=False,
            splitting_detected=False,
            spurious_magnetisation=False,
            n_kpts=0,
            n_bands_soc=0,
            flags=[f"FILE_NOT_FOUND:{soc_eig_npy}"],
        )

    # 2
    e_kn = np.load(str(soc_eig_npy))       # (nkpts, 2*nbands)
    s_kn = np.load(str(soc_spin_npy)) if soc_spin_npy.exists() else None

    nkpts, n_bands_soc = e_kn.shape

    # 3
    from gpaw import GPAW

    calc = GPAW(str(scf_gpw))
    ef = float(calc.get_fermi_level())
    n_elec = int(round(calc.get_number_of_electrons()))

    # PBE gap (no SOC)
    try:
        homo_pbe, lumo_pbe = calc.get_homo_lumo()
        gap_no_soc = float(lumo_pbe - homo_pbe)
    except Exception as exc:
        flags.append(f"PBE_GAP_FAILED:{exc}")
        gap_no_soc = None

    # 4
    # SOC doubles bands
    # (2 spin states per original banda → n_elec = 2 * n_original_occupied)
    try:
        occupied = e_kn[:, :n_elec]
        unoccupied = e_kn[:, n_elec:]
        vbm_soc = float(occupied.max())
        cbm_soc = float(unoccupied.min())
        gap_soc = cbm_soc - vbm_soc
    except Exception as exc:
        flags.append(f"SOC_GAP_FAILED:{exc}")
        gap_soc = None

    # 5
    chi_soc: Optional[float] = None
    chi_plausible = False
    if gap_soc is not None and gap_no_soc is not None:
        chi_soc = gap_soc - gap_no_soc
        lo, hi = chi_soc_bounds
        chi_plausible = lo <= chi_soc <= hi
        if not chi_plausible:
            flags.append(
                f"CHI_SOC_OUT_OF_RANGE:{chi_soc:.3f}eV (expected [{lo},{hi}])"
            )

    # 6
    # Spin projections s_kn debe have non-zero variance si SOC active
    splitting_detected = False
    if s_kn is not None:
        spin_variance = float(np.var(s_kn))
        splitting_detected = spin_variance > 1e-6
        if not splitting_detected:
            flags.append("SOC_NO_SPIN_SPLITTING_DETECTED")
    else:
        # Fallback
        try:
            pbe_eigs = calc.get_eigenvalues(kpt=0)
            soc_k0 = e_kn[0, :]
            # SOC debe produce ≥ 2× more bands en each k-point
            if len(soc_k0) >= 2 * len(pbe_eigs):
                splitting_detected = True
            else:
                flags.append("SOC_BANDS_NOT_DOUBLED")
        except Exception:
            flags.append("SPLITTING_CHECK_SKIPPED")

    # 7
    # For non-spin-polarised collinear cálculo, <Sz> debe be ~0
    spurious_mag = False
    try:
        mag = float(calc.get_magnetic_moment())
        if abs(mag) > 0.05:
            spurious_mag = True
            flags.append(f"SPURIOUS_MAGNETISATION:{mag:.4f} μB")
    except Exception:
        pass

    return SOCReport(
        soc_applied=True,
        gap_no_soc_eV=gap_no_soc,
        gap_soc_eV=gap_soc,
        chi_soc_eV=chi_soc,
        chi_soc_plausible=chi_plausible,
        splitting_detected=splitting_detected,
        spurious_magnetisation=spurious_mag,
        n_kpts=nkpts,
        n_bands_soc=n_bands_soc,
        flags=flags,
    )


def soc_was_applied(soc_dir: str | Path) -> bool:
    """Devuelve True si SOC salida archivos exist en dado step directorio."""
    soc_dir = Path(soc_dir)
    return (soc_dir / "soc_eigenvalues.npy").exists()
