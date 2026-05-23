"""Point-defect formation energies para CsPbI₃ usa DFT supercell método."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# Madelung constant para simple cubic lattice (usado as approximation para
# cubic 2×2×2 supercell
_MADELUNG_SC = 2.8373

# Default ε∞ desde computed LO-TO resultado
_EPS_INF_DEFAULT = 3.647

# eV/Å (Hartree/Bohr conversion factors absorbed into formula)
_EV_A_TO_SI = 1.0   # energies already en eV, lengths en Å

# Elemental reference energies [eV/atom] - DFT-PBE estándar state
# These debe be replaced con valores computed en mismo level theory
# (mismo GPAW settings, mismo PAW datasets) para quantitative resultados
_ELEMENTAL_REFS_EV: dict[str, float] = {
    "Cs":  -0.85,
    "Pb":  -3.70,
    "I":   -1.49,   # I₂ molecule per I atom (½ × E(I₂))
}

# Chemical potential limits para CsPbI₃ (Cs-rich / I-rich extremes)
# μ_α = μ_α^elemental + Δμ_α, Δμ_α bounded by estabilidad constraints
# Full convex-hull analysis needed para precise limits
_DELTA_MU_RANGES: dict[str, tuple[float, float]] = {
    "Cs": (-2.0, 0.0),
    "Pb": (-2.5, 0.0),
    "I":  (-1.5, 0.0),
}

# Defect configurations
_DEFECT_CONFIGS: list[tuple[str, dict, dict, tuple]] = [
    ("V_I",   {"I": 1},  {},       (0, +1)),
    ("I_i",   {},        {"I": 1}, (0, -1)),
    ("V_Pb",  {"Pb": 1}, {},       (0, -1, -2)),
    ("V_Cs",  {"Cs": 1}, {},       (0, -1)),
    ("Pb_I",  {"I": 1},  {"Pb": 1}, (0, +1, +2)),
    ("I_Pb",  {"Pb": 1}, {"I": 1}, (0, -1, -2)),
]


@dataclass
class DefectResult:
    """Formation energía y electronic level para one (defect, charge) pair."""

    defect_name: str
    charge: int
    E_formation_eV: float
    E_formation_midgap_eV: float         # en E_F = E_gap / 2
    transition_level_eV: Optional[float]
    E_dft_defect_eV: float               # raw DFT total energía
    E_corr_eV: float
    mace_relaxed: bool
    flags: list[str] = field(default_factory=list)

    @property
    def deep_trap(self) -> bool:
        """True si transition level more than 0.2 eV desde banda edges."""
        if self.transition_level_eV is None:
            return False
        return 0.2 < self.transition_level_eV

    @property
    def summary(self) -> str:
        return (
            f"{self.defect_name}^{self.charge:+d}: "
            f"E_f={self.E_formation_eV:.3f} eV, "
            f"E_f(midgap)={self.E_formation_midgap_eV:.3f} eV"
            + (f", CTL={self.transition_level_eV:.3f} eV" if self.transition_level_eV else "")
        )


def build_defect_supercell(
    atoms,
    defect_name: str,
    supercell_matrix: tuple[int, int, int] = (2, 2, 2),
    interstitial_site: Optional[np.ndarray] = None,
) -> tuple:
    """Crea supercell con one point defect."""
    from ase import Atoms as _Atoms

    # Construye supercell
    sc = atoms.repeat(supercell_matrix)
    n, m, l_ = supercell_matrix

    # Find defect config
    cfg = {name: (rm, add) for name, rm, add, _ in _DEFECT_CONFIGS}
    if defect_name not in cfg:
        raise ValueError(f"Unknown defect '{defect_name}'. Choose from {list(cfg)}")

    removed_atoms, added_atoms = cfg[defect_name]
    removed_idx = -1

    syms = sc.get_chemical_symbols()

    # Remove atoms
    for elem, count in removed_atoms.items():
        indices = [i for i, s in enumerate(syms) if s == elem]
        if len(indices) < count:
            raise RuntimeError(f"Not enough {elem} atoms in supercell to remove {count}")
        to_remove = indices[:count]
        # Remove en reverse orden keep indices valid
        for idx in sorted(to_remove, reverse=True):
            del sc[idx]
            removed_idx = idx

    # Add atoms
    for elem, count in added_atoms.items():
        for _ in range(count):
            if interstitial_site is not None:
                frac = np.array(interstitial_site)
            else:
                frac = np.array([0.5, 0.5, 0.5])
            pos = sc.cell.cartesian_positions(frac.reshape(1, 3))[0]
            new_atom = _Atoms(elem, positions=[pos], cell=sc.cell, pbc=True)
            sc += new_atom

    logger.info(
        "Built %s supercell: %d atoms (host: %d)",
        defect_name, len(sc), len(atoms) * n * m * l_,
    )
    return sc, removed_idx


def mace_relax_defect(
    defect_sc,
    work_dir: Path,
    model: str = "mace-mp-0",
    fmax: float = 0.05,
    max_steps: int = 300,
):
    """Relax defect geometry usa MACE-MP-0 (fast pre-relaxation)."""
    try:
        from mace.calculators import mace_mp
        from ase.optimize import BFGS
    except ImportError as exc:
        raise ImportError("pip install mace-torch to use MACE geometry relaxation") from exc

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    sc = defect_sc.copy()
    calc = mace_mp(model=model, dispersion=False, default_dtype="float32", device="cpu")
    sc.calc = calc

    opt = BFGS(sc, trajectory=str(work_dir / "mace_relax.traj"), logfile=str(work_dir / "mace_relax.log"))
    opt.run(fmax=fmax, steps=max_steps)
    logger.info("MACE relaxation converged: fmax=%.4f eV/Å", opt.get_residual())
    return sc


def compute_formation_energy(
    E_defect_eV: float,
    E_host_eV: float,
    charge: int,
    removed_atoms: dict[str, int],
    added_atoms: dict[str, int],
    fermi_level_eV: float = 0.0,
    delta_mu: Optional[dict[str, float]] = None,
    eps_inf: float = _EPS_INF_DEFAULT,
    supercell_length_Ang: float = 12.36,
) -> tuple[float, float]:
    """Calcula defect formation energía."""
    if delta_mu is None:
        delta_mu = {}

    # Chemical potential terms
    mu_correction = 0.0
    for elem, count in removed_atoms.items():
        mu = _ELEMENTAL_REFS_EV.get(elem, 0.0) + delta_mu.get(elem, 0.0)
        mu_correction -= count * mu
    for elem, count in added_atoms.items():
        mu = _ELEMENTAL_REFS_EV.get(elem, 0.0) + delta_mu.get(elem, 0.0)
        mu_correction += count * mu

    # Makov-Payne monopole correction (eV)
    if charge != 0:
        # E_MP = q² × α_M / (2 ε ε₀ L) en SI
        # E_MP [eV] = q² × 14.4 eV·Å × α_M / (2 ε L)
        E_corr = (charge ** 2) * 14.4 * _MADELUNG_SC / (2 * eps_inf * supercell_length_Ang)
    else:
        E_corr = 0.0

    E_f = (E_defect_eV - E_host_eV) + mu_correction + charge * fermi_level_eV + E_corr
    return E_f, E_corr


def gpaw_single_point(
    atoms,
    factory,
    work_dir: Path,
    label: str = "defect",
) -> float:
    """Ejecuta GPAW único-point SCF en dado geometry."""
    from gpaw import GPAW
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    calc = factory.create(
        "scf",
        params_override={"symmetry": "off", "convergence": {"energy": 1e-6}},
        txt=str(work_dir / f"{label}_scf.txt"),
    )
    sc = atoms.copy()
    sc.calc = calc
    energy = sc.get_potential_energy()
    calc.write(str(work_dir / f"{label}_scf.gpw"))
    logger.info("DFT single-point %s: E = %.6f eV", label, energy)
    return float(energy)


def compute_all_defects(
    atoms,
    factory,
    work_dir: Path,
    E_host_eV: Optional[float] = None,
    host_gpw: Optional[Path] = None,
    bandgap_eV: float = 1.089,
    eps_inf: float = _EPS_INF_DEFAULT,
    supercell_matrix: tuple[int, int, int] = (2, 2, 2),
    use_mace_geometry: bool = True,
    delta_mu: Optional[dict[str, float]] = None,
    defect_names: Optional[list[str]] = None,
) -> list[DefectResult]:
    """Calcula formation energies para all intrinsic defects."""
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    if defect_names is None:
        defect_names = [name for name, _, _, _ in _DEFECT_CONFIGS]

    # Host supercell energía
    if E_host_eV is None:
        if host_gpw is not None and Path(host_gpw).exists():
            from gpaw import GPAW as _GPAW
            calc = _GPAW(str(host_gpw))
            E_host_eV = float(calc.get_potential_energy())
            logger.info("Loaded host energy from %s: %.6f eV", host_gpw, E_host_eV)
        else:
            host_sc = atoms.repeat(supercell_matrix)
            host_dir = work_dir / "host"
            E_host_eV = gpaw_single_point(host_sc, factory, host_dir, "host")

    n, m, l_ = supercell_matrix
    L_Ang = float(np.linalg.det(atoms.cell.array) ** (1.0/3.0)) * (n * m * l_) ** (1.0/3.0)

    results: list[DefectResult] = []

    for def_name, removed, added, charges in _DEFECT_CONFIGS:
        if def_name not in defect_names:
            continue
        for charge in charges:
            label = f"{def_name}_q{charge:+d}"
            sub_dir = work_dir / label
            sub_dir.mkdir(parents=True, exist_ok=True)
            flags: list[str] = []

            logger.info("Processing defect: %s charge=%+d", def_name, charge)
            try:
                defect_sc, _ = build_defect_supercell(atoms, def_name, supercell_matrix)

                mace_relaxed = False
                if use_mace_geometry:
                    try:
                        defect_sc = mace_relax_defect(defect_sc, sub_dir / "mace")
                        mace_relaxed = True
                        flags.append("MACE_GEOM")
                    except ImportError:
                        flags.append("MACE_SKIPPED:not_installed")

                E_def = gpaw_single_point(defect_sc, factory, sub_dir, label)

                E_f_vbm, E_corr = compute_formation_energy(
                    E_def, E_host_eV, charge, removed, added,
                    fermi_level_eV=0.0,
                    delta_mu=delta_mu,
                    eps_inf=eps_inf,
                    supercell_length_Ang=L_Ang,
                )
                E_f_mid, _ = compute_formation_energy(
                    E_def, E_host_eV, charge, removed, added,
                    fermi_level_eV=bandgap_eV / 2.0,
                    delta_mu=delta_mu,
                    eps_inf=eps_inf,
                    supercell_length_Ang=L_Ang,
                )

                # Charge transition level
                # Simplified
                ctl = None
                if charge != 0:
                    E_f_neutral, _ = compute_formation_energy(
                        E_def, E_host_eV, 0, removed, added,
                        fermi_level_eV=0.0, delta_mu=delta_mu,
                        eps_inf=eps_inf, supercell_length_Ang=L_Ang,
                    )
                    ctl = E_f_neutral - E_f_vbm

                res = DefectResult(
                    defect_name=def_name,
                    charge=charge,
                    E_formation_eV=E_f_vbm,
                    E_formation_midgap_eV=E_f_mid,
                    transition_level_eV=ctl,
                    E_dft_defect_eV=E_def,
                    E_corr_eV=E_corr,
                    mace_relaxed=mace_relaxed,
                    flags=flags,
                )
                logger.info("%s", res.summary)
                results.append(res)

            except Exception as exc:
                flags.append(f"ERROR:{exc}")
                logger.error("Defect %s q=%+d failed: %s", def_name, charge, exc)
                results.append(DefectResult(
                    defect_name=def_name, charge=charge,
                    E_formation_eV=float("nan"), E_formation_midgap_eV=float("nan"),
                    transition_level_eV=None, E_dft_defect_eV=float("nan"),
                    E_corr_eV=0.0, mace_relaxed=False, flags=flags,
                ))

    return results


def save_defect_results(results: list[DefectResult], work_dir: Path) -> None:
    """Guarda defect resultados text tabla."""
    work_dir = Path(work_dir)
    lines = [
        "defect | charge | E_f(VBM) eV | E_f(midgap) eV | CTL eV | MACE | flags",
        "-------|--------|-------------|----------------|--------|------|------",
    ]
    for r in results:
        ctl_str = f"{r.transition_level_eV:.3f}" if r.transition_level_eV is not None else "N/A"
        lines.append(
            f"{r.defect_name} | {r.charge:+d} | {r.E_formation_eV:.3f} | "
            f"{r.E_formation_midgap_eV:.3f} | {ctl_str} | "
            f"{'✓' if r.mace_relaxed else '✗'} | {','.join(r.flags)}"
        )
    (work_dir / "defect_formation_energies.txt").write_text("\n".join(lines))
    logger.info("Defect results saved to %s/defect_formation_energies.txt", work_dir)
