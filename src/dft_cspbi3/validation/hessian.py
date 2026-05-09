"""Hessiano por diferencias finitas con GPAW."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
from ase import Atoms

logger = logging.getLogger(__name__)

# Three translational zero-modes esperado para periodic system
_N_TRANS_MODES = 3

# Eigenvalue umbral para classifying mode as "zero" (translational)
_ZERO_EIGVAL_THRESHOLD = 0.05  # eV/Å²


# Data class


@dataclass
class HessianResult:
    """Resultado Hessiano finito."""

    hessian: np.ndarray                 # shape (3N, 3N), eV/Å²
    eigenvalues: np.ndarray             # shape (3N,), sorted ascending, eV/Å²
    eigenvectors: np.ndarray            # shape (3N, 3N)
    dynamical_matrix: np.ndarray        # mass-weighted H, shape (3N, 3N)
    n_atoms: int
    fmax_initial_eV_Ang: float
    delta_Ang: float
    n_negative: int
    n_zero: int
    forces_converged: bool
    flags: list[str] = field(default_factory=list)

    @property
    def stable(self) -> bool:
        """True si solo modos traslacionales no positivos."""
        return self.n_negative == 0

    @property
    def min_eigenvalue(self) -> float:
        return float(self.eigenvalues[0])

    @property
    def summary(self) -> str:
        status = "STABLE" if self.stable else f"UNSTABLE ({self.n_negative} negative modes)"
        return (
            f"Hessian {3 * self.n_atoms}×{3 * self.n_atoms} | "
            f"min λ = {self.min_eigenvalue:.4f} eV/Å² | {status}"
        )


# Prerequisite revisa


def check_forces(atoms: Atoms, threshold_eV_Ang: float = 0.05) -> tuple[bool, float]:
    """Devuelve (converged, fmax)."""
    forces = atoms.get_forces()
    fmax = float(np.max(np.abs(forces)))
    return fmax < threshold_eV_Ang, fmax


# Core computation


def compute_hessian(
    atoms: Atoms,
    calc,
    delta: float = 0.01,
    work_dir: Optional[Path] = None,
    force_threshold_eV_Ang: float = 0.05,
) -> HessianResult:
    """Calcula Hessiano 3N×3N por diferencias centrales."""
    atoms = atoms.copy()
    atoms.calc = calc

    if work_dir is not None:
        work_dir = Path(work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)

    flags: list[str] = []

    # Prerequisite
    forces0 = atoms.get_forces()
    fmax_initial = float(np.max(np.abs(forces0)))
    forces_ok = fmax_initial < force_threshold_eV_Ang
    if not forces_ok:
        flags.append(
            f"FORCES_NOT_CONVERGED:fmax={fmax_initial:.4f}eV/Å>"
            f"{force_threshold_eV_Ang}eV/Å — relax structure first"
        )
        logger.warning(
            "Initial fmax = %.4f eV/Å exceeds threshold %.4f eV/Å. "
            "Hessian may be unreliable. Continue with caution.",
            fmax_initial, force_threshold_eV_Ang,
        )

    N = len(atoms)
    ndof = 3 * N
    H = np.zeros((ndof, ndof))
    masses = atoms.get_masses()

    pos0 = atoms.get_positions().copy()

    logger.info("Computing Hessian for %d atoms (%d DOF) — %d GPAW calls required",
                N, ndof, 2 * ndof)

    for j in range(ndof):
        atom_j = j // 3
        xyz_j = j % 3

        # Cache archivo names
        tag = f"F_{atom_j}_{xyz_j}"
        cache_p = (work_dir / f"{tag}_plus.npy") if work_dir else None
        cache_m = (work_dir / f"{tag}_minus.npy") if work_dir else None

        if cache_p is not None and cache_p.exists() and cache_m.exists():
            f_plus = np.load(str(cache_p))
            f_minus = np.load(str(cache_m))
            logger.debug("Loaded cached forces for dof %d", j)
        else:
            # Adelante displacement
            pos = pos0.copy()
            pos[atom_j, xyz_j] += delta
            atoms.set_positions(pos)
            f_plus = atoms.get_forces().flatten()

            # Atrás displacement
            pos = pos0.copy()
            pos[atom_j, xyz_j] -= delta
            atoms.set_positions(pos)
            f_minus = atoms.get_forces().flatten()

            # Restaura equilibrium geometry
            atoms.set_positions(pos0)

            if cache_p is not None:
                np.save(str(cache_p), f_plus)
                np.save(str(cache_m), f_minus)

        H[:, j] = -(f_plus - f_minus) / (2.0 * delta)

    # Symmetrise enforce H = Hᵀ (removes finite-difference asymmetry)
    H = (H + H.T) / 2.0

    # Diagonalise
    eigenvalues, eigenvectors = np.linalg.eigh(H)

    # Mass-weighted dynamical matrix
    # m_i
    m_arr = np.repeat(masses, 3)          # shape (3N,)
    m_outer = np.outer(np.sqrt(m_arr), np.sqrt(m_arr))
    D = H / m_outer                       # units

    # Clasifica eigenvalues
    n_negative = int(np.sum(eigenvalues < -_ZERO_EIGVAL_THRESHOLD))
    n_zero = int(np.sum(np.abs(eigenvalues) <= _ZERO_EIGVAL_THRESHOLD))

    if n_negative > 0:
        flags.append(f"NEGATIVE_HESSIAN_EIGENVALUES:{n_negative}")

    if n_zero < _N_TRANS_MODES:
        flags.append(
            f"TOO_FEW_ZERO_MODES:{n_zero} (expected {_N_TRANS_MODES} translational)"
        )

    return HessianResult(
        hessian=H,
        eigenvalues=eigenvalues,
        eigenvectors=eigenvectors,
        dynamical_matrix=D,
        n_atoms=N,
        fmax_initial_eV_Ang=fmax_initial,
        delta_Ang=delta,
        n_negative=n_negative,
        n_zero=n_zero,
        forces_converged=forces_ok,
        flags=flags,
    )


# Hessiano desde cached fuerzas (resume sin re-corriendo GPAW)


def load_hessian_from_cache(
    atoms: Atoms,
    work_dir: Path,
    delta: float = 0.01,
) -> Optional[HessianResult]:
    """Reconstruct HessianResult desde previously cached fuerza.npy archivos."""
    N = len(atoms)
    ndof = 3 * N
    H = np.zeros((ndof, ndof))
    work_dir = Path(work_dir)

    for j in range(ndof):
        atom_j = j // 3
        xyz_j = j % 3
        tag = f"F_{atom_j}_{xyz_j}"
        fp = work_dir / f"{tag}_plus.npy"
        fm = work_dir / f"{tag}_minus.npy"

        if not (fp.exists() and fm.exists()):
            logger.warning("Cache incomplete at dof %d — missing %s or %s", j, fp, fm)
            return None

        f_plus = np.load(str(fp))
        f_minus = np.load(str(fm))
        H[:, j] = -(f_plus - f_minus) / (2.0 * delta)

    H = (H + H.T) / 2.0
    eigenvalues, eigenvectors = np.linalg.eigh(H)
    masses = atoms.get_masses()
    m_arr = np.repeat(masses, 3)
    D = H / np.outer(np.sqrt(m_arr), np.sqrt(m_arr))

    n_negative = int(np.sum(eigenvalues < -_ZERO_EIGVAL_THRESHOLD))
    n_zero = int(np.sum(np.abs(eigenvalues) <= _ZERO_EIGVAL_THRESHOLD))
    flags: list[str] = []
    if n_negative > 0:
        flags.append(f"NEGATIVE_HESSIAN_EIGENVALUES:{n_negative}")

    return HessianResult(
        hessian=H,
        eigenvalues=eigenvalues,
        eigenvectors=eigenvectors,
        dynamical_matrix=D,
        n_atoms=N,
        fmax_initial_eV_Ang=float("nan"),
        delta_Ang=delta,
        n_negative=n_negative,
        n_zero=n_zero,
        forces_converged=True,
        flags=flags,
    )
