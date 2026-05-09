"""AIMD screening via Machine-Learning Interatomic Potentials (MACE-MP-0 / TorchSim)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# Default MACE-MP-0 model tag (universal potential, ~50-100 meV/atom MAE)
_DEFAULT_MODEL = "mace-mp-0"

# Stability thresholds
_RMSD_STABLE_ANG   = 0.50   # Å - relaxed criterion (perovskita tilts esperado)
_RMSD_DISTORTED_ANG = 0.80  # Å - beyond this → "distorted"
_PBI_RMIN_ANG = 2.5         # Å - min valid Pb-I bond
_PBI_RMAX_ANG = 3.8         # Å - max valid Pb-I bond (longer = octahedron broken)


@dataclass
class AIMDResult:
    """MLIP-AIMD estabilidad screening resultado para one temperature."""

    temperature_K: float
    n_steps: int
    timestep_fs: float
    rmsd_final_Ang: float
    rmsd_mean_Ang: float
    pbi_rdf_peak_Ang: Optional[float]    # first Pb-I RDF peak position [Å]
    pbi_angle_mean_deg: Optional[float]
    label: str
    flags: list[str] = field(default_factory=list)
    trajectory_path: Optional[str] = None

    @property
    def summary(self) -> str:
        rmsd_str  = f"RMSD={self.rmsd_final_Ang:.3f}Å"
        peak_str  = f"RDF_peak={self.pbi_rdf_peak_Ang:.2f}Å" if self.pbi_rdf_peak_Ang else "RDF=N/A"
        ang_str   = f"∠PbIPb={self.pbi_angle_mean_deg:.1f}°" if self.pbi_angle_mean_deg else ""
        parts = [f"T={self.temperature_K}K", self.label, rmsd_str, peak_str]
        if ang_str:
            parts.append(ang_str)
        return "AIMD-MLIP: " + ", ".join(parts)


def _compute_rmsd(pos_ref: np.ndarray, pos_traj: np.ndarray) -> np.ndarray:
    """RMSD each frame en pos_traj vs."""
    diff = pos_traj - pos_ref[np.newaxis, :, :]
    return np.sqrt(np.mean(np.sum(diff**2, axis=2), axis=1))


def _rdf_first_peak(positions: np.ndarray, cell: np.ndarray, sym_a: str, sym_b: str,
                    symbols: list[str], r_max: float = 6.0, n_bins: int = 200
                    ) -> Optional[float]:
    """Estimate position first RDF peak entre elements sym_a y sym_b."""
    idx_a = [i for i, s in enumerate(symbols) if s == sym_a]
    idx_b = [i for i, s in enumerate(symbols) if s == sym_b]
    if not idx_a or not idx_b:
        return None

    bins = np.linspace(0.0, r_max, n_bins + 1)
    hist = np.zeros(n_bins)

    for i in idx_a:
        for j in idx_b:
            if i == j:
                continue
            dr = positions[j] - positions[i]
            # Minimum image (orthorhombic approx)
            lx, ly, lz = cell[0, 0], cell[1, 1], cell[2, 2]
            dr[0] -= lx * round(dr[0] / lx)
            dr[1] -= ly * round(dr[1] / ly)
            dr[2] -= lz * round(dr[2] / lz)
            r = float(np.linalg.norm(dr))
            if r < r_max:
                bin_idx = int(r / r_max * n_bins)
                hist[min(bin_idx, n_bins - 1)] += 1

    if hist.max() == 0:
        return None
    # Find first prominent peak (sobre half max)
    centers = 0.5 * (bins[:-1] + bins[1:])
    threshold = hist.max() * 0.3
    peaks_r = centers[hist > threshold]
    return float(peaks_r[0]) if len(peaks_r) > 0 else None


def _label_from_metrics(rmsd: float, rdf_peak: Optional[float]) -> str:
    if rmsd > _RMSD_DISTORTED_ANG:
        return "decomposed"
    if rdf_peak is not None and (rdf_peak < _PBI_RMIN_ANG or rdf_peak > _PBI_RMAX_ANG):
        return "decomposed"
    if rmsd > _RMSD_STABLE_ANG:
        return "distorted"
    return "stable"


def run_mace_aimd(
    atoms,
    temperature_K: float,
    work_dir: Path,
    n_steps: int = 5000,
    timestep_fs: float = 2.0,
    model: str = _DEFAULT_MODEL,
    save_trajectory: bool = True,
    thermostat: str = "nvt_langevin",
    friction: float = 0.01,
) -> AIMDResult:
    """Ejecuta NVT AIMD usa MACE-MP-0 potential."""
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    flags: list[str] = []

    try:
        from mace.calculators import mace_mp
    except ImportError:
        flags.append("MACE_NOT_INSTALLED: pip install mace-torch")
        logger.error("mace-torch not installed. Run: pip install mace-torch")
        return AIMDResult(
            temperature_K=temperature_K, n_steps=0, timestep_fs=timestep_fs,
            rmsd_final_Ang=0.0, rmsd_mean_Ang=0.0,
            pbi_rdf_peak_Ang=None, pbi_angle_mean_deg=None,
            label="error", flags=flags,
        )

    try:
        from ase import units
        from ase.md.langevin import Langevin
        from ase.io import Trajectory
    except ImportError as exc:
        flags.append(f"ASE_IMPORT_ERROR:{exc}")
        return AIMDResult(
            temperature_K=temperature_K, n_steps=0, timestep_fs=timestep_fs,
            rmsd_final_Ang=0.0, rmsd_mean_Ang=0.0,
            pbi_rdf_peak_Ang=None, pbi_angle_mean_deg=None,
            label="error", flags=flags,
        )

    atoms = atoms.copy()
    calc = mace_mp(model=model, dispersion=False, default_dtype="float32", device="cpu")
    atoms.calc = calc

    pos_ref = atoms.get_positions().copy()
    symbols = atoms.get_chemical_symbols()
    cell = atoms.get_cell().array.copy()

    dt = timestep_fs * units.fs
    dyn = Langevin(atoms, dt, temperature_K=temperature_K, friction=friction)

    traj_path = str(work_dir / f"aimd_{int(temperature_K)}K.traj")
    traj: Optional[Trajectory] = None
    if save_trajectory:
        traj = Trajectory(traj_path, "w", atoms)
        dyn.attach(traj.write, interval=10)

    # Equilibrate (100 steps, no recording)
    logger.info("MACE AIMD: equilibrating at %d K …", temperature_K)
    dyn.run(100)

    # Produccion: junta posiciones para RMSD.
    positions_history: list[np.ndarray] = []

    def _collect():
        positions_history.append(atoms.get_positions().copy())

    dyn.attach(_collect, interval=10)
    logger.info("MACE AIMD: running %d steps at %d K …", n_steps, temperature_K)
    dyn.run(n_steps)

    if traj is not None:
        traj.close()

    # Metrics
    if positions_history:
        pos_traj = np.stack(positions_history, axis=0)
        rmsd_series = _compute_rmsd(pos_ref, pos_traj)
        rmsd_final = float(rmsd_series[-1])
        rmsd_mean  = float(rmsd_series.mean())
    else:
        rmsd_final = rmsd_mean = 0.0

    # RDF last frame
    rdf_peak = _rdf_first_peak(atoms.get_positions(), cell, "Pb", "I", symbols)

    # Pb-I-Pb angle (simplified
    pbi_angle = _mean_pbi_angle(atoms.get_positions(), symbols, cell)

    label = _label_from_metrics(rmsd_final, rdf_peak)
    flags.append(f"MODEL:{model}")

    result = AIMDResult(
        temperature_K=temperature_K,
        n_steps=n_steps,
        timestep_fs=timestep_fs,
        rmsd_final_Ang=rmsd_final,
        rmsd_mean_Ang=rmsd_mean,
        pbi_rdf_peak_Ang=rdf_peak,
        pbi_angle_mean_deg=pbi_angle,
        label=label,
        flags=flags,
        trajectory_path=traj_path if save_trajectory else None,
    )
    logger.info("%s", result.summary)

    # Guarda resumen
    summary_lines = [
        f"T_K = {temperature_K}",
        f"n_steps = {n_steps}",
        f"timestep_fs = {timestep_fs}",
        f"rmsd_final_Ang = {rmsd_final:.4f}",
        f"rmsd_mean_Ang = {rmsd_mean:.4f}",
        f"pbi_rdf_peak_Ang = {rdf_peak}",
        f"pbi_angle_mean_deg = {pbi_angle}",
        f"label = {label}",
        f"flags = {flags}",
    ]
    (work_dir / f"aimd_{int(temperature_K)}K_summary.txt").write_text("\n".join(summary_lines))

    return result


def _mean_pbi_angle(positions: np.ndarray, symbols: list[str], cell: np.ndarray,
                    r_cut: float = 4.0) -> Optional[float]:
    """Calcula mean Pb-I-Pb angle [°] en last frame usa nearest-neighbour search."""
    idx_pb = [i for i, s in enumerate(symbols) if s == "Pb"]
    idx_i  = [i for i, s in enumerate(symbols) if s == "I"]
    if len(idx_pb) < 2 or len(idx_i) < 1:
        return None

    angles: list[float] = []
    lx, ly, lz = cell[0, 0], cell[1, 1], cell[2, 2]

    for ii in idx_i:
        # Find Pb atoms bonded this I
        bonded_pb = []
        for ip in idx_pb:
            dr = positions[ip] - positions[ii]
            dr[0] -= lx * round(dr[0] / lx)
            dr[1] -= ly * round(dr[1] / ly)
            dr[2] -= lz * round(dr[2] / lz)
            if np.linalg.norm(dr) < r_cut:
                bonded_pb.append(dr)
        if len(bonded_pb) >= 2:
            for a_idx in range(len(bonded_pb)):
                for b_idx in range(a_idx + 1, len(bonded_pb)):
                    va = bonded_pb[a_idx]
                    vb = bonded_pb[b_idx]
                    cos_theta = np.dot(va, vb) / (np.linalg.norm(va) * np.linalg.norm(vb) + 1e-12)
                    angles.append(float(np.degrees(np.arccos(np.clip(cos_theta, -1, 1)))))

    return float(np.mean(angles)) if angles else None


def screen_thermal_stability(
    atoms,
    work_dir: Path,
    temperatures_K: tuple[float, ...] = (300.0, 400.0, 500.0),
    n_steps: int = 5000,
    timestep_fs: float = 2.0,
    model: str = _DEFAULT_MODEL,
) -> dict[float, AIMDResult]:
    """Ejecuta MLIP-AIMD screening en multiple temperatures."""
    results: dict[float, AIMDResult] = {}
    for T in sorted(temperatures_K):
        sub_dir = Path(work_dir) / f"{int(T)}K"
        result = run_mace_aimd(
            atoms, T, sub_dir,
            n_steps=n_steps, timestep_fs=timestep_fs, model=model,
        )
        results[T] = result
        logger.info("T=%d K → %s", T, result.label)
        if result.label == "decomposed":
            logger.warning("Decomposition detected at %d K — skipping higher temperatures", T)
            break

    return results
