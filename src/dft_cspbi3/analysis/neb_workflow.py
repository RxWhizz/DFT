"""CI-NEB workflow for computing transition state barriers between two structures.

Uses ASE's NEB implementation with GPAW calculators. Designed for transitions
between structures found via PES scan (double-well minima), but works for any
two Atoms objects with the same cell.

Extended with build_migration_endpoints() for systematic ionic migration paths
in CsPbI₃: V_I <100>/<110> hops, I_i interstitial migration, V_Cs A-site jumps.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
from ase import Atoms

logger = logging.getLogger(__name__)

# Typical bond lengths for nearest-neighbour search [Å]
_BOND_CUTOFFS: dict[str, float] = {
    "I-I":   4.5,
    "Pb-I":  3.5,
    "Cs-I":  4.8,
    "Pb-Pb": 5.5,
    "Cs-Pb": 5.5,
}

@dataclass
class NEBResult:
    images: list[Atoms]
    energies_eV: np.ndarray          # shape (n_total_images,) relative to image 0
    barrier_forward_meV: float        # E_saddle − E_start
    barrier_reverse_meV: float        # E_saddle − E_end
    saddle_image_idx: int
    converged: bool
    n_images: int                     # total including endpoints
    flags: list[str] = field(default_factory=list)


def run_cineb(
    atoms_start: Atoms,
    atoms_end: Atoms,
    factory,
    work_dir: Path,
    n_images: int = 7,
    fmax: float = 0.10,
    k: float = 0.10,
    max_steps: int = 200,
) -> NEBResult:
    """Run CI-NEB between two structures to find the transition state.

    Strategy:
      1. Build images by linear interpolation.
      2. Assign independent GPAW calculators to interior images.
      3. Stage 1 — plain NEB (climb=False) to fmax*3 for initial relaxation.
      4. Stage 2 — CI-NEB (climb=True) to fmax for saddle-point refinement.
      5. Collect energies relative to the start image.

    Args:
        atoms_start: Starting structure (endpoint 1).
        atoms_end: Ending structure (endpoint 2).
        factory: GPAWCalculatorFactory instance.
        work_dir: Directory for GPAW logs and cached data.
        n_images: Number of interior NEB images (excluding endpoints).
        fmax: Convergence criterion in eV/Å.
        k: Spring constant in eV/Å².
        max_steps: Maximum optimizer steps per stage.

    Returns:
        NEBResult with optimized images, energies, and barrier heights.
    """
    from ase.mep.neb import NEB, NEBOptimizer

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    # Build image list: endpoints + n_images interior images
    images = [atoms_start.copy()]
    for _ in range(n_images):
        images.append(atoms_start.copy())
    images.append(atoms_end.copy())

    neb = NEB(images, k=k, climb=False)
    neb.interpolate()

    # Assign independent calculators to interior images only
    for i, image in enumerate(images[1:-1], start=1):
        calc = factory.create(
            "scf",
            params_override={"symmetry": "off"},
            txt=str(work_dir / f"neb_{i:02d}.txt"),
        )
        image.calc = calc

    logger.info("NEB: stage 1 (plain NEB) — %d interior images …", n_images)
    opt1 = NEBOptimizer(neb)
    opt1.run(fmax=fmax * 3, steps=max_steps // 2)

    logger.info("NEB: stage 2 (CI-NEB) — climbing image …")
    neb.climb = True
    opt2 = NEBOptimizer(neb)
    converged = opt2.run(fmax=fmax, steps=max_steps)

    # Collect energies
    energies = np.array([img.get_potential_energy() for img in images])
    energies -= energies[0]   # relative to start image
    saddle_idx = int(np.argmax(energies))

    barrier_fwd = float(energies[saddle_idx] * 1000)
    barrier_rev = float((energies[saddle_idx] - energies[-1]) * 1000)

    flags: list[str] = []
    if not converged:
        flags.append(f"CI-NEB did not converge within {max_steps} steps")

    logger.info(
        "CI-NEB done: barrier_fwd=%.1f meV, barrier_rev=%.1f meV, converged=%s",
        barrier_fwd, barrier_rev, converged,
    )

    return NEBResult(
        images=images,
        energies_eV=energies,
        barrier_forward_meV=barrier_fwd,
        barrier_reverse_meV=barrier_rev,
        saddle_image_idx=saddle_idx,
        converged=bool(converged),
        n_images=len(images),
        flags=flags,
    )


# ---------------------------------------------------------------------------
# Migration endpoint builder for systematic ionic migration in CsPbI₃
# ---------------------------------------------------------------------------

def _nearest_neighbour_idx(atoms: Atoms, ref_idx: int, elem: str, r_cut: float) -> list[int]:
    """Return indices of atoms of type `elem` within r_cut of atom ref_idx."""
    pos = atoms.get_positions()
    cell = atoms.get_cell().array
    syms = atoms.get_chemical_symbols()
    ref = pos[ref_idx]

    neighbours: list[int] = []
    for j, (p, s) in enumerate(zip(pos, syms)):
        if j == ref_idx or s != elem:
            continue
        dr = p - ref
        # Minimum image (orthorhombic approx)
        for k in range(3):
            L = cell[k, k]
            dr[k] -= L * round(dr[k] / L)
        if float(np.linalg.norm(dr)) < r_cut:
            neighbours.append(j)
    return neighbours


def build_migration_endpoints(
    atoms: Atoms,
    defect_type: str,
    supercell_matrix: tuple[int, int, int] = (2, 2, 2),
    path_type: str = "100",
) -> list[tuple[Atoms, Atoms, str]]:
    """Generate (start, end, label) endpoint pairs for ionic migration NEB.

    Supported defect_type / path_type combinations:

    +----------+----------+----------------------------------------------+
    | defect   | path     | Description                                  |
    +----------+----------+----------------------------------------------+
    | V_I      | 100      | Vacancy hop along <100> between NN I sites   |
    | V_I      | 110      | Vacancy hop along <110> (diagonal jump)      |
    | I_i      | 100      | Interstitial I migration between body-centre |
    |          |          | sites along <100>                            |
    | V_Cs     | 100      | Cs vacancy hop to nearest A-site             |
    +----------+----------+----------------------------------------------+

    Args:
        atoms: Primitive cell Atoms (before building defect supercell).
        defect_type: "V_I", "I_i", or "V_Cs".
        supercell_matrix: Supercell expansion to use.
        path_type: "100" or "110".

    Returns:
        List of (start_atoms, end_atoms, path_label) ready for run_cineb().
    """
    from .defects import build_defect_supercell

    sc = atoms.repeat(supercell_matrix)
    syms = sc.get_chemical_symbols()
    pos  = sc.get_positions()
    cell = sc.get_cell().array

    endpoints: list[tuple[Atoms, Atoms, str]] = []

    if defect_type == "V_I":
        # Find first I atom as vacancy site; find NN I atoms for end points
        i_indices = [i for i, s in enumerate(syms) if s == "I"]
        if not i_indices:
            raise RuntimeError("No I atoms found in supercell")

        vac_idx = i_indices[0]   # source vacancy
        r_cut = _BOND_CUTOFFS["I-I"] if path_type == "100" else _BOND_CUTOFFS["I-I"] * 1.5
        neighbours = _nearest_neighbour_idx(sc, vac_idx, "I", r_cut)

        if not neighbours:
            raise RuntimeError(f"No I neighbours found for V_I path_type={path_type}")

        # Keep only <100> or <110> direction neighbours
        ref_pos = pos[vac_idx]
        filtered: list[int] = []
        for j in neighbours:
            dr = pos[j] - ref_pos
            for k in range(3):
                L = cell[k, k]
                dr[k] -= L * round(dr[k] / L)
            dr_norm = dr / (np.linalg.norm(dr) + 1e-12)
            n_nonzero = np.sum(np.abs(dr_norm) > 0.5)
            if path_type == "100" and n_nonzero == 1:
                filtered.append(j)
            elif path_type == "110" and n_nonzero == 2:
                filtered.append(j)

        for end_idx in filtered[:2]:    # at most 2 inequivalent paths
            # Start: remove atom at vac_idx
            start_sc = sc.copy()
            del start_sc[vac_idx]

            # End: remove atom at end_idx (vacancy has hopped there)
            end_sc = sc.copy()
            del end_sc[end_idx]

            label = f"V_I_{path_type}_hop_{vac_idx}_to_{end_idx}"
            endpoints.append((start_sc, end_sc, label))
            logger.info("Built migration endpoints: %s", label)

    elif defect_type == "I_i":
        # Two interstitial sites at fractional [0.5,0.5,0.5] and adjacent [1.0,0.5,0.5]
        from ase import Atoms as _Atoms

        def _frac_to_cart(frac, cell_arr):
            return cell_arr.T @ np.array(frac)

        site_a_frac = [0.5, 0.5, 0.5]
        site_b_frac = [1.0, 0.5, 0.5]

        site_a = _frac_to_cart(site_a_frac, cell)
        site_b = _frac_to_cart(site_b_frac, cell)

        start_sc = sc.copy()
        start_sc += _Atoms("I", positions=[site_a], cell=sc.cell, pbc=True)

        end_sc = sc.copy()
        end_sc += _Atoms("I", positions=[site_b], cell=sc.cell, pbc=True)

        label = "I_i_100_hop_bc_to_edge"
        endpoints.append((start_sc, end_sc, label))
        logger.info("Built migration endpoints: %s", label)

    elif defect_type == "V_Cs":
        cs_indices = [i for i, s in enumerate(syms) if s == "Cs"]
        if len(cs_indices) < 2:
            raise RuntimeError("Need at least 2 Cs atoms for V_Cs migration NEB")

        vac_idx = cs_indices[0]
        neighbours = _nearest_neighbour_idx(sc, vac_idx, "Cs", _BOND_CUTOFFS["Cs-Pb"])
        if not neighbours:
            # Fallback: next Cs atom
            neighbours = [cs_indices[1]]

        end_idx = neighbours[0]
        start_sc = sc.copy()
        del start_sc[vac_idx]

        end_sc = sc.copy()
        del end_sc[end_idx]

        label = f"V_Cs_100_hop_{vac_idx}_to_{end_idx}"
        endpoints.append((start_sc, end_sc, label))
        logger.info("Built migration endpoints: %s", label)

    else:
        raise ValueError(f"Unknown defect_type '{defect_type}'. Choose 'V_I', 'I_i', 'V_Cs'.")

    return endpoints


def run_migration_neb(
    atoms: Atoms,
    defect_type: str,
    factory,
    work_dir: Path,
    supercell_matrix: tuple[int, int, int] = (2, 2, 2),
    path_type: str = "100",
    n_images: int = 7,
    fmax: float = 0.10,
) -> list["NEBResult"]:
    """Build migration endpoints and run CI-NEB for each path.

    Convenience wrapper combining build_migration_endpoints() + run_cineb().

    Returns:
        List of NEBResult, one per migration path.
    """
    endpoints = build_migration_endpoints(atoms, defect_type, supercell_matrix, path_type)
    results: list[NEBResult] = []
    for start_sc, end_sc, label in endpoints:
        path_dir = Path(work_dir) / label
        logger.info("Running CI-NEB for migration path: %s", label)
        result = run_cineb(
            start_sc, end_sc, factory, path_dir,
            n_images=n_images, fmax=fmax,
        )
        result.flags.insert(0, f"PATH:{label}")
        results.append(result)
        logger.info(
            "%s: barrier_fwd=%.1f meV, barrier_rev=%.1f meV, converged=%s",
            label, result.barrier_forward_meV, result.barrier_reverse_meV, result.converged,
        )
    return results
