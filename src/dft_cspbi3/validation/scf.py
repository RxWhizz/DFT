"""Valida convergencia SCF desde txt/.gpw."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# GPAW 24.x SCF línea
_ITER_RE = re.compile(
    r"^iter:\s+\d+\s+\d+:\d+:\d+\s+([-\d.]+(?:[eE][+-]?\d+)?)",
    re.MULTILINE,
)
_CONVERGED_RE = re.compile(r"Converged", re.IGNORECASE)
_NOT_CONVERGED_RE = re.compile(r"Did not converge", re.IGNORECASE)


# Data classes


@dataclass
class SCFReport:
    """Resultado análisis SCF."""

    converged: bool
    iterations: int
    final_energy_change_eV: float
    oscillating: bool
    energy_history: list[float] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return self.converged and not self.oscillating and not self.flags


@dataclass
class PhysicalChecks:
    """Chequeos físicos básicos GPAW."""

    energy_negative: bool
    energy_eV: float
    n_electrons: float
    fermi_level_eV: float
    occupations_consistent: bool
    occupations_sum: float
    flags: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return self.energy_negative and self.occupations_consistent and not self.flags


# SCF text-salida validación


def validate_scf(
    txt_file: str | Path,
    oscillation_window: int = 6,
    oscillation_threshold_eV: float = 1e-3,
) -> SCFReport:
    """Parsea log SCF; evalúa convergencia."""
    txt_file = Path(txt_file)
    flags: list[str] = []

    if not txt_file.exists():
        return SCFReport(
            converged=False,
            iterations=0,
            final_energy_change_eV=float("inf"),
            oscillating=False,
            flags=[f"FILE_NOT_FOUND:{txt_file}"],
        )

    text = txt_file.read_text(encoding="utf-8", errors="replace")
    energies = [float(m.group(1)) for m in _ITER_RE.finditer(text)]

    converged = bool(_CONVERGED_RE.search(text))
    if _NOT_CONVERGED_RE.search(text):
        flags.append("SCF_DID_NOT_CONVERGE")
    if not converged:
        flags.append("CONVERGENCE_FLAG_MISSING")

    iterations = len(energies)
    final_de = abs(energies[-1] - energies[-2]) if len(energies) >= 2 else float("inf")

    # Oscilacion.
    oscillating = False
    if len(energies) >= oscillation_window:
        tail = np.array(energies[-oscillation_window:])
        diffs = np.diff(tail)
        sign_changes = int(np.sum(np.diff(np.sign(diffs)) != 0))
        # Mitad ventana alterna + ultimo |ΔE| grande → oscila.
        if sign_changes >= oscillation_window // 2 and final_de > oscillation_threshold_eV:
            oscillating = True
            flags.append("SCF_OSCILLATING")

    return SCFReport(
        converged=converged,
        iterations=iterations,
        final_energy_change_eV=final_de,
        oscillating=oscillating,
        energy_history=energies,
        flags=flags,
    )


# Checks consistencia fisica en checkpoint .gpw.


def validate_physical_checks(gpw_file: str | Path) -> PhysicalChecks:
    """Verifica consistencia física GPAW."""
    from gpaw import GPAW

    calc = GPAW(str(gpw_file))
    flags: list[str] = []

    etot = float(calc.get_potential_energy())
    n_elec = float(calc.get_number_of_electrons())
    ef = float(calc.get_fermi_level())

    if etot >= 0:
        flags.append("ENERGY_NOT_NEGATIVE")

    occ_sum: float = float("nan")
    occ_ok = False
    try:
        # GPAW ya pondera ocupaciones por peso k.
        if hasattr(calc, "get_k_point_weights"):
            nk = len(calc.get_k_point_weights())
            occ_sum = float(sum(
                calc.get_occupation_numbers(kpt=k).sum() for k in range(nk)
            ))
        else:
            occ_sum = float(calc.get_occupation_numbers().sum())
        occ_ok = abs(occ_sum - n_elec) < 0.1
        if not occ_ok:
            flags.append(f"OCC_INCONSISTENT:sum={occ_sum:.3f},N_elec={n_elec:.3f}")
    except Exception as exc:
        flags.append(f"OCC_CHECK_FAILED:{exc}")

    return PhysicalChecks(
        energy_negative=etot < 0,
        energy_eV=etot,
        n_electrons=n_elec,
        fermi_level_eV=ef,
        occupations_consistent=occ_ok,
        occupations_sum=occ_sum,
        flags=flags,
    )


# Bandgap physical classification


def classify_electronic_structure(gpw_file: str | Path) -> dict:
    """Clasifica metal/semiconductor/aislante."""
    from gpaw import GPAW

    calc = GPAW(str(gpw_file))
    ef = float(calc.get_fermi_level())

    result: dict = {"fermi_level_eV": ef}

    try:
        homo, lumo = calc.get_homo_lumo()
        gap = float(lumo - homo)
        result["homo_eV"] = float(homo)
        result["lumo_eV"] = float(lumo)
        result["bandgap_eV"] = gap

        if gap < 0.05:
            result["type"] = "metallic"
        elif gap < 3.0:
            result["type"] = "semiconductor"
        else:
            result["type"] = "insulator"
    except Exception as exc:
        logger.warning("Could not compute HOMO/LUMO: %s", exc)
        result["type"] = "unknown"
        result["bandgap_eV"] = None

    return result
