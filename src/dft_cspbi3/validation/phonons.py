"""Phonon cálculo usa finite-displacement supercell método."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
from ase import Atoms

logger = logging.getLogger(__name__)

# Frequency umbral bajo which mode considered imaginary (numerical noise)
_IMAGINARY_THRESHOLD_CM1 = 10.0   # cm⁻¹ - modes within ±10 cm⁻¹ 0 ignored
_METASTABLE_THRESHOLD_CM1 = 100.0 # cm⁻¹ - modes bajo this "small" imaginary

# Conversion factor
# ħ·c en eV·cm
_THZ_TO_CM1 = 33.3564   # 1 THz = 33.356 cm⁻¹


# Data class


@dataclass
class PhononResult:
    """Resultados fonón cálculo via supercell finite-displacement método."""

    frequencies_cm1: np.ndarray
    n_imaginary: int                   # branches con freq < -_IMAGINARY_THRESHOLD_CM1
    max_imaginary_cm1: float           # most negative imaginary frequency (0 si none)
    n_atoms_unit_cell: int
    supercell: tuple[int, int, int]
    delta_Ang: float
    band_structure: Optional[object]
    dos_frequencies_cm1: Optional[np.ndarray]
    dos_weights: Optional[np.ndarray]
    flags: list[str] = field(default_factory=list)

    @property
    def stable(self) -> bool:
        return self.n_imaginary == 0

    @property
    def summary(self) -> str:
        if self.stable:
            return f"STABLE — no imaginary frequencies (min = {self.frequencies_cm1.min():.1f} cm⁻¹)"
        return (
            f"UNSTABLE — {self.n_imaginary} imaginary modes "
            f"(worst: {self.max_imaginary_cm1:.1f} cm⁻¹)"
        )


# Main computation


def compute_phonons(
    atoms: Atoms,
    calc,
    supercell: tuple[int, int, int] = (2, 2, 2),
    delta: float = 0.05,
    work_dir: Path = Path("./phonons"),
    kpath_npoints: int = 60,
    acoustic_sum_rule: bool = True,
) -> PhononResult:
    """Calcula fonón frequencies along high-symmetry ruta usa ASE Phonons."""
    from ase.phonons import Phonons

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    flags: list[str] = []

    name = str(work_dir / "phonon")
    logger.info(
        "Computing phonons: supercell %s, delta=%.3f Å, %d k-path points",
        supercell, delta, kpath_npoints,
    )

    # Attach fresh calculator (ASE Phonons needs it directly)
    atoms_copy = atoms.copy()
    atoms_copy.calc = calc

    ph = Phonons(atoms_copy, calc, supercell=supercell, delta=delta, name=name)

    # Ejecuta displacements (skips already-computed ones thanks pickle cache)
    ph.run()

    # Read y process fuerza constants
    ph.read(acoustic=acoustic_sum_rule)

    # Aplica LO-TO Gonze-Lee correction si Born charges disponible
    born_path = work_dir / "born_charges.npy"
    eps_path = work_dir / "dielectric_tensor.npy"
    loto_applied = False
    if born_path.exists() and eps_path.exists():
        try:
            Z_born = np.load(str(born_path))   # shape (N, 3, 3)
            eps_inf = np.load(str(eps_path))    # shape (3, 3)
            ph.set_born_charges(Z_born, eps_inf)
            loto_applied = True
            logger.info("LO-TO Gonze-Lee correction applied from %s", born_path)
        except Exception as exc:
            flags.append(f"LOTO_CORRECTION_FAILED:{exc}")
            logger.warning("LO-TO correction failed: %s", exc)

    # Banda estructura along high-symmetry ruta
    bs = None
    try:
        path = atoms.cell.bandpath(npoints=kpath_npoints)
        bs = ph.get_band_structure(path)
        # energies en eV, convert cm⁻¹
        # ASE PhononBandStructure stores energies en eV (meV?)
        # sign convention
        raw_eV = bs.energies   # shape (nspins_unused=1, nkpts, nbranch) typically
        if raw_eV.ndim == 3:
            raw_eV = raw_eV[0]
        freqs_cm1 = _eV_to_cm1_signed(raw_eV)
        if loto_applied:
            flags.append("LOTO_CORRECTION_APPLIED")
    except Exception as exc:
        flags.append(f"BAND_STRUCTURE_FAILED:{exc}")
        logger.warning("Band structure computation failed: %s", exc)
        freqs_cm1 = np.array([[0.0]])

    # DOS
    dos_freqs = None
    dos_weights = None
    try:
        # ASE >= 3.22 usa 'delta' en eV
        # 5 cm⁻¹ broadening ≈ 0.00062 eV
        try:
            dos_energies, dos_w = ph.dos(kpts=(20, 20, 20), npts=1000, delta=5e-4)
        except TypeError:
            dos_energies, dos_w = ph.dos(kpts=(20, 20, 20), npts=1000)
        dos_freqs = _eV_to_cm1_signed(dos_energies)
        dos_weights = dos_w
    except Exception as exc:
        flags.append(f"DOS_FAILED:{exc}")
        logger.warning("Phonon DOS computation failed: %s", exc)

    # Clasifica imaginary modes
    n_imaginary = int(np.sum(freqs_cm1 < -_IMAGINARY_THRESHOLD_CM1))
    if n_imaginary > 0:
        max_imag = float(freqs_cm1[freqs_cm1 < -_IMAGINARY_THRESHOLD_CM1].min())
        flags.append(f"IMAGINARY_PHONONS:{n_imaginary} (worst:{max_imag:.1f}cm⁻¹)")
    else:
        max_imag = 0.0

    return PhononResult(
        frequencies_cm1=freqs_cm1,
        n_imaginary=n_imaginary,
        max_imaginary_cm1=max_imag,
        n_atoms_unit_cell=len(atoms),
        supercell=supercell,
        delta_Ang=delta,
        band_structure=bs,
        dos_frequencies_cm1=dos_freqs,
        dos_weights=dos_weights,
        flags=flags,
    )


# Frequency conversion helpers


def _eV_to_cm1_signed(energies_eV: np.ndarray) -> np.ndarray:
    """Convert fonón energies desde eV cm⁻¹, preserving sign para imaginary modes."""
    EV_TO_CM1 = 8065.544   # 1 eV = 8065.544 cm⁻¹
    return energies_eV * EV_TO_CM1


def compute_born_charges(
    scf_gpw: str | Path,
    work_dir: Path = Path("./loto"),
    delta: float = 0.01,
) -> tuple[np.ndarray, np.ndarray]:
    """Calcula Born effective charges Z* y dielectric tensor ε_∞."""
    from gpaw import GPAW
    from gpaw.borncharges import displace_atom
    from gpaw.borncharges import born_charges as _gpaw_born_charges
    try:
        from gpaw.borncharges import _all_disp
    except ImportError:
        def _all_disp(atoms, delta):
            """Inlined from gpaw 25.7.0 (removed in master)."""
            def _all_avs(atoms):
                for ia in range(len(atoms)):
                    for iv in range(3):
                        for sign in [-1, 1]:
                            yield (ia, iv, sign)
            result = {}
            for dd, (ia, iv, sign) in enumerate(_all_avs(atoms)):
                sym_v = 'xyz'[iv]
                sym_s = ' +-'[sign]
                label = f'disp_{dd:03d}_{ia}{sym_v}{sym_s}'
                result[label] = (ia, iv, sign, delta)
            return result
    from gpaw.berryphase import polarization_phase
    from gpaw.external import static_polarizability
    from gpaw.mpi import world
    from ase.io.jsonio import write_json, read_json
    from ase.units import Bohr, Ha

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    ref_calc = GPAW(str(scf_gpw), txt=None)
    atoms = ref_calc.get_atoms()
    vol = atoms.get_volume()

    # Calculator para displacements - symmetry debe be off para Berry fase
    calc_disp = GPAW(
        str(scf_gpw),
        symmetry="off",
        txt=str(work_dir / "born_disp.txt"),
    )

    # ── Z*
    disps_av = _all_disp(atoms, delta)
    phases_c: dict[str, np.ndarray] = {}

    for dlabel, (ia, iv, sign, disp_delta) in disps_av.items():
        berry_path = work_dir / f"{dlabel}_berry.json"
        gpw_path = work_dir / f"{dlabel}.gpw"

        if berry_path.exists():
            with open(str(berry_path)) as f:
                phases_c[dlabel] = read_json(f)["phase_c"]
            continue

        atoms_d = displace_atom(atoms, ia, iv, sign, disp_delta)
        atoms_d.calc = calc_disp
        atoms_d.get_potential_energy()
        atoms_d.calc.write(str(gpw_path), mode="all")
        world.barrier()

        berry_result = polarization_phase(gpw_path, comm=world)
        phases_c[dlabel] = berry_result["phase_c"]

        if world.rank == 0:
            with open(str(berry_path), "w") as f:
                write_json(f, berry_result)
            gpw_path.unlink(missing_ok=True)
        world.barrier()

    Z_born_results = _gpaw_born_charges(atoms, disps_av, phases_c, check=True)
    Z_born = Z_born_results["Z_avv"]   # (N_atoms, 3, 3)

    # ── ε_∞
    ref_calc2 = GPAW(str(scf_gpw), txt=None)
    atoms2 = ref_calc2.get_atoms()
    atoms2.calc = ref_calc2
    atoms2.get_potential_energy()

    # alpha en e²·Å²/eV
    alpha_gpaw = static_polarizability(atoms2, strength=0.01)
    alpha_ang3 = alpha_gpaw * Bohr * Ha
    eps_inf = np.eye(3) + 4 * np.pi * alpha_ang3 / vol

    np.save(str(work_dir / "born_charges.npy"), Z_born)
    np.save(str(work_dir / "dielectric_tensor.npy"), eps_inf)
    logger.info(
        "Born charges: mean |Z*|=%.3f, ε_∞ diagonal=%s",
        float(np.abs(Z_born).mean()),
        list(np.round(np.diag(eps_inf), 3)),
    )
    return Z_born, eps_inf


def compute_phonons_phonopy(
    atoms: Atoms,
    calc,
    supercell: tuple[int, int, int] = (2, 2, 2),
    delta: float = 0.02,
    work_dir: Path = Path("./phonons"),
    kpath_npoints: int = 60,
    asr: str = "crystal",
    scf_convergence: dict | None = None,
    factory=None,
) -> PhononResult:
    """Calcula fonones usa Phonopy + GPAW (symmetry-reduced displacements)."""
    from ..analysis.phonopy_workflow import (
        generate_phonopy_displacements,
        run_gpaw_forces,
        compute_phonon_dispersion,
    )
    import numpy as np

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    if factory is None:
        raise ValueError(
            "compute_phonons_phonopy() requires factory=GPAWCalculatorFactory "
            "for k-mesh scaling. Pass factory= explicitly."
        )

    supercell_matrix = np.diag(supercell)

    logger.info(
        "Phonopy backend: supercell %s, Δ=%.3f Å, ASR=%s", supercell, delta, asr
    )

    phonon, supercells, n_disp = generate_phonopy_displacements(
        atoms, supercell=supercell, delta=delta, work_dir=work_dir
    )
    logger.info("Running %d GPAW force calculations", n_disp)

    force_sets = run_gpaw_forces(
        phonon,
        supercells,
        factory,
        work_dir=work_dir,
        supercell_matrix=supercell_matrix,
        scf_convergence=scf_convergence,
    )

    return compute_phonon_dispersion(
        phonon,
        force_sets,
        atoms,
        delta=delta,
        supercell=supercell,
        kpath_npoints=kpath_npoints,
        dos_kpts=(20, 20, 20),
        asr=asr,
        work_dir=work_dir,
    )


def frequencies_at_gamma(
    atoms: Atoms,
    calc,
    delta: float = 0.02,
    work_dir: Path = Path("./hessian_vib"),
) -> np.ndarray:
    """Calcula vibrational frequencies en Γ point usa ASE Vibrations."""
    from ase.vibrations import Vibrations

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    atoms_copy = atoms.copy()
    atoms_copy.calc = calc

    name = str(work_dir / "vib")
    vib = Vibrations(atoms_copy, delta=delta, name=name)
    vib.run()

    # get_energies() returns complex array en eV:
    # real modes
    # imaginary modes
    energies_eV = vib.get_energies()

    EV_TO_CM1 = 8065.544
    sign = np.where(np.imag(energies_eV) != 0, -1.0, 1.0)
    freqs_cm1 = sign * np.abs(energies_eV) * EV_TO_CM1

    return freqs_cm1
