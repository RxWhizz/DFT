"""Potential energy surface (PES) scan along soft phonon modes.

Detects soft modes from the Hessian, scans E(Q) via finite displacement,
and identifies double-well potentials (saddle points).
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
class PESScanResult:
    displacements_Ang: np.ndarray    # shape (n_steps,) — Q values in Å
    energies_eV: np.ndarray          # shape (n_steps,) — E(Q) relative to Q=0
    mode_index: int
    eigenvalue_eV_Ang2: float
    double_well_detected: bool
    barrier_meV: float               # barrier height if double well, else 0
    saddle_Q_Ang: float              # Q of saddle point, else 0
    q_min1_Ang: float                # Q of left minimum (0 if no double well)
    q_min2_Ang: float                # Q of right minimum (0 if no double well)
    atoms_min1: Optional[Atoms]
    atoms_min2: Optional[Atoms]
    flags: list[str] = field(default_factory=list)


def detect_soft_modes(
    hessian_npy: str | Path,
    threshold: float = 0.05,
) -> list[tuple[int, float, np.ndarray]]:
    """Recompute eigenvectors from the Hessian and return quasi-zero/negative modes.

    Args:
        hessian_npy: Path to hessian.npy (shape 3N×3N, eV/Å²).
        threshold: Eigenvalue cutoff in eV/Å². The default matches the Hessian
            numerical floor used in the stability classifier; modes above it are
            positive-curvature vibrations and do not trigger the expensive PES scan.

    Returns:
        List of (mode_index, eigenvalue, eigenvector_3N) sorted by eigenvalue.
    """
    H = np.load(str(hessian_npy))
    eigs, evecs = np.linalg.eigh(H)   # evecs[:, i] is eigenvector i
    soft = [
        (i, float(eigs[i]), evecs[:, i])
        for i in range(len(eigs))
        if eigs[i] < threshold
    ]
    return sorted(soft, key=lambda x: x[1])


def _detect_double_well(
    q_values: np.ndarray,
    energies_rel: np.ndarray,
    barrier_threshold_meV: float = 10.0,
) -> tuple[bool, float, float, float, float]:
    """Detect a double-well potential from a 1D energy scan.

    Algorithm:
      1. Find the global maximum (candidate saddle point).
      2. Find the minimum to the left of the maximum.
      3. Find the minimum to the right of the maximum.
      4. Compute barrier relative to the higher of the two minima.
      5. Classify as double well if barrier > threshold and saddle is interior.

    Returns:
        (detected, barrier_meV, q_saddle, q_min1, q_min2)
    """
    n = len(energies_rel)
    if n < 5:
        return False, 0.0, 0.0, q_values[0], q_values[-1]

    i_max = int(np.argmax(energies_rel))

    # Saddle must not be at the boundary
    if i_max == 0 or i_max == n - 1:
        return False, 0.0, 0.0, q_values[0], q_values[-1]

    i_min1 = int(np.argmin(energies_rel[:i_max]))
    i_min2 = int(np.argmin(energies_rel[i_max + 1:])) + i_max + 1

    e_saddle = energies_rel[i_max]
    e_ref = max(energies_rel[i_min1], energies_rel[i_min2])
    barrier_eV = e_saddle - e_ref
    barrier_meV = barrier_eV * 1000.0

    detected = barrier_meV > barrier_threshold_meV
    return (
        detected,
        float(barrier_meV),
        float(q_values[i_max]),
        float(q_values[i_min1]),
        float(q_values[i_min2]),
    )


def scan_pes_1d(
    atoms: Atoms,
    factory,
    eigenvector: np.ndarray,
    n_steps: int = 20,
    amplitude: float = 0.5,
    work_dir: Path = Path("."),
    mode_index: int = 0,
    eigenvalue: float = 0.0,
    barrier_threshold_meV: float = 10.0,
) -> PESScanResult:
    """Scan E(Q) by displacing atoms ±amplitude Å along the eigenvector.

    Caching: each point is saved to E_NNN.npy to allow restarts.
    The eigenvector is normalized to unit norm before use.
    The reference energy E(Q=0) is stored in E_ref.npy.

    Args:
        atoms: Relaxed Atoms object (reference geometry).
        factory: GPAWCalculatorFactory instance.
        eigenvector: Shape (3N,) — soft mode eigenvector.
        n_steps: Number of displacement points in [-amplitude, +amplitude].
        amplitude: Maximum displacement in Å.
        work_dir: Directory for cached energies and GPAW logs.
        mode_index: Index of the mode (for labeling).
        eigenvalue: Eigenvalue of the mode in eV/Å².
        barrier_threshold_meV: Minimum barrier to classify as double well.

    Returns:
        PESScanResult with E(Q) curve and double-well analysis.
    """
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    n_atoms = len(atoms)
    evec_norm = eigenvector / np.linalg.norm(eigenvector)
    q_values = np.linspace(-amplitude, amplitude, n_steps)

    # Reference energy at Q=0
    E_ref_cache = work_dir / "E_ref.npy"
    if not E_ref_cache.exists():
        logger.info("Computing reference energy at Q=0 …")
        calc_ref = factory.create(
            "scf",
            params_override={"symmetry": "off"},
            txt=str(work_dir / "scf_ref.txt"),
        )
        atoms_ref = atoms.copy()
        atoms_ref.calc = calc_ref
        E_ref = atoms_ref.get_potential_energy()
        np.save(str(E_ref_cache), np.array([E_ref]))
        logger.info("E_ref = %.6f eV", E_ref)
    E_ref = float(np.load(str(E_ref_cache))[0])

    # Scan
    energies_abs: list[float] = []
    for i, q in enumerate(q_values):
        cache = work_dir / f"E_{i:03d}.npy"
        if cache.exists():
            energies_abs.append(float(np.load(str(cache))))
            logger.debug("Step %d/%d (Q=%.3f Å): loaded from cache", i + 1, n_steps, q)
            continue

        logger.info("Step %d/%d  Q = %+.3f Å …", i + 1, n_steps, q)
        displaced = atoms.copy()
        displaced.positions += q * evec_norm.reshape(n_atoms, 3)
        calc = factory.create(
            "scf",
            params_override={"symmetry": "off"},
            txt=str(work_dir / f"scf_{i:03d}.txt"),
        )
        displaced.calc = calc
        E = displaced.get_potential_energy()
        np.save(str(cache), np.array([E]))
        energies_abs.append(E)

    energies_rel = np.array(energies_abs) - E_ref

    # Double-well analysis
    detected, barrier_meV, q_saddle, q_min1, q_min2 = _detect_double_well(
        q_values, energies_rel, barrier_threshold_meV
    )

    # Build Atoms objects at the two minima (if double well)
    atoms_min1: Optional[Atoms] = None
    atoms_min2: Optional[Atoms] = None
    if detected:
        atoms_min1 = atoms.copy()
        atoms_min1.positions += q_min1 * evec_norm.reshape(n_atoms, 3)
        atoms_min2 = atoms.copy()
        atoms_min2.positions += q_min2 * evec_norm.reshape(n_atoms, 3)

    flags: list[str] = []
    if detected:
        flags.append(f"double_well: barrier={barrier_meV:.1f} meV at Q={q_saddle:.3f} Å")

    return PESScanResult(
        displacements_Ang=q_values,
        energies_eV=energies_rel,
        mode_index=mode_index,
        eigenvalue_eV_Ang2=eigenvalue,
        double_well_detected=detected,
        barrier_meV=barrier_meV,
        saddle_Q_Ang=q_saddle,
        q_min1_Ang=q_min1,
        q_min2_Ang=q_min2,
        atoms_min1=atoms_min1,
        atoms_min2=atoms_min2,
        flags=flags,
    )
