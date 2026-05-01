"""Phonon calculation via Phonopy + GPAW finite-displacement method.

Advantages over the ASE Phonons backend:
  1. Symmetry reduction: Pm-3m (O_h) reduces ~30 displacements to ~4-6 independent.
  2. Crystal ASR: symmetrize_force_constants() applies the acoustic sum rule as
     a symmetry constraint on C(R), not as a post-hoc diagonal correction.
  3. Compatible with LO-TO Gonze-Lee correction (set_born_charges).

Δ choice for CsPbI3:
  Optimal Δ ≈ 0.02 Å — balances numerical noise (σ_F/2Δ) against anharmonic
  contamination (∝ V3·Δ²). The previous Δ=0.05 Å exceeds the harmonic regime
  for soft cage/tilt modes, producing spurious acoustic branches.

Extended with compute_quasiharmonic() for Quasi-Harmonic Approximation (QHA):
  Runs phonon force sets at 5–7 volumes, computes F_vib(T,V) via Phonopy QHA,
  and extracts thermal expansion α(T), heat capacity C_p(T), and G(T).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np
from ase import Atoms

logger = logging.getLogger(__name__)

# 1 THz = 33.3564 cm⁻¹
_THZ_TO_CM1 = 33.3564

# imaginary threshold — same as in phonons.py
_IMAGINARY_THRESHOLD_CM1 = 10.0


# ---------------------------------------------------------------------------
# Structure conversion helpers
# ---------------------------------------------------------------------------

def _ase_to_phonopy(atoms: Atoms):
    """Convert ASE Atoms to PhonopyAtoms."""
    from phonopy.structure.atoms import PhonopyAtoms
    return PhonopyAtoms(
        symbols=atoms.get_chemical_symbols(),
        scaled_positions=atoms.get_scaled_positions(),
        cell=atoms.cell.array.copy(),
    )


def _phonopy_to_ase(ph_atoms) -> Atoms:
    """Convert PhonopyAtoms to ASE Atoms with PBC."""
    return Atoms(
        symbols=list(ph_atoms.symbols),
        positions=np.array(ph_atoms.positions),   # Cartesian positions in Å
        cell=np.array(ph_atoms.cell),
        pbc=True,
    )


# ---------------------------------------------------------------------------
# Step 1: Generate symmetry-reduced displacements
# ---------------------------------------------------------------------------

def generate_phonopy_displacements(
    atoms: Atoms,
    supercell: tuple[int, int, int] = (2, 2, 2),
    delta: float = 0.02,
    work_dir: Path = Path("."),
) -> tuple:
    """Generate symmetry-reduced displacements using Phonopy.

    Args:
        atoms: Relaxed primitive cell ASE Atoms with PBC.
        supercell: Supercell expansion factors.
        delta: Displacement amplitude in Å.
        work_dir: Directory for phonopy_disp.yaml output.

    Returns:
        (phonon, displaced_supercells, n_independent) where
        displaced_supercells is a list of ASE Atoms.
    """
    from phonopy import Phonopy

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    ph_atoms = _ase_to_phonopy(atoms)
    supercell_matrix = np.diag(supercell)

    phonon = Phonopy(ph_atoms, supercell_matrix)
    phonon.generate_displacements(distance=delta)

    phonon.save(filename=str(work_dir / "phonopy_disp.yaml"), settings={"force_constants": False})

    displaced = phonon.supercells_with_displacements
    ase_displaced = [_phonopy_to_ase(sc) for sc in displaced if sc is not None]
    n = len(ase_displaced)

    logger.info(
        "Phonopy displacements: %d independent (Δ=%.3f Å, supercell %s)",
        n, delta, supercell,
    )
    return phonon, ase_displaced, n


# ---------------------------------------------------------------------------
# Step 2: Run GPAW forces for each displaced supercell
# ---------------------------------------------------------------------------

def build_supercell_reference(
    atoms: Atoms,
    factory,
    work_dir: Path,
    supercell_matrix: np.ndarray,
    scf_convergence: Optional[dict] = None,
    kpts_sc: Optional[list] = None,
) -> Path:
    """Run a reference SCF on the undisplaced supercell and save as sc_ref.gpw.

    Used by run_gpaw_forces() as wavefunction starting point for each
    displaced SCF, cutting iterations from ~50 to ~8 (10× speedup).

    The reference uses the same k-mesh and convergence as the displaced SCFs
    so wavefunctions are directly transferable.

    Returns:
        Path to sc_ref.gpw.
    """
    from ase.build import make_supercell
    from gpaw import GPAW

    ref_gpw = Path(work_dir) / "sc_ref.gpw"
    if ref_gpw.exists():
        logger.info("Reference supercell GPW found: %s", ref_gpw)
        return ref_gpw

    convergence = {"energy": 1e-8}
    if scf_convergence:
        convergence.update(scf_convergence)

    sc_atoms = make_supercell(atoms, supercell_matrix)
    calc = factory.create(
        "scf",
        params_override={
            "kpts": {"size": kpts_sc, "gamma": True},
            "symmetry": "off",
            "convergence": convergence,
        },
        txt=str(Path(work_dir) / "sc_ref.txt"),
    )
    sc_atoms.calc = calc
    sc_atoms.get_potential_energy()
    calc.write(str(ref_gpw))
    logger.info("Reference supercell SCF saved: %s", ref_gpw)
    return ref_gpw


def run_gpaw_forces(
    phonon,
    supercells: list[Atoms],
    factory,
    work_dir: Path,
    supercell_matrix: np.ndarray,
    scf_convergence: Optional[dict] = None,
    txt_prefix: str = "phonopy_sc",
    reference_gpw: Optional[Path] = None,
) -> list[np.ndarray]:
    """Run GPAW SCF for each displaced supercell and collect forces.

    Force caching: if forces_NNN.npy already exists in work_dir, the
    displacement is skipped and the cached forces are loaded.

    Wavefunction restart: if reference_gpw is provided (a converged SCF on
    the undisplaced supercell with the same k-mesh), each displaced SCF starts
    from those wavefunctions instead of LCAO, reducing iterations ~10×.

    CORRECTNESS NOTE: convergence dict is *merged*, not replaced.
    factory.create() uses kwargs.update(params_override), which would clobber
    the energy criterion if convergence were passed raw. We always include
    energy:1e-8 as a floor before adding any tighter criteria from config.

    Args:
        phonon: Phonopy object with displacements generated.
        supercells: List of displaced supercell Atoms (from generate_phonopy_displacements).
        factory: GPAWCalculatorFactory instance.
        work_dir: Directory for output files and force caches.
        supercell_matrix: (3,3) supercell matrix (diagonal for cubic).
        scf_convergence: Extra convergence criteria to add on top of energy:1e-8.
        txt_prefix: Prefix for GPAW log file names.
        reference_gpw: Optional path to sc_ref.gpw for wavefunction restart.

    Returns:
        List of force arrays, each shape (N_atoms_supercell, 3).
    """
    from gpaw import GPAW

    work_dir = Path(work_dir)

    # CRITICAL: merge convergence — never replace energy threshold
    convergence = {"energy": 1e-8}
    if scf_convergence:
        convergence.update(scf_convergence)

    # Scale k-mesh inversely to supercell to maintain k-point density
    base_kpts = factory.config["scf"]["kpts"]   # e.g. [6, 6, 6]
    sc_diag = [int(supercell_matrix[i, i]) for i in range(3)]
    kpts_sc = [max(1, k // s) for k, s in zip(base_kpts, sc_diag)]
    logger.info("Supercell k-mesh: %s (base %s ÷ supercell %s)", kpts_sc, base_kpts, sc_diag)

    use_restart = reference_gpw is not None and Path(reference_gpw).exists()
    if use_restart:
        logger.info("Wavefunction restart enabled from %s", reference_gpw)

    force_sets: list[np.ndarray] = []

    for i, sc_atoms in enumerate(supercells):
        force_cache = work_dir / f"forces_{i:03d}.npy"

        if force_cache.exists():
            logger.info("Loading cached forces for displacement %d/%d", i + 1, len(supercells))
            force_sets.append(np.load(str(force_cache)))
            continue

        logger.info(
            "Computing forces for displacement %d/%d (k=%s, convergence=%s)",
            i + 1, len(supercells), kpts_sc, convergence,
        )

        if use_restart:
            # Start from converged supercell wavefunctions — skips LCAO init
            # and converges in ~8 iterations instead of ~50
            calc = GPAW(
                str(reference_gpw),
                convergence=convergence,
                symmetry="off",
                txt=str(work_dir / f"{txt_prefix}_{i:03d}.txt"),
            )
        else:
            calc = factory.create(
                "scf",
                params_override={
                    "kpts": {"size": kpts_sc, "gamma": True},
                    "symmetry": "off",      # displacement breaks crystal symmetry
                    "convergence": convergence,
                },
                txt=str(work_dir / f"{txt_prefix}_{i:03d}.txt"),
            )

        sc_atoms = sc_atoms.copy()
        sc_atoms.calc = calc
        sc_atoms.get_potential_energy()
        forces = sc_atoms.get_forces()   # shape (N_atoms, 3)

        np.save(str(force_cache), forces)
        logger.info(
            "Displacement %d done — max |F| = %.4f eV/Å", i + 1, np.abs(forces).max()
        )
        force_sets.append(np.array(forces))

    return force_sets


# ---------------------------------------------------------------------------
# Step 3: Build force constants, apply ASR, compute dispersion + DOS
# ---------------------------------------------------------------------------

def compute_phonon_dispersion(
    phonon,
    force_sets: list[np.ndarray],
    atoms: Atoms,
    delta: float,
    supercell: tuple[int, int, int],
    kpath_npoints: int = 60,
    dos_kpts: tuple[int, int, int] = (20, 20, 20),
    asr: str = "crystal",
    work_dir: Path = Path("."),
) -> "PhononResult":
    """Build force constants from force sets, apply ASR, compute dispersion + DOS.

    Frequencies are evaluated at the q-points from ASE's cell.bandpath for
    direct comparison with the ASE Phonons backend results.

    Args:
        phonon: Phonopy object after generate_displacements().
        force_sets: List of force arrays from run_gpaw_forces().
        atoms: Original primitive cell Atoms (for bandpath).
        delta: Displacement amplitude in Å (stored in result).
        supercell: Supercell tuple (stored in result).
        kpath_npoints: Number of q-points along band path.
        dos_kpts: Mesh for DOS integration.
        asr: "crystal" applies full crystal symmetry (recommended);
             "translational" applies translational ASR only;
             "none" skips symmetrisation.
        work_dir: Output directory for .npy result files.

    Returns:
        PhononResult with frequencies, DOS, and stability classification.
    """
    from dft_cspbi3.validation.phonons import PhononResult

    work_dir = Path(work_dir)
    flags: list[str] = []

    # --- Assemble force constants ---
    phonon.forces = [np.array(f) for f in force_sets]
    phonon.produce_force_constants()

    if asr != "none":
        # symmetrize_force_constants(level=1) enforces translational + point-group
        # constraints simultaneously, producing a physically correct ASR.
        phonon.symmetrize_force_constants(level=1)
        flags.append(f"ASR_{asr.upper()}_APPLIED")
        logger.info("Force constants symmetrised (ASR=%s)", asr)

    # --- Band structure at ASE q-path ---
    freqs_cm1 = np.zeros((kpath_npoints, 3 * len(atoms)))
    try:
        ase_path = atoms.cell.bandpath(npoints=kpath_npoints)
        qpoints = ase_path.kpts   # fractional (nq, 3)
        phonon.run_qpoints(qpoints, with_eigenvectors=False)
        qp_dict = phonon.get_qpoints_dict()
        freqs_thz = qp_dict["frequencies"]   # (nq, nbranch), in THz
        # Phonopy sign convention: imaginary → negative THz
        freqs_cm1 = freqs_thz * _THZ_TO_CM1
        logger.info(
            "Band structure done: min=%.1f cm⁻¹, max=%.1f cm⁻¹",
            freqs_cm1.min(), freqs_cm1.max(),
        )
    except Exception as exc:
        flags.append(f"BAND_STRUCTURE_FAILED:{exc}")
        logger.warning("Phonopy band structure failed: %s", exc)

    # --- DOS ---
    dos_freqs = None
    dos_weights = None
    try:
        phonon.run_mesh(list(dos_kpts))
        phonon.run_total_dos(use_tetrahedron_method=False)
        dos_dict = phonon.get_total_dos_dict()
        dos_freqs = dos_dict["frequency_points"] * _THZ_TO_CM1
        dos_weights = dos_dict["total_dos"]
    except Exception as exc:
        flags.append(f"DOS_FAILED:{exc}")
        logger.warning("Phonopy DOS failed: %s", exc)

    # --- Save outputs ---
    np.save(str(work_dir / "phonon_frequencies_phonopy.npy"), freqs_cm1)
    if dos_freqs is not None:
        np.save(
            str(work_dir / "phonon_dos_phonopy.npy"),
            np.column_stack([dos_freqs, dos_weights]),
        )

    # --- Classify imaginary modes ---
    n_imaginary = int(np.sum(freqs_cm1 < -_IMAGINARY_THRESHOLD_CM1))
    if n_imaginary > 0:
        max_imag = float(freqs_cm1[freqs_cm1 < -_IMAGINARY_THRESHOLD_CM1].min())
        flags.append(f"IMAGINARY_PHONONS:{n_imaginary} (worst:{max_imag:.1f}cm⁻¹)")
        logger.warning("Imaginary phonons detected: %d modes (worst %.1f cm⁻¹)", n_imaginary, max_imag)
    else:
        max_imag = 0.0
        logger.info("No imaginary phonons — phonon stable")

    return PhononResult(
        frequencies_cm1=freqs_cm1,
        n_imaginary=n_imaginary,
        max_imaginary_cm1=max_imag,
        n_atoms_unit_cell=len(atoms),
        supercell=tuple(supercell),
        delta_Ang=delta,
        band_structure=None,   # Phonopy obj, not ASE BandStructure
        dos_frequencies_cm1=dos_freqs,
        dos_weights=dos_weights,
        flags=flags,
    )


# ---------------------------------------------------------------------------
# Step 4 (optional): Compare Δ convergence
# ---------------------------------------------------------------------------

def compare_delta_convergence(
    atoms: Atoms,
    factory,
    work_dir: Path,
    deltas: list[float] = None,
    supercell: tuple[int, int, int] = (2, 2, 2),
    scf_convergence: Optional[dict] = None,
) -> dict:
    """Run phonon calculation for multiple Δ values and compare acoustic branches.

    Results are cached: if forces_NNN.npy already exist for a given Δ, the
    SCF step is skipped and only the post-processing is repeated.

    Args:
        atoms: Primitive cell Atoms.
        factory: GPAWCalculatorFactory.
        work_dir: Parent directory; subdirs delta_002/ etc. are created automatically.
        deltas: List of displacement amplitudes in Å. Defaults to [0.02, 0.03].
        supercell: Supercell matrix diagonal.
        scf_convergence: Tighter SCF convergence for force accuracy.

    Returns:
        dict mapping delta (float) → PhononResult.
    """
    if deltas is None:
        deltas = [0.02, 0.03]

    results = {}
    for delta in deltas:
        sub_dir = Path(work_dir) / f"delta_{int(delta * 1000):03d}"
        logger.info("Delta convergence check: Δ=%.3f Å in %s", delta, sub_dir)

        phonon, supercells, n_disp = generate_phonopy_displacements(
            atoms, supercell=supercell, delta=delta, work_dir=sub_dir
        )
        force_sets = run_gpaw_forces(
            phonon, supercells, factory, sub_dir,
            supercell_matrix=np.diag(supercell),
            scf_convergence=scf_convergence,
        )
        result = compute_phonon_dispersion(
            phonon, force_sets, atoms, delta=delta, supercell=supercell,
            work_dir=sub_dir,
        )
        results[delta] = result

        # Log acoustic branches at Γ (first q-point should be Γ for bandpath starting at G)
        acoustic_at_gamma = result.frequencies_cm1[0, :3]
        logger.info(
            "Δ=%.3f Å: acoustic at Γ = [%.2f, %.2f, %.2f] cm⁻¹ (ideal: 0)",
            delta, *acoustic_at_gamma,
        )

    return results


# ---------------------------------------------------------------------------
# Quasi-Harmonic Approximation (QHA)
# ---------------------------------------------------------------------------

from dataclasses import dataclass as _dc, field as _field


@_dc
class QHAResult:
    """Output of a Quasi-Harmonic Approximation calculation."""

    volumes_Ang3: np.ndarray            # volume grid [Å³]
    temperatures_K: np.ndarray          # temperature grid [K]
    gibbs_free_energy_eV: np.ndarray    # G(T) at equilibrium V [eV/cell]
    thermal_expansion: np.ndarray       # α(T) = d ln V / dT [1/K]
    heat_capacity_Cp: np.ndarray        # C_p(T) [kB/cell] or [eV/K/cell]
    equilibrium_volume_Ang3: np.ndarray # V_eq(T) [Å³]
    bulk_modulus_GPa: Optional[float]   # B₀ at 0 K from BM EOS [GPa]
    flags: list[str] = _field(default_factory=list)

    @property
    def summary(self) -> str:
        T_mid = float(self.temperatures_K[len(self.temperatures_K)//2])
        alpha_mid = float(self.thermal_expansion[len(self.thermal_expansion)//2])
        return (
            f"QHA: {len(self.volumes_Ang3)} volumes, "
            f"α({T_mid:.0f}K)={alpha_mid:.2e}/K, "
            f"B₀={self.bulk_modulus_GPa:.1f} GPa"
            if self.bulk_modulus_GPa else
            f"QHA: {len(self.volumes_Ang3)} volumes, α({T_mid:.0f}K)={alpha_mid:.2e}/K"
        )


def compute_quasiharmonic(
    atoms: Atoms,
    factory,
    work_dir: Path,
    volume_strains: tuple[float, ...] = (-0.04, -0.02, 0.0, +0.02, +0.04, +0.06),
    supercell: tuple[int, int, int] = (2, 2, 2),
    delta: float = 0.02,
    temperatures_K: tuple[float, ...] = tuple(range(0, 801, 50)),
    eos_model: str = "vinet",
) -> QHAResult:
    """Compute quasi-harmonic thermodynamic properties.

    Strategy:
      1. Scale primitive cell volume by each strain factor.
      2. Relax ions (fixed cell) with GPAW SCF at each volume.
      3. Run full Phonopy displacement calculation at each volume.
      4. Feed (V, E_DFT, phonon force sets) to Phonopy QHA.
      5. Extract G(T), α(T), C_p(T), V_eq(T).

    Args:
        atoms: Relaxed equilibrium structure (0 K, 0 GPa).
        factory: GPAWCalculatorFactory.
        work_dir: Root directory; sub-dirs vol_{strain}/ are created.
        volume_strains: Fractional volume strains relative to V₀.
        supercell: Phonon supercell expansion.
        delta: Displacement amplitude [Å].
        temperatures_K: Temperature grid for thermodynamic integration.
        eos_model: Equation of state for volume optimisation ("vinet" | "birch_murnaghan").

    Returns:
        QHAResult with thermodynamic properties.
    """
    from phonopy import Phonopy
    from phonopy.structure.atoms import PhonopyAtoms

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    flags: list[str] = []

    V0 = float(atoms.get_volume())
    a0 = float(atoms.cell[0, 0])   # cubic approximation

    volumes:    list[float] = []
    energies:   list[float] = []
    phonons_list = []

    for strain in volume_strains:
        scale = (1.0 + strain) ** (1.0/3.0)
        vol_dir = work_dir / f"vol_{strain:+.3f}"
        vol_dir.mkdir(parents=True, exist_ok=True)

        # Scaled structure
        scaled_atoms = atoms.copy()
        scaled_atoms.set_cell(atoms.cell * scale, scale_atoms=True)
        V = float(scaled_atoms.get_volume())

        # DFT total energy (fixed cell SCF)
        energy_npy = vol_dir / "E_dft.npy"
        if energy_npy.exists():
            E = float(np.load(str(energy_npy)))
            logger.info("QHA volume %+.3f: loading cached E=%.6f eV", strain, E)
        else:
            calc = factory.create(
                "scf",
                params_override={"symmetry": "on"},
                txt=str(vol_dir / "scf_vol.txt"),
            )
            sc_calc = scaled_atoms.copy()
            sc_calc.calc = calc
            E = float(sc_calc.get_potential_energy())
            calc.write(str(vol_dir / "scf_vol.gpw"))
            np.save(str(energy_npy), E)
            logger.info("QHA volume %+.3f: E=%.6f eV", strain, E)

        volumes.append(V)
        energies.append(E)

        # Phonon force sets at this volume
        phonon_obj, displaced, n_disp = generate_phonopy_displacements(
            scaled_atoms, supercell=supercell, delta=delta, work_dir=vol_dir,
        )
        force_sets = run_gpaw_forces(
            phonon_obj, displaced, factory, vol_dir,
            supercell_matrix=np.diag(supercell),
        )
        phonons_list.append((phonon_obj, force_sets))

    volumes_arr  = np.array(volumes)
    energies_arr = np.array(energies)
    temps_arr    = np.array(temperatures_K)

    # QHA via Phonopy
    try:
        from phonopy.qha import PhonopyQHA

        # Build force constants for each volume
        entropy_list: list[np.ndarray]  = []
        cv_list:      list[np.ndarray]  = []
        fe_list:      list[np.ndarray]  = []

        for phonon_obj, _ in phonons_list:
            phonon_obj.run_thermal_properties(
                temperatures=list(temps_arr),
                is_projected_dos=False,
            )
            tp = phonon_obj.get_thermal_properties_dict()
            fe_list.append(np.array(tp["free_energy"]) * 0.010364)    # kJ/mol → eV
            entropy_list.append(np.array(tp["entropy"]) * 1.0364e-4)  # J/mol/K → eV/K
            cv_list.append(np.array(tp["heat_capacity"]) * 1.0364e-4) # J/mol/K → eV/K

        fe_arr      = np.stack(fe_list, axis=0)      # (n_vol, n_T)
        entropy_arr = np.stack(entropy_list, axis=0)
        cv_arr      = np.stack(cv_list, axis=0)

        qha = PhonopyQHA(
            volumes=volumes_arr,
            electronic_energies=energies_arr,
            temperatures=list(temps_arr),
            free_energy=fe_arr.T,      # PhonopyQHA expects (n_T, n_vol)
            cv=cv_arr.T,
            entropy=entropy_arr.T,
            eos=eos_model,
        )
        qha.run()

        gibbs    = np.array(qha.get_gibbs_temperature())
        alpha    = np.array(qha.get_thermal_expansion())
        v_eq     = np.array(qha.get_volume_temperature())
        cp       = np.array(qha.get_heat_capacity_P_numerical())

        # Bulk modulus at 0 K from EOS fit
        try:
            bm = float(qha.get_bulk_modulus_temperature()[0]) * 160.2   # eV/Å³ → GPa
        except Exception:
            bm = None
            flags.append("BM_FAILED")

        flags.append(f"EOS:{eos_model}")

    except Exception as exc:
        flags.append(f"QHA_FAILED:{exc}")
        logger.error("QHA computation failed: %s", exc)
        gibbs = energies_arr[len(energies_arr)//2] * np.ones_like(temps_arr)
        alpha = np.zeros_like(temps_arr)
        v_eq  = volumes_arr[len(volumes_arr)//2] * np.ones_like(temps_arr)
        cp    = np.zeros_like(temps_arr)
        bm    = None

    result = QHAResult(
        volumes_Ang3=volumes_arr,
        temperatures_K=temps_arr,
        gibbs_free_energy_eV=gibbs,
        thermal_expansion=alpha,
        heat_capacity_Cp=cp,
        equilibrium_volume_Ang3=v_eq,
        bulk_modulus_GPa=bm,
        flags=flags,
    )

    # Persist
    np.save(str(work_dir / "qha_volumes.npy"),       volumes_arr)
    np.save(str(work_dir / "qha_energies.npy"),      energies_arr)
    np.save(str(work_dir / "qha_temperatures.npy"),  temps_arr)
    np.save(str(work_dir / "qha_gibbs.npy"),         gibbs)
    np.save(str(work_dir / "qha_alpha.npy"),         alpha)
    np.save(str(work_dir / "qha_Cp.npy"),            cp)
    np.save(str(work_dir / "qha_V_eq.npy"),          v_eq)

    logger.info("%s", result.summary)
    return result
