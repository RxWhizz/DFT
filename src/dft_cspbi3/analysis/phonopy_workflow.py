"""Fonones con Phonopy + GPAW."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np
from ase import Atoms

logger = logging.getLogger(__name__)

# 1 THz = 33.3564 cm⁻¹
_THZ_TO_CM1 = 33.3564

# imaginary umbral - mismo as en fonones.py
_IMAGINARY_THRESHOLD_CM1 = 10.0


# Estructura conversion helpers

def _ase_to_phonopy(atoms: Atoms):
    """Convert ASE Atoms PhonopyAtoms."""
    from phonopy.structure.atoms import PhonopyAtoms
    return PhonopyAtoms(
        symbols=atoms.get_chemical_symbols(),
        scaled_positions=atoms.get_scaled_positions(),
        cell=atoms.cell.array.copy(),
    )


def _phonopy_to_ase(ph_atoms) -> Atoms:
    """Convert PhonopyAtoms ASE Atoms con PBC."""
    return Atoms(
        symbols=list(ph_atoms.symbols),
        positions=np.array(ph_atoms.positions),   # Cartesian positions en Å
        cell=np.array(ph_atoms.cell),
        pbc=True,
    )


# Step 1

def generate_phonopy_displacements(
    atoms: Atoms,
    supercell: tuple[int, int, int] = (2, 2, 2),
    delta: float = 0.02,
    work_dir: Path = Path("."),
) -> tuple:
    """Genera symmetry-reduced displacements usa Phonopy."""
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


# Step 2

def build_supercell_reference(
    atoms: Atoms,
    factory,
    work_dir: Path,
    supercell_matrix: np.ndarray,
    scf_convergence: Optional[dict] = None,
    kpts_sc: Optional[list] = None,
) -> Path:
    """Ejecuta SCF referencia en supercelda."""
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
    """Ejecuta SCF por desplazamiento."""
    from gpaw import GPAW

    work_dir = Path(work_dir)

    # CRITICAL
    convergence = {"energy": 1e-8}
    if scf_convergence:
        convergence.update(scf_convergence)

    # Scale k-mesh inversely supercell maintain k-point densidad
    base_kpts = factory.config["scf"]["kpts"]   # e.g
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
            # Start desde converged supercell wavefunctions - skips LCAO init
            # y converges en ~8 iterations instead ~50
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
                    "symmetry": "off",
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


# Step 3

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
    """Construye constantes de fuerza + ASR."""
    from dft_cspbi3.validation.phonons import PhononResult

    work_dir = Path(work_dir)
    flags: list[str] = []

    # Assemble fuerza constants
    phonon.forces = [np.array(f) for f in force_sets]
    phonon.produce_force_constants()

    if asr != "none":
        # symmetrize_force_constants(level=1) enforces translational + point-group
        # constraints simultaneously, producing physically correct ASR
        phonon.symmetrize_force_constants(level=1)
        flags.append(f"ASR_{asr.upper()}_APPLIED")
        logger.info("Force constants symmetrised (ASR=%s)", asr)

    # Banda estructura en ASE q-ruta
    freqs_cm1 = np.zeros((kpath_npoints, 3 * len(atoms)))
    try:
        ase_path = atoms.cell.bandpath(npoints=kpath_npoints)
        qpoints = ase_path.kpts   # fractional (nq, 3)
        phonon.run_qpoints(qpoints, with_eigenvectors=False)
        qp_dict = phonon.get_qpoints_dict()
        freqs_thz = qp_dict["frequencies"]
        # Phonopy sign convention
        freqs_cm1 = freqs_thz * _THZ_TO_CM1
        logger.info(
            "Band structure done: min=%.1f cm⁻¹, max=%.1f cm⁻¹",
            freqs_cm1.min(), freqs_cm1.max(),
        )
    except Exception as exc:
        flags.append(f"BAND_STRUCTURE_FAILED:{exc}")
        logger.warning("Phonopy band structure failed: %s", exc)

    # DOS
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

    # Guarda salidas
    np.save(str(work_dir / "phonon_frequencies_phonopy.npy"), freqs_cm1)
    if dos_freqs is not None:
        np.save(
            str(work_dir / "phonon_dos_phonopy.npy"),
            np.column_stack([dos_freqs, dos_weights]),
        )

    # Clasifica imaginary modes
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
        band_structure=None,
        dos_frequencies_cm1=dos_freqs,
        dos_weights=dos_weights,
        flags=flags,
    )


# Step 4 (opcional)

def compare_delta_convergence(
    atoms: Atoms,
    factory,
    work_dir: Path,
    deltas: list[float] = None,
    supercell: tuple[int, int, int] = (2, 2, 2),
    scf_convergence: Optional[dict] = None,
) -> dict:
    """Ejecuta fonón cálculo para multiple Δ valores y compara acoustic branches."""
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

        # Log ramas acusticas en Γ; primer q debe ser Γ.
        acoustic_at_gamma = result.frequencies_cm1[0, :3]
        logger.info(
            "Δ=%.3f Å: acoustic at Γ = [%.2f, %.2f, %.2f] cm⁻¹ (ideal: 0)",
            delta, *acoustic_at_gamma,
        )

    return results


# Quasi-Harmonic Approximation (QHA)

from dataclasses import dataclass as _dc, field as _field


@_dc
class QHAResult:
    """Output Quasi-Harmonic Approximation cálculo."""

    volumes_Ang3: np.ndarray            # volume grid [Å³]
    temperatures_K: np.ndarray
    gibbs_free_energy_eV: np.ndarray    # G(T) en equilibrium V [eV/celda]
    thermal_expansion: np.ndarray       # α(T) = d ln V / dT [1/K]
    heat_capacity_Cp: np.ndarray        # C_p(T) [kB/celda] o [eV/K/celda]
    equilibrium_volume_Ang3: np.ndarray # V_eq(T) [Å³]
    bulk_modulus_GPa: Optional[float]   # B₀ en 0 K desde BM EOS [GPa]
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
    """Calcula quasi-harmonic thermodynamic properties."""
    from phonopy import Phonopy
    from phonopy.structure.atoms import PhonopyAtoms

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    flags: list[str] = []

    V0 = float(atoms.get_volume())
    a0 = float(atoms.cell[0, 0])

    volumes:    list[float] = []
    energies:   list[float] = []
    phonons_list = []

    for strain in volume_strains:
        scale = (1.0 + strain) ** (1.0/3.0)
        vol_dir = work_dir / f"vol_{strain:+.3f}"
        vol_dir.mkdir(parents=True, exist_ok=True)

        # Scaled estructura
        scaled_atoms = atoms.copy()
        scaled_atoms.set_cell(atoms.cell * scale, scale_atoms=True)
        V = float(scaled_atoms.get_volume())

        # DFT total energía (fixed celda SCF)
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

        # Phonon fuerza sets en this volume
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

        # Construye fuerza constants para each volume
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

        fe_arr      = np.stack(fe_list, axis=0)
        entropy_arr = np.stack(entropy_list, axis=0)
        cv_arr      = np.stack(cv_list, axis=0)

        qha = PhonopyQHA(
            volumes=volumes_arr,
            electronic_energies=energies_arr,
            temperatures=list(temps_arr),
            free_energy=fe_arr.T,
            cv=cv_arr.T,
            entropy=entropy_arr.T,
            eos=eos_model,
        )
        qha.run()

        gibbs    = np.array(qha.get_gibbs_temperature())
        alpha    = np.array(qha.get_thermal_expansion())
        v_eq     = np.array(qha.get_volume_temperature())
        cp       = np.array(qha.get_heat_capacity_P_numerical())

        # Bulk modulus en 0 K desde EOS fit
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
