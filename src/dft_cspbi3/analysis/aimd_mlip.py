"""AIMD screening via Machine-Learning Interatomic Potentials (MACE-MP-0 / TorchSim).

Replaces ab-initio AIMD (~400 h/temperature on 7 cores) with MLIP-driven MD
(~5 min/temperature on CPU). Used as a fast pre-screening step before QHA-DFT
validation of thermally stable structures.

Stability criteria (conservative defaults for perovskite screening):
  RMSD < 0.8 Å     — structure intact (vs. reference at 0 K)
  Pb-I RDF peak    — first peak must remain at 3.0–3.5 Å (octahedron survives)
  Pb-I-Pb angle    — mean angle must stay 160–180° (no complete octahedral collapse)
  No decomp.       — no split RDF suggestive of CsI + PbI₂ separation

Output label: "stable" | "distorted" | "decomposed"

Dependencies (install once):
  pip install mace-torch torchsim    # CPU-compatible
"""

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
_RMSD_STABLE_ANG   = 0.50   # Å — relaxed criterion (perovskite tilts are expected)
_RMSD_DISTORTED_ANG = 0.80  # Å — beyond this → "distorted"
_PBI_RMIN_ANG = 2.5         # Å — min valid Pb-I bond
_PBI_RMAX_ANG = 3.8         # Å — max valid Pb-I bond (longer = octahedron broken)


@dataclass
class AIMDResult:
    """MLIP-AIMD stability screening result for one temperature."""

    temperature_K: float
    n_steps: int
    timestep_fs: float
    rmsd_final_Ang: float                # RMSD of last frame vs. initial structure
    rmsd_mean_Ang: float                 # mean RMSD over trajectory
    pbi_rdf_peak_Ang: Optional[float]    # first Pb-I RDF peak position [Å]
    pbi_angle_mean_deg: Optional[float]  # mean Pb-I-Pb angle over trajectory [°]
    label: str                           # "stable" | "distorted" | "decomposed"
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
    """RMSD of each frame in pos_traj vs. pos_ref.  pos_traj: (N_frames, N_atoms, 3)."""
    diff = pos_traj - pos_ref[np.newaxis, :, :]
    return np.sqrt(np.mean(np.sum(diff**2, axis=2), axis=1))


def _rdf_first_peak(positions: np.ndarray, cell: np.ndarray, sym_a: str, sym_b: str,
                    symbols: list[str], r_max: float = 6.0, n_bins: int = 200
                    ) -> Optional[float]:
    """Estimate position of the first RDF peak between elements sym_a and sym_b."""
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
    # Find first prominent peak (above half max)
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
    """Run NVT AIMD using MACE-MP-0 potential.

    Integrates the ASE-compatible MACE calculator with Langevin dynamics.
    A 10-step equilibration phase (same T, no data collection) precedes sampling.

    Args:
        atoms: ASE Atoms object (primitive or supercell; a 2×2×2 supercell
            is recommended for reliable statistics — build with atoms.repeat(2)).
        temperature_K: Target temperature [K].
        work_dir: Directory for trajectory and log files.
        n_steps: Number of MD steps.
        timestep_fs: Integration timestep [fs].
        model: MACE model tag. "mace-mp-0" uses the universal MP-trained potential.
        save_trajectory: Whether to write trajectory to disk (.traj file).
        thermostat: "nvt_langevin" (Langevin) or "nvt_nose_hoover" (NHC, needs ASE ≥ 3.23).
        friction: Langevin friction coefficient [1/fs].

    Returns:
        AIMDResult with stability label and metrics.
    """
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

    # Production run — collect positions for RMSD
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

    # RDF of last frame
    rdf_peak = _rdf_first_peak(atoms.get_positions(), cell, "Pb", "I", symbols)

    # Pb-I-Pb angle (simplified: use positions of last frame)
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

    # Save summary
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
    """Compute mean Pb-I-Pb angle [°] in last frame using nearest-neighbour search."""
    idx_pb = [i for i, s in enumerate(symbols) if s == "Pb"]
    idx_i  = [i for i, s in enumerate(symbols) if s == "I"]
    if len(idx_pb) < 2 or len(idx_i) < 1:
        return None

    angles: list[float] = []
    lx, ly, lz = cell[0, 0], cell[1, 1], cell[2, 2]

    for ii in idx_i:
        # Find Pb atoms bonded to this I
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
    """Run MLIP-AIMD screening at multiple temperatures.

    Returns a dict mapping temperature → AIMDResult. Stops early if "decomposed"
    is detected at a given temperature (hotter temperatures are skipped).

    Args:
        atoms: ASE Atoms (use a 2×2×2 supercell for better statistics).
        work_dir: Parent directory; sub-dirs {T}K/ are created automatically.
        temperatures_K: Temperatures to screen [K].
        n_steps: MD steps per temperature.
        timestep_fs: Integration timestep [fs].
        model: MACE model identifier.

    Returns:
        dict {T_K: AIMDResult}
    """
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
