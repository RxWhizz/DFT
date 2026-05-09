"""Workflow CI-NEB para barreras entre estructuras."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
from ase import Atoms

logger = logging.getLogger(__name__)

# Typical bond lengths para nearest-neighbour search [Å]
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
    energies_eV: np.ndarray          # shape (n_total_images,) vs image 0
    barrier_forward_meV: float
    barrier_reverse_meV: float
    saddle_image_idx: int
    converged: bool
    n_images: int
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
    """Ejecuta CI-NEB entre two structures find transition state."""
    from ase.mep.neb import NEB, NEBOptimizer

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    # Construye image list
    images = [atoms_start.copy()]
    for _ in range(n_images):
        images.append(atoms_start.copy())
    images.append(atoms_end.copy())

    neb = NEB(images, k=k, climb=False)
    neb.interpolate()

    # Assign independent calculators interior images only
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
    energies -= energies[0]
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


# Migration endpoint builder para systematic ionic migration en CsPbI₃

def _nearest_neighbour_idx(atoms: Atoms, ref_idx: int, elem: str, r_cut: float) -> list[int]:
    """Devuelve indices atoms type `elem` within r_cut atom ref_idx."""
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
    """Genera (start, end, label) endpoint pairs para ionic migration NEB."""
    from .defects import build_defect_supercell

    sc = atoms.repeat(supercell_matrix)
    syms = sc.get_chemical_symbols()
    pos  = sc.get_positions()
    cell = sc.get_cell().array

    endpoints: list[tuple[Atoms, Atoms, str]] = []

    if defect_type == "V_I":
        # Find first I atom as vacancy site
        i_indices = [i for i, s in enumerate(syms) if s == "I"]
        if not i_indices:
            raise RuntimeError("No I atoms found in supercell")

        vac_idx = i_indices[0]
        r_cut = _BOND_CUTOFFS["I-I"] if path_type == "100" else _BOND_CUTOFFS["I-I"] * 1.5
        neighbours = _nearest_neighbour_idx(sc, vac_idx, "I", r_cut)

        if not neighbours:
            raise RuntimeError(f"No I neighbours found for V_I path_type={path_type}")

        # Keep only <100> o <110> direction neighbours
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

        for end_idx in filtered[:2]:    # máximo 2 rutas no equivalentes
            # Start
            start_sc = sc.copy()
            del start_sc[vac_idx]

            # End
            end_sc = sc.copy()
            del end_sc[end_idx]

            label = f"V_I_{path_type}_hop_{vac_idx}_to_{end_idx}"
            endpoints.append((start_sc, end_sc, label))
            logger.info("Built migration endpoints: %s", label)

    elif defect_type == "I_i":
        # Two interstitial sites en fractional [0.5,0.5,0.5] y adjacent [1.0,0.5,0.5]
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
            # Fallback
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
    """Construye migration endpoints y ejecuta CI-NEB para each ruta."""
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
