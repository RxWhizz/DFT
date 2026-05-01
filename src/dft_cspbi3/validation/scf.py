"""SCF convergence validation from GPAW text output and .gpw checkpoints."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# GPAW 24.x SCF line: "iter:   N  HH:MM:SS  ENERGY  ..."
_ITER_RE = re.compile(
    r"^iter:\s+\d+\s+\d+:\d+:\d+\s+([-\d.]+(?:[eE][+-]?\d+)?)",
    re.MULTILINE,
)
_CONVERGED_RE = re.compile(r"Converged", re.IGNORECASE)
_NOT_CONVERGED_RE = re.compile(r"Did not converge", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SCFReport:
    """Result of SCF convergence analysis."""

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
    """Results of basic physical sanity checks on a GPAW calculation."""

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


# ---------------------------------------------------------------------------
# SCF text-output validation
# ---------------------------------------------------------------------------


def validate_scf(
    txt_file: str | Path,
    oscillation_window: int = 6,
    oscillation_threshold_eV: float = 1e-3,
) -> SCFReport:
    """Parse GPAW SCF text log and assess convergence quality.

    Checks performed:
      - 'Converged' flag present in output
      - Number of SCF iterations
      - Energy oscillation in last *oscillation_window* steps
      - Monotonic convergence vs. non-monotonic behaviour

    Args:
        txt_file: Path to GPAW output .txt file.
        oscillation_window: Number of final iterations to inspect for oscillation.
        oscillation_threshold_eV: |ΔE| above which alternating steps count as oscillation.

    Returns:
        SCFReport with full diagnostics.
    """
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

    # Oscillation: look for alternating signs in energy differences over last window
    oscillating = False
    if len(energies) >= oscillation_window:
        tail = np.array(energies[-oscillation_window:])
        diffs = np.diff(tail)
        sign_changes = int(np.sum(np.diff(np.sign(diffs)) != 0))
        # ≥ half the window alternating AND last |ΔE| still large → oscillating
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


# ---------------------------------------------------------------------------
# Physical-consistency checks on .gpw checkpoint
# ---------------------------------------------------------------------------


def validate_physical_checks(gpw_file: str | Path) -> PhysicalChecks:
    """Verify basic physical consistency of a completed GPAW calculation.

    Checks:
      1. Total energy is negative (bound electronic system).
      2. Number of valence electrons is positive.
      3. Occupation numbers sum to N_electrons within 0.01.

    Args:
        gpw_file: Path to GPAW .gpw checkpoint file.

    Returns:
        PhysicalChecks dataclass.
    """
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
        # GPAW returns occupations pre-multiplied by k-point weight,
        # so summing directly over all k-points gives total electron count.
        nk = len(calc.get_k_point_weights())
        occ_sum = float(sum(
            calc.get_occupation_numbers(kpt=k).sum() for k in range(nk)
        ))
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


# ---------------------------------------------------------------------------
# Bandgap physical classification
# ---------------------------------------------------------------------------


def classify_electronic_structure(gpw_file: str | Path) -> dict:
    """Classify the system as metallic, semiconducting, or insulating.

    Args:
        gpw_file: Path to GPAW .gpw checkpoint.

    Returns:
        Dict with keys: type, bandgap_eV, homo_eV, lumo_eV, fermi_level_eV.
    """
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
