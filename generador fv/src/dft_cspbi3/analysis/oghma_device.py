"""OghmaNano device package generation for the DFT workflow.

OghmaNano is not an ML model. It is a deterministic optoelectronic device
solver, so this module keeps it as an optional DFT/device-analysis step rather
than part of the ML-only AINAGENT scoring path.
"""

from __future__ import annotations

import copy
import json
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np


# Work functions used when patching metal contact shapes (eV, literature)
_METAL_WORK_FUNCTION: dict[str, float] = {"au": 5.1, "ag": 4.7, "al": 4.2}

# ── CsPbI₃ transport parameters (literature, PBE+SOC level) ─────────────────
# Ref: Giorgi & Yamashita, J. Mater. Chem. A 2015; Liu et al. ACS Energy Lett. 2017
_CSPBI3_TRANSPORT = {
    "mue_y":            2e-3,     # electron mobility [m²/Vs]; ~20 cm²/Vs experimental
    "muh_y":            2e-3,     # hole mobility [m²/Vs]
    "Nc":               1e26,     # effective DOS conduction band [m⁻³]
    "Nv":               1e26,     # effective DOS valence band [m⁻³]
    "free_to_free_recombination": 1e-15,
    "srh_tau_n":        1e-7,     # SRH electron lifetime [s]; ~100 ns
    "srh_tau_p":        1e-7,     # SRH hole lifetime [s]
    "ss_srh_enabled":   True,
    "ion_density":      1e22,     # mobile ion density [m⁻³]
    "ion_mobility":     1e-13,
    "epsilonr":         6.2,      # overridden with DFT value at runtime
    "Eg":               1.59,     # overridden with DFT value at runtime
    "Xi":               3.8,      # electron affinity [eV]; CsPbI₃
}

# Optical n/k data source wavelength range used for OghmaNano material file
_NM_MIN = 200.0
_NM_MAX = 1200.0
_PIN_MW_CM2 = 100.0
_A_M2_TO_MA_CM2 = 0.1
_OPTICAL_EG_EV = 1.5858
_OPTICAL_URBACH_ENERGY_MEV = 25.0
_OPTICAL_SMOOTH_WINDOW = 11
_OPTICAL_SMOOTH_POLY = 3
_HC_EV_CM = 1.239841984e-4


@dataclass
class OghmaDeviceResult:
    """Summary of the OghmaNano DFT handoff step."""

    status: str
    method_type: str = "device_physics_drift_diffusion_not_ml"
    pce_pct: Optional[float] = None
    voc_V: Optional[float] = None
    jsc_mA_cm2: Optional[float] = None
    ff: Optional[float] = None
    runner: Optional[str] = None
    manifest_path: Optional[str] = None
    stack_path: Optional[str] = None
    sim_dir: Optional[str] = None
    comparison_report_path: Optional[str] = None
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "method_type": self.method_type,
            "pce_pct": self.pce_pct,
            "voc_V": self.voc_V,
            "jsc_mA_cm2": self.jsc_mA_cm2,
            "ff": self.ff,
            "runner": self.runner,
            "manifest_path": self.manifest_path,
            "stack_path": self.stack_path,
            "sim_dir": self.sim_dir,
            "comparison_report_path": self.comparison_report_path,
            "flags": list(self.flags),
        }


# ── main entry point ──────────────────────────────────────────────────────────

def prepare_oghma_device_step(
    phase_dir: str | Path,
    step_dir: str | Path,
    *,
    phase: str,
    config: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> OghmaDeviceResult:
    """Prepare and optionally run an OghmaNano device simulation.

    1. Build device_stack.json from DFT outputs.
    2. Write a valid OghmaNano sim directory (sim.json + nk material file).
    3. Launch oghma_core if execute=true and a runner is found.
    4. Parse sim_info.dat if it exists.
    """
    phase_dir = Path(phase_dir)
    step_dir = Path(step_dir)
    step_dir.mkdir(parents=True, exist_ok=True)
    cfg = config or {}

    stack = build_device_stack_from_dft(phase_dir, phase=phase, config=cfg)
    stack_path = step_dir / "device_stack.json"
    stack_path.write_text(json.dumps(stack, indent=2), encoding="utf-8")

    runner = resolve_oghma_runner(cfg.get("executable"))
    execute = bool(cfg.get("execute", False)) and not dry_run
    force_execute = bool(cfg.get("force_execute", False))
    sim_dir = step_dir / "sim"

    flags: list[str] = ["OGHMANANO_IS_DEVICE_PHYSICS_NOT_ML"]

    # ── write OghmaNano project ───────────────────────────────────────────────
    try:
        write_oghma_sim_dir(sim_dir, stack, phase_dir, config=cfg)
        flags.append("OGHMA_PROJECT_WRITTEN")
    except Exception as exc:
        flags.append(f"OGHMA_PROJECT_WRITE_FAILED:{exc}")

    if not runner:
        flags.append("OGHMANANO_RUNNER_NOT_FOUND")
    if not execute:
        flags.append("OGHMANANO_EXECUTION_NOT_REQUESTED")

    manifest_path = step_dir / "oghma_manifest.json"
    result_path = step_dir / "oghma_device_result.json"
    sim_info_path = sim_dir / "sim_info.dat"

    manifest = {
        "phase": phase,
        "method_type": "device_physics_drift_diffusion_not_ml",
        "status": "prepared",
        "runner": runner,
        "execute_requested": execute,
        "sim_dir": str(sim_dir),
        "stack_path": str(stack_path),
        "expected_oghma_outputs": ["sim_info.dat", "jv.dat", "out.txt"],
        "flags": flags,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    _write_readme(step_dir, runner=runner)

    # ── parse pre-existing sim_info.dat ──────────────────────────────────────
    parsed = None if (execute and force_execute) else parse_oghma_sim_info(sim_info_path)
    if parsed and not (execute and force_execute):
        _append_oghma_output_flags(step_dir, sim_dir, phase_dir, stack, flags)
        out = OghmaDeviceResult(
            status="parsed_existing_result",
            pce_pct=parsed.get("pce_pct"),
            voc_V=parsed.get("voc_V"),
            jsc_mA_cm2=parsed.get("jsc_mA_cm2"),
            ff=parsed.get("ff"),
            runner=runner,
            manifest_path=str(manifest_path),
            stack_path=str(stack_path),
            sim_dir=str(sim_dir),
            flags=flags,
        )
        out.comparison_report_path = str(write_oghma_method_comparison(step_dir, stack, out))
        plot_oghma_results(step_dir, sim_dir, out)
        result_path.write_text(json.dumps(out.to_dict(), indent=2), encoding="utf-8")
        return out

    # ── run oghma_core ────────────────────────────────────────────────────────
    if execute and runner and "OGHMA_PROJECT_WRITTEN" in flags:
        if force_execute:
            _remove_previous_oghma_outputs(sim_dir)
        on_windows = sys.platform == "win32"
        if on_windows:
            ensure_oghma_local_windows(sim_dir / "materials")
        else:
            ensure_oghma_local_links(materials_overlay=sim_dir / "materials")
            ensure_wine_drive_links(sim_dir)
        wine_env = _wine_env()
        run_cfg = dict(cfg)
        if on_windows:
            sim_dir_abs = str(sim_dir.resolve())
            run_cfg["sim_root_path"] = sim_dir_abs
            run_cfg["lockfile"] = str(sim_dir.resolve() / "lock0.dat")
        worker_cmd = build_oghma_worker_command(runner, run_cfg)
        _remove_stale_lockfile(sim_dir, run_cfg.get("lockfile", r"S:\lock0.dat"))
        try:
            completed = subprocess.run(
                worker_cmd,
                cwd=str(sim_dir),
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=int(cfg.get("timeout_s", 600)),
                env={**os.environ, **wine_env},
            )
            (step_dir / "oghma_stdout.log").write_text(completed.stdout, encoding="utf-8")
            (step_dir / "oghma_stderr.log").write_text(completed.stderr, encoding="utf-8")
            parsed = parse_oghma_sim_info(sim_info_path)
            status = "completed" if completed.returncode == 0 else "failed"
            if completed.returncode != 0:
                flags.append(f"OGHMANANO_RETURN_CODE:{completed.returncode}")
                if error := _extract_oghma_error(completed.stdout + "\n" + completed.stderr):
                    flags.append(f"OGHMANANO_ERROR:{error}")
        except subprocess.TimeoutExpired as exc:
            (step_dir / "oghma_stdout.log").write_text((exc.stdout or "") if isinstance(exc.stdout, str) else "", encoding="utf-8")
            (step_dir / "oghma_stderr.log").write_text((exc.stderr or "") if isinstance(exc.stderr, str) else "", encoding="utf-8")
            parsed = parse_oghma_sim_info(sim_info_path)
            status = "timeout"
            flags.append(f"OGHMANANO_TIMEOUT:{int(cfg.get('timeout_s', 600))}s")
        _append_oghma_output_flags(step_dir, sim_dir, phase_dir, stack, flags)
        flags.append(f"OGHMANANO_WORKER_CMD:{' '.join(worker_cmd)}")
        out = OghmaDeviceResult(
            status=status,
            pce_pct=parsed.get("pce_pct") if parsed else None,
            voc_V=parsed.get("voc_V") if parsed else None,
            jsc_mA_cm2=parsed.get("jsc_mA_cm2") if parsed else None,
            ff=parsed.get("ff") if parsed else None,
            runner=runner,
            manifest_path=str(manifest_path),
            stack_path=str(stack_path),
            sim_dir=str(sim_dir),
            flags=flags,
        )
        out.comparison_report_path = str(write_oghma_method_comparison(step_dir, stack, out))
        if status in ("completed", "timeout") and parsed:
            plot_oghma_results(step_dir, sim_dir, out)
        result_path.write_text(json.dumps(out.to_dict(), indent=2), encoding="utf-8")
        return out

    out = OghmaDeviceResult(
        status="prepared",
        runner=runner,
        manifest_path=str(manifest_path),
        stack_path=str(stack_path),
        sim_dir=str(sim_dir),
        flags=flags,
    )
    out.comparison_report_path = str(write_oghma_method_comparison(step_dir, stack, out))
    result_path.write_text(json.dumps(out.to_dict(), indent=2))
    return out


# ── OghmaNano project writer ──────────────────────────────────────────────────

def write_oghma_sim_dir(
    sim_dir: Path,
    stack: dict[str, Any],
    phase_dir: Path,
    *,
    config: dict[str, Any] | None = None,
) -> None:
    """Write a valid OghmaNano simulation directory from DFT-derived inputs.

    Patches ONLY DFT-derived fields onto the template — structure (contacts,
    mesh, electrical solver, optical model) is left exactly as the template
    provides it to avoid headless validation errors.

    Creates:
      sim_dir/
        sim.json / json.inp
        materials/CsPbI3/{n.csv, alpha.csv, nk.csv, data.json, mat.json}
    """
    sim_dir.mkdir(parents=True, exist_ok=True)
    cfg = config or {}
    dft = stack.get("dft_inputs", {})
    layers = stack.get("layers", [])

    absorber = next((l for l in layers if l.get("role") == "absorber"), {})
    thickness_m = absorber.get("thickness_nm", 500.0) * 1e-9
    bandgap_eV = dft.get("bandgap_eV") or absorber.get("bandgap_eV") or 1.59
    eps_r = dft.get("dielectric_constant") or absorber.get("dielectric_constant") or 6.2
    m_e = (dft.get("effective_masses") or {}).get("m_e_m0") or 0.11
    m_h = (dft.get("effective_masses") or {}).get("m_h_m0") or 0.15
    mue = _mobility_from_mass(m_e)
    muh = _mobility_from_mass(m_h)

    sim_json = _get_perovskite_template()

    # simmode only
    sim_json.setdefault("sim", {})["simmode"] = str(cfg.get("simmode", "segment0@jv"))

    # ── patch absorber segment (only DFT fields) ──────────────────────────────
    epi = sim_json.get("epitaxy", {})
    absorber_seg = _find_absorber_segment(epi)
    if absorber_seg is not None:
        absorber_seg["dy"] = thickness_m
        dos = absorber_seg.setdefault("shape_dos", {})
        dos["Eg"] = float(bandgap_eV)
        dos["epsilonr"] = float(eps_r)
        dos["mue_y"] = mue
        dos["mue_x"] = mue
        dos["mue_z"] = mue
        dos["muh_y"] = muh
        dos["muh_x"] = muh
        dos["muh_z"] = muh
        absorber_seg["optical_material"] = "CsPbI3"

    # ── minimal fast-mode patches (numbers only, no structure) ───────────────
    fast_mode = bool(cfg.get("fast_mode", True))
    if fast_mode:
        _apply_fast_oghma_settings(
            sim_json,
            vstart=float(cfg.get("jv_vstart", cfg.get("fast_vstart", 0.0))),
            vstop=float(cfg.get("jv_vstop", cfg.get("fast_vstop", 1.2))),
            vstep=float(cfg.get("fast_vstep", 0.1)),
            ion_density=float(cfg.get("fast_ion_density", 0.0)),
            generation_model=None,
        )
    _apply_mesh_resolution_settings(
        sim_json,
        electrical_points=cfg.get("electrical_mesh_points"),
        optical_points=cfg.get("optical_mesh_points"),
    )
    _apply_solver_iteration_settings(
        sim_json,
        max_iterations=cfg.get("solver_max_iterations"),
        ramp_iterations=cfg.get("solver_ramp_iterations"),
    )

    # ── write sim.json ────────────────────────────────────────────────────────
    (sim_dir / "sim.json").write_text(json.dumps(sim_json, indent=2), encoding="utf-8")
    (sim_dir / "json.inp").write_text(json.dumps(sim_json, indent=2), encoding="utf-8")

    # ── write DFT nk material ─────────────────────────────────────────────────
    materials_dir = sim_dir / "materials"
    materials_dir.mkdir(parents=True, exist_ok=True)
    _write_materials_index_json(materials_dir / "data.json")

    mat_dir = materials_dir / "CsPbI3"
    mat_dir.mkdir(parents=True, exist_ok=True)
    optical_rows = _load_optical_rows(phase_dir)
    _write_nk_csv(mat_dir / "nk.csv", optical_rows)
    _write_oghma_n_csv(mat_dir / "n.csv", optical_rows)
    _write_oghma_alpha_csv(mat_dir / "alpha.csv", optical_rows)
    _write_mat_json(mat_dir / "data.json", bandgap_eV, eps_r)
    _write_mat_json(mat_dir / "mat.json", bandgap_eV, eps_r)


def _find_absorber_segment(epi: dict[str, Any]) -> dict[str, Any] | None:
    """Return the absorber layer dict from an epitaxy section.

    Identifies the absorber as the thickest 'active' obj_type segment,
    or falls back to any segment whose name contains 'perovskite' or 'mapi'.
    """
    best: dict[str, Any] | None = None
    best_dy = -1.0
    for key, val in epi.items():
        if not (key.startswith("segment") and isinstance(val, dict)):
            continue
        name_lower = val.get("name", "").lower()
        if val.get("obj_type") == "active":
            dy = float(val.get("dy") or 0.0)
            if dy > best_dy:
                best_dy = dy
                best = val
        elif any(kw in name_lower for kw in ("perovskite", "mapi", "cspbi")):
            if best is None:
                best = val
    return best


def _get_perovskite_template() -> dict[str, Any]:
    """Return the OghmaNano perovskite template.

    Search order:
    1. Local OghmaNano installation device_lib (Windows/Linux)
    2. Cached download in temp dir
    3. Fresh download from GitHub
    4. Built-in minimal fallback
    """
    local_candidates = [
        Path(r"C:\Users\LUIS\ogh\sim.json"),
        Path(r"C:\Program Files (x86)\OghmaNano\device_lib\perovskite\perovskite.json"),
        Path(r"C:\Program Files\OghmaNano\device_lib\perovskite\perovskite.json"),
        Path("/usr/share/oghma_data/device_lib/perovskite/perovskite.json"),
    ]
    for candidate in local_candidates:
        if candidate.exists():
            return json.loads(candidate.read_text())

    cache = Path(tempfile.gettempdir()) / "_oghma_perovskite_template.json"
    if cache.exists():
        return json.loads(cache.read_text())
    url = (
        "https://raw.githubusercontent.com/roderickmackenzie/OghmaNano"
        "/master/oghma_data/device_lib/perovskite/perovskite.json"
    )
    try:
        if sys.platform == "win32":
            dl_cmd = ["curl", "-s", "--max-time", "20", "-o", str(cache), url]
        else:
            dl_cmd = ["wget", "-q", "--timeout=20", "-O", str(cache), url]
        subprocess.run(dl_cmd, check=True, capture_output=True)
        return json.loads(cache.read_text())
    except Exception:
        return _minimal_perovskite_template()


def _minimal_perovskite_template() -> dict[str, Any]:
    """Minimal OghmaNano perovskite template for offline use."""
    return {
        "sim": {"simmode": "segment0@jv", "version": "8.0"},
        "sims": {
            "jv": {
                "segments": 1,
                "segment0": {
                    "name": "JV curve",
                    "Vstart": 0.0,
                    "Vstop": 1.4,
                    "Vstep": 0.02,
                    "id": "jv_seg0",
                },
            }
        },
        "math": {"max_newton_iterations": 100, "newton_clever_exit": True},
        "optical": {
            "light": {
                "light_model": "full",
                "sun": "AM1.5G",
                "Dphotoneff": 1.0,
                "NDfilter": 0.0,
            },
        },
        "epitaxy": {
            "segments": 5,
            "segment0": {"name": "FTO",       "obj_type": "contact", "dy": 5e-8,  "shape_dos": {}},
            "segment1": {"name": "TiO2",      "obj_type": "layer",   "dy": 2e-7,  "shape_dos": {"Eg": 3.2, "epsilonr": 9.0}},
            "segment2": {"name": "Perovskite","obj_type": "active",  "dy": 4e-7,  "shape_dos": copy.deepcopy(_CSPBI3_TRANSPORT)},
            "segment3": {"name": "Spiro",     "obj_type": "layer",   "dy": 2e-7,  "shape_dos": {"Eg": 3.0, "epsilonr": 3.0}},
            "segment4": {"name": "Au",        "obj_type": "contact", "dy": 1e-7,  "shape_dos": {}},
            "contacts": {"segments": 2, "segment0": {"position": "top"}, "segment1": {"position": "bottom"}},
        },
        "mesh": {"mesh_y": {"segments": 1, "segment0": {"len": 1e-6, "points": 100, "mul": 1.0}}},
        "server": {"max_gpvdm_instances": 1},
        "dump": {"dump_level": 1},
    }


def _load_optical_rows(phase_dir: Path) -> list[tuple[float, float, float]]:
    """Return optical rows as (wavelength_nm, n, k)."""
    opt_dir = phase_dir / "11_optical"
    freq_path = opt_dir / "optical_frequencies.npy"
    n_path = opt_dir / "n_omega.npy"
    k_path = opt_dir / "k_omega.npy"

    if not (freq_path.exists() and n_path.exists() and k_path.exists()):
        dielectric_path = opt_dir / "dielectric_function.csv"
        if dielectric_path.exists():
            return _load_optical_rows_from_dielectric(dielectric_path)
        return _cauchy_nk_rows()

    freq_eV = np.load(str(freq_path))   # energies in eV (0 to 6 eV, 241 pts)
    n_arr = np.load(str(n_path))
    k_arr = np.load(str(k_path))

    # Convert eV → nm (skip ω=0 to avoid inf)
    mask = freq_eV > 0.1
    wl_nm = 1239.84 / freq_eV[mask]    # E(eV) = hc/λ, hc=1239.84 eV·nm
    n_sel = n_arr[mask]
    k_sel = k_arr[mask]

    # OghmaNano expects ascending wavelength → flip (DFT is ascending E)
    idx = np.argsort(wl_nm)
    wl_nm = wl_nm[idx]
    n_sel = n_sel[idx]
    k_sel = k_sel[idx]

    # Restrict to visible–NIR range useful for PV (200–1200 nm)
    mask2 = (wl_nm >= _NM_MIN) & (wl_nm <= _NM_MAX)
    wl_nm = wl_nm[mask2]
    n_sel = n_sel[mask2]
    k_sel = k_sel[mask2]

    return [(float(wl), float(n), float(k)) for wl, n, k in zip(wl_nm, n_sel, k_sel)]


def _load_optical_rows_from_dielectric(path: Path) -> list[tuple[float, float, float]]:
    """Return (wavelength_nm, n, k) derived from dielectric_function.csv."""
    data = np.loadtxt(path, delimiter=",")
    energy = data[:, 0]
    eps1 = np.nanmean(data[:, [1, 3]], axis=1)
    eps2 = np.nanmean(data[:, [2, 4]], axis=1)
    eps_abs = np.sqrt(eps1**2 + eps2**2)
    n_arr = np.sqrt(np.clip((eps_abs + eps1) / 2.0, 0.0, None))
    k_arr = np.sqrt(np.clip((eps_abs - eps1) / 2.0, 0.0, None))
    n_arr = _smooth_optical_series(n_arr, window=_OPTICAL_SMOOTH_WINDOW, poly=_OPTICAL_SMOOTH_POLY)
    k_arr = _smooth_optical_series(k_arr, window=_OPTICAL_SMOOTH_WINDOW, poly=_OPTICAL_SMOOTH_POLY)
    k_arr = np.clip(k_arr, 0.0, None)
    k_arr = _apply_bandgap_absorption_onset(energy, k_arr, eg_eV=_OPTICAL_EG_EV)
    wl_nm = np.divide(1239.84, energy, out=np.full_like(energy, np.nan), where=energy > 0)
    mask = np.isfinite(wl_nm) & (wl_nm >= _NM_MIN) & (wl_nm <= _NM_MAX)
    wl_nm = wl_nm[mask]
    n_arr = n_arr[mask]
    k_arr = k_arr[mask]
    idx = np.argsort(wl_nm)
    return [
        (float(wl_nm[i]), float(n_arr[i]), float(k_arr[i]))
        for i in idx
    ]


def _apply_bandgap_absorption_onset(
    energy_eV: np.ndarray,
    k_arr: np.ndarray,
    *,
    eg_eV: float,
    urbach_energy_meV: float | None = _OPTICAL_URBACH_ENERGY_MEV,
) -> np.ndarray:
    """Apply a smooth Urbach sub-gap tail before device export."""
    energy = np.asarray(energy_eV, dtype=float)
    k = np.clip(np.asarray(k_arr, dtype=float), 0.0, None)
    below_gap = energy < float(eg_eV)
    eu_eV = 0.0 if urbach_energy_meV is None else float(urbach_energy_meV) * 1e-3
    if eu_eV <= 0.0:
        out = k.copy()
        out[below_gap] = 0.0
        return out

    alpha = _absorption_cm1_from_k(energy, k)
    above_gap = energy >= float(eg_eV)
    if not np.any(above_gap) or np.nanmax(alpha[above_gap]) <= 0.0:
        out = k.copy()
        out[below_gap] = 0.0
        return out

    order = np.argsort(energy[above_gap])
    edge_energy = energy[above_gap][order]
    edge_alpha = alpha[above_gap][order]
    alpha_edge = float(np.interp(float(eg_eV), edge_energy, edge_alpha, left=edge_alpha[0], right=edge_alpha[-1]))
    alpha[below_gap] = alpha_edge * np.exp(np.clip((energy[below_gap] - float(eg_eV)) / eu_eV, -700.0, 0.0))
    return _k_from_absorption_cm1(energy, alpha)


def _absorption_cm1_from_k(energy_eV: np.ndarray, k_arr: np.ndarray) -> np.ndarray:
    wavelength_cm = np.divide(
        _HC_EV_CM,
        energy_eV,
        out=np.full_like(energy_eV, np.inf, dtype=float),
        where=energy_eV > 0,
    )
    return np.divide(
        4.0 * np.pi * np.clip(k_arr, 0.0, None),
        wavelength_cm,
        out=np.zeros_like(k_arr, dtype=float),
        where=np.isfinite(wavelength_cm) & (wavelength_cm > 0),
    )


def _k_from_absorption_cm1(energy_eV: np.ndarray, alpha_cm1: np.ndarray) -> np.ndarray:
    wavelength_cm = np.divide(
        _HC_EV_CM,
        energy_eV,
        out=np.full_like(energy_eV, np.inf, dtype=float),
        where=energy_eV > 0,
    )
    return np.divide(
        np.clip(alpha_cm1, 0.0, None) * wavelength_cm,
        4.0 * np.pi,
        out=np.zeros_like(alpha_cm1, dtype=float),
        where=np.isfinite(wavelength_cm) & (wavelength_cm > 0),
    )


def _smooth_optical_series(values: np.ndarray, *, window: int, poly: int) -> np.ndarray:
    """Savitzky-Golay style smoothing without requiring scipy."""
    values = np.asarray(values, dtype=float)
    if len(values) < 5:
        return values.copy()
    window = min(window, len(values) if len(values) % 2 else len(values) - 1)
    window = max(window, poly + 2 + ((poly + 2) % 2 == 0))
    if window % 2 == 0:
        window -= 1
    half = window // 2
    x_window = np.arange(-half, half + 1, dtype=float)
    out = np.empty_like(values)
    for i in range(len(values)):
        left = max(0, i - half)
        right = min(len(values), i + half + 1)
        y = values[left:right]
        x = np.arange(left - i, right - i, dtype=float)
        degree = min(poly, len(y) - 1)
        coeff = np.polyfit(x_window, y, degree) if len(y) == window else np.polyfit(x, y, degree)
        out[i] = np.polyval(coeff, 0.0)
    return out


def _write_nk_csv(path: Path, rows: list[tuple[float, float, float]]) -> None:
    """Export n(lambda), k(lambda) for human inspection: wavelength_nm, n, k."""
    lines = ["#wavelength_nm n k\n"]
    for wl, n, k in rows:
        lines.append(f"{wl:.4f} {n:.6f} {k:.6f}\n")
    path.write_text("".join(lines), encoding="utf-8")


def _cauchy_nk_rows() -> list[tuple[float, float, float]]:
    """Analytical Cauchy n(lambda) + Urbach k(lambda) for CsPbI3 offline fallback."""
    wl = np.linspace(300, 1000, 200)  # nm
    # Cauchy: n ~= 2.25 + 0.02/lambda^2(um)
    n = 2.25 + 0.02 / (wl * 1e-3) ** 2
    # Bounded fallback only: a pure exponential makes impossible short-wave k.
    E = 1239.84 / wl
    eg = 1.59
    k = np.where(E > eg, 0.02 + 0.80 * (1.0 - np.exp(-(E - eg) / 0.6)), 0.0)
    k = np.clip(k, 0.0, 1.0)
    return [(float(w), float(ni), float(ki)) for w, ni, ki in zip(wl, n, k)]


def _write_oghma_n_csv(path: Path, rows: list[tuple[float, float, float]]) -> None:
    """Write OghmaNano n.csv: wavelength in meters, refractive index."""
    lines = [
        '#oghma_csv {"title":"","type":"xy","y_label":"Wavelength",'
        '"data_label":"Refractive index","y_units":"nm","y_mul":1000000000.0,'
        '"data_units":"au","icon":"mat_file","time ":0.0,"Vexternal":0.0,'
        '"x_len":1,"y_len":%d,"z_len":1,"cols":"yd"}*\n' % len(rows)
    ]
    for wl_nm, n, _k in rows:
        lines.append(f"{wl_nm * 1e-9:.6e}\t{n:.6e}\n")
    path.write_text("".join(lines), encoding="utf-8")


def _write_oghma_alpha_csv(path: Path, rows: list[tuple[float, float, float]]) -> None:
    """Write OghmaNano alpha.csv: wavelength in meters, absorption in m^-1."""
    lines = [
        '#oghma_csv {"title":"","type":"xy","y_label":"Wavelength",'
        '"data_label":"Absorption","y_units":"nm","y_mul":1000000000.0,'
        '"data_units":"m^{-1}","icon":"mat_file","time ":0.0,"Vexternal":0.0,'
        '"x_len":1,"y_len":%d,"z_len":1,"cols":"yd"}*\n' % len(rows)
    ]
    for wl_nm, _n, k in rows:
        wavelength_m = wl_nm * 1e-9
        alpha_m1 = 4.0 * np.pi * max(k, 0.0) / wavelength_m
        lines.append(f"{wavelength_m:.6e}\t{alpha_m1:.6e}\n")
    path.write_text("".join(lines), encoding="utf-8")


def _write_materials_index_json(path: Path) -> None:
    """Write the local material database index that OghmaNano probes first."""
    template = Path("/usr/share/oghma_data/materials/data.json")
    if template.exists():
        path.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
        return
    path.write_text(json.dumps({"item_type": "material_db", "status": "public"}, indent=2), encoding="utf-8")


def _reposition_epitaxy_layers(epi: dict[str, Any]) -> None:
    """Keep layer y origins contiguous after changing thicknesses."""
    layer_keys = sorted(
        (key for key, value in epi.items() if key.startswith("segment") and isinstance(value, dict)),
        key=lambda item: int(item.replace("segment", "")) if item.replace("segment", "").isdigit() else 10**9,
    )
    y0 = 0.0
    for key in layer_keys:
        layer = epi[key]
        if "dy" not in layer:
            continue
        layer["y0"] = y0
        y0 += float(layer.get("dy") or 0.0)


def _normalize_contact_shapes(epi: dict[str, Any]) -> None:
    """Keep Oghma contact helper shapes electrically valid after thickness edits."""
    contacts = epi.get("contacts", {})
    if not isinstance(contacts, dict):
        return
    active_end = 0.0
    total_end = 0.0
    for key, value in epi.items():
        if not (key.startswith("segment") and isinstance(value, dict)):
            continue
        end = float(value.get("y0") or 0.0) + float(value.get("dy") or 0.0)
        total_end = max(total_end, end)
        if value.get("obj_type") == "active":
            active_end = max(active_end, end)
    for key, value in contacts.items():
        if key.startswith("segment") and isinstance(value, dict):
            value.setdefault("obj_type", "other")
            value.setdefault("enabled", "True")
            value.setdefault("shape_electrical", _default_contact_electrical())
            value.setdefault("shape_dos", _default_contact_dos())
            if value.get("name", "").lower() in {"btm", "bottom", "back"} or key == "segment1":
                value["y0"] = 0.0
                value["dy"] = max(float(value.get("dy") or 0.0), active_end or total_end)
            else:
                value["y0"] = 0.0
                value["dy"] = max(float(value.get("dy") or 0.0), 1e-7)


def _patch_electrical_mesh_y(epi: dict[str, Any], data: dict[str, Any]) -> None:
    """Match Oghma's 1D drift-diffusion mesh to the active-layer thickness."""
    active_thickness = 0.0
    for key, value in epi.items():
        if key.startswith("segment") and isinstance(value, dict) and value.get("obj_type") == "active":
            active_thickness += float(value.get("dy") or 0.0)
    if active_thickness <= 0.0:
        return

    mesh_y = (
        data.get("electrical_solver", {})
        .get("mesh", {})
        .get("mesh_y", {})
    )
    if not isinstance(mesh_y, dict):
        return
    mesh_y["auto"] = "False"
    for value in mesh_y.values():
        if isinstance(value, dict) and "len" in value:
            value["len"] = active_thickness
            break

    # Patch the optical mesh to cover the full device stack (active + contacts).
    # The stock template has opt_len = total_device_height and el_len = active_thickness.
    # Using auto=True for the optical mesh lets oghma self-compute it; we supply a
    # hint (total_thickness) so it knows the full extent including the metal contacts.
    total_thickness = 0.0
    for value in epi.values():
        if isinstance(value, dict) and value.get("obj_type") in {"active", "contact", "other"}:
            total_thickness = max(
                total_thickness,
                float(value.get("y0") or 0.0) + float(value.get("dy") or 0.0),
            )
    mesh_y_opt = (
        data.get("optical", {})
        .get("mesh", {})
        .get("mesh_y", {})
    )
    if isinstance(mesh_y_opt, dict):
        mesh_y_opt["auto"] = "True"
        for value in mesh_y_opt.values():
            if isinstance(value, dict) and "len" in value:
                value["len"] = total_thickness if total_thickness > 0 else active_thickness
                break


def _enable_shape_electrical_blocks(data: Any) -> None:
    """Add v8 electrical-enable flags to legacy template shape blocks."""
    if isinstance(data, dict):
        shape_electrical = data.get("shape_electrical")
        if isinstance(shape_electrical, dict):
            shape_electrical.setdefault("enabled", "True")
        shape_dos = data.get("shape_dos")
        if isinstance(shape_dos, dict):
            shape_dos.setdefault("enabled", "True")
        for value in data.values():
            _enable_shape_electrical_blocks(value)
    elif isinstance(data, list):
        for value in data:
            _enable_shape_electrical_blocks(value)


def _strip_enabled_from_metals(epi: dict[str, Any]) -> None:
    """Remove shape_electrical.enabled / shape_dos.enabled injected by
    _enable_shape_electrical_blocks for metal contact layers.

    The optical solver checks this flag to decide whether to map optical
    absorption in a shape onto the electrical mesh.  For metal contacts
    (outside the drift-diffusion mesh) having enabled=True triggers the
    "Au covering electrical mesh with no electrical parameters" error.
    The GUI leaves this key absent for metal layers, which is the safe default.
    """
    for seg_key, seg_val in epi.items():
        if not (seg_key.startswith("segment") and isinstance(seg_val, dict)):
            continue
        if seg_val.get("name", "").lower() in _METAL_WORK_FUNCTION:
            seg_val.get("shape_electrical", {}).pop("enabled", None)
            seg_val.get("shape_dos", {}).pop("enabled", None)


def _default_contact_electrical() -> dict[str, Any]:
    return {
        "enabled": "True",
        "electrical_component": "resistance",
        "electrical_shunt": 1_000_000.0,
        "electrical_symmetrical_resistance": "symmetric",
        "electrical_series_z": 0.2439,
        "electrical_series_x": 0.2439,
        "electrical_series_y": 1e-8,
        "electrical_n": 1.2,
        "electrical_J0": 5e-9,
        "electrical_enable_generation": "False",
    }


def _default_contact_dos() -> dict[str, Any]:
    return {
        "enabled": "True",
        "dd_enabled": "True",
        "mue_y": 1e-5,
        "muh_y": 1e-5,
        "Nc": 5e25,
        "Nv": 5e25,
        "ion_density": 0.0,
        "ion_mobility": 0.0,
        "Xi": "1.6",
        "Eg": "1.3",
        "epsilonr": 5.0,
    }


def _disable_light_source_shapes(data: dict[str, Any]) -> None:
    """Disable geometric light-source boxes when using constant generation."""
    lights = (
        data.get("optical", {})
        .get("light_sources", {})
        .get("lights", {})
    )
    if not isinstance(lights, dict):
        return
    for key, value in lights.items():
        if key.startswith("segment") and isinstance(value, dict):
            value["enabled"] = "False"


def _write_mat_json(path: Path, bandgap_eV: float, eps_r: float) -> None:
    """Write OghmaNano material metadata file."""
    mat = {
        "item_type": "material",
        "color_r": 0.72,
        "color_g": 0.18,
        "color_b": 0.10,
        "color_alpha": 0.5,
        "material_type": "perovskite",
        "status": "public",
        "changelog": "Generated by DFT CsPbI3 workflow from optical n/k arrays.",
        "mat_src": "GPAW PBE/RPA",
        "material_db_electrical_params": {
            "material_blend": "False",
            "Xi0": -3.9,
            "Eg0": float(bandgap_eV),
            "Xi1": -3.9,
            "Eg1": float(bandgap_eV),
            "epsilonr": float(eps_r),
        },
    }
    path.write_text(json.dumps(mat, indent=2), encoding="utf-8")


def _mobility_from_mass(m_star: float) -> float:
    """Convert effective mass (m*/m₀) to approximate mobility [m²/Vs].

    Uses μ = eτ/m* with τ≈10 fs (acoustic phonon scattering limit for halide perovskites).
    Returns in m²/Vs; OghmaNano uses SI units.
    """
    e = 1.602e-19    # C
    tau = 1e-14      # s  (10 fs acoustic phonon)
    m0 = 9.109e-31   # kg
    mu = e * tau / (m_star * m0)   # m²/Vs
    # Clamp to physically reasonable range (0.1 – 100 cm²/Vs = 1e-5 – 1e-2 m²/Vs)
    return float(max(1e-5, min(1e-2, mu)))


def _wine_env() -> dict[str, str]:
    """Return env vars needed for wine64 run.

    Returns empty dict on Windows (native execution, no Wine needed).
    DISPLAY is intentionally not set here on Linux; xvfb-run owns it.
    """
    if sys.platform == "win32":
        return {}
    return {
        "WINEPREFIX":  str(Path.home() / ".wine64"),
        "WINEARCH":    "win64",
        "WINEDEBUG":   "-all",
    }


def build_oghma_worker_command(runner: str, config: dict[str, Any] | None = None) -> list[str]:
    """Build the OghmaNano worker-mode command.

    OghmaNano without arguments starts server mode. Worker mode requires a
    simulation root, ``--simmode`` and ``--lockfile``.
    """
    cfg = config or {}
    on_windows = sys.platform == "win32"
    simmode = str(cfg.get("simmode", "segment0@jv"))
    lockfile = str(cfg.get("lockfile", r"S:\lock0.dat"))
    sim_root_path = str(cfg.get("sim_root_path", cfg.get("sim_path_arg", "S:\\")))
    base: list[str]
    if runner.endswith(".exe") and not on_windows:
        base = ["wine", runner]
    else:
        base = [runner]
    cmd = [*base]
    if sim_root_path:
        cmd.extend(["--sim-root-path", sim_root_path])
    if bool(cfg.get("html_log", True)):
        cmd.extend(["--gui", "--html"])
    cmd.extend(["--simmode", simmode, "--lockfile", lockfile])
    use_xvfb = bool(cfg.get("use_xvfb", True)) and not on_windows
    if use_xvfb:
        return ["xvfb-run", "-a", "--", *cmd]
    return cmd


def _remove_stale_lockfile(sim_dir: Path, lockfile: Any) -> None:
    lock_text = str(lockfile)
    lock_path = Path(lock_text)
    if lock_path.is_absolute():
        if lock_path.exists():
            lock_path.unlink()
        return
    if lock_text.lower().startswith("s:\\"):
        local_name = lock_text[3:].replace("\\", "/")
        path = sim_dir / local_name
    else:
        path = sim_dir / Path(lock_text).name
    if path.exists():
        path.unlink()


def _remove_previous_oghma_outputs(sim_dir: Path) -> None:
    """Remove summary outputs so a forced run cannot reuse stale metrics."""
    for name in (
        "sim_info.dat",
        "jv.csv",
        "iv.csv",
        "jv_internal.csv",
        "jv_contact0.csv",
        "jv_contact1.csv",
        "converge.dat",
    ):
        path = sim_dir / name
        if path.exists():
            path.unlink()


def ensure_oghma_local_windows(materials_overlay: str | Path | None = None) -> Path:
    """Copy workflow-generated materials into the Windows OghmaNano user data dir.

    OghmaNano on Windows looks for materials at:
      %USERPROFILE%\\oghma_local\\materials\\<name>\\
    This function copies every subdirectory from ``materials_overlay`` (our
    sim/materials/) into that location so the core can find CsPbI3/n.csv etc.
    """
    root = Path.home() / "oghma_local" / "materials"
    root.mkdir(parents=True, exist_ok=True)
    if materials_overlay is None:
        return root
    overlay = Path(materials_overlay)
    if not overlay.exists():
        return root
    for child in overlay.iterdir():
        if child.name == "data.json" or not child.is_dir():
            continue
        dest = root / child.name
        dest.mkdir(parents=True, exist_ok=True)
        for src_file in child.iterdir():
            if src_file.is_file():
                shutil.copy2(str(src_file), str(dest / src_file.name))
    return root


def ensure_oghma_local_links(
    root: str | Path | None = None,
    *,
    materials_overlay: str | Path | None = None,
) -> Path:
    """Create OghmaNano data-directory symlinks expected by the Wine core."""
    root = Path(root) if root is not None else Path.home() / "oghma_local"
    root.mkdir(parents=True, exist_ok=True)

    for parent in (Path("/usr/share/oghma_data"), Path("/usr/share/oghma_gui")):
        if not parent.exists():
            continue
        for child in parent.iterdir():
            if parent.name == "oghma_data" and child.name == "materials":
                continue
            if child.is_dir():
                _safe_symlink(child, root / child.name)
    _ensure_materials_overlay(root / "materials", materials_overlay)
    _safe_symlink(Path("/usr/lib/oghma_core/plugins"), root / "plugins")
    return root


def _ensure_materials_overlay(dest: Path, overlay: str | Path | None = None) -> None:
    """Expose system materials plus workflow-generated materials in oghma_local."""
    system_materials = Path("/usr/share/oghma_data/materials")
    if dest.is_symlink():
        dest.unlink()
    dest.mkdir(parents=True, exist_ok=True)
    if system_materials.exists():
        for child in system_materials.iterdir():
            _safe_symlink(child, dest / child.name)
    if overlay is None:
        return
    overlay_path = Path(overlay)
    if not overlay_path.exists():
        return
    for child in overlay_path.iterdir():
        if child.name == "data.json":
            continue
        _safe_symlink(child, dest / child.name)


def ensure_wine_drive_links(sim_dir: str | Path, wineprefix: str | Path | None = None) -> None:
    """Map Wine S: to the active simulation dir and O: to Oghma core."""
    wineprefix = Path(wineprefix) if wineprefix is not None else Path.home() / ".wine64"
    dosdevices = wineprefix / "dosdevices"
    dosdevices.mkdir(parents=True, exist_ok=True)
    _safe_symlink(Path(sim_dir).resolve(), dosdevices / "s:")
    _safe_symlink(Path("/usr/lib/oghma_core"), dosdevices / "o:")


def _safe_symlink(source: Path, dest: Path) -> None:
    if not source.exists():
        return
    if dest.is_symlink() or not dest.exists():
        if dest.is_symlink():
            dest.unlink()
        try:
            dest.symlink_to(source.resolve(), target_is_directory=source.is_dir())
        except OSError:
            if source.is_dir():
                shutil.copytree(source, dest, dirs_exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)


def _apply_fast_oghma_settings(
    data: Any,
    *,
    vstart: float,
    vstop: float,
    vstep: float,
    ion_density: float,
    generation_model: str | None,
) -> None:
    """Reduce runtime for smoke tests by simplifying JV and ion settings."""
    if isinstance(data, dict):
        for key, value in list(data.items()):
            key_lower = str(key).lower()
            if key == "Vstart":
                data[key] = vstart
            elif key == "Vstop":
                data[key] = vstop
            elif key == "Vstep":
                data[key] = vstep
            elif key_lower == "ion_density":
                data[key] = ion_density
            elif key_lower == "ion_mobility" and ion_density == 0.0:
                data[key] = 0.0
            elif key == "charge_carrier_generation_model" and generation_model:
                data[key] = generation_model
            elif key == "dump_verbosity":
                data[key] = min(_float_or_none(value) or 1, 1)
            else:
                _apply_fast_oghma_settings(
                    value,
                    vstart=vstart,
                    vstop=vstop,
                    vstep=vstep,
                    ion_density=ion_density,
                    generation_model=generation_model,
                )
    elif isinstance(data, list):
        for item in data:
            _apply_fast_oghma_settings(
                item,
                vstart=vstart,
                vstop=vstop,
                vstep=vstep,
                ion_density=ion_density,
                generation_model=generation_model,
            )


def _apply_mesh_resolution_settings(
    data: dict[str, Any],
    *,
    electrical_points: Any = None,
    optical_points: Any = None,
) -> None:
    """Optionally refine Oghma electrical/optical y meshes."""
    if electrical_points is not None:
        points = float(electrical_points)
        _set_mesh_y_points(
            data.get("electrical_solver", {}).get("mesh", {}).get("mesh_y", {}),
            points,
        )
        _set_mesh_y_points(
            data.get("mesh", {}).get("mesh_y", {}),
            points,
        )
    if optical_points is not None:
        _set_mesh_y_points(
            data.get("optical", {}).get("mesh", {}).get("mesh_y", {}),
            float(optical_points),
        )


def _set_mesh_y_points(mesh_y: Any, points: float) -> None:
    if not isinstance(mesh_y, dict) or points <= 0:
        return
    for value in mesh_y.values():
        if isinstance(value, dict) and "points" in value:
            value["points"] = points


def _apply_solver_iteration_settings(
    data: dict[str, Any],
    *,
    max_iterations: Any = None,
    ramp_iterations: Any = None,
) -> None:
    """Optionally raise electrical Newton iteration limits for difficult JV sweeps."""
    math_settings = data.setdefault("math", {})
    if not isinstance(math_settings, dict):
        return
    if max_iterations is not None:
        value = int(max_iterations)
        math_settings["maxelectricalitt"] = value
        math_settings["max_newton_iterations"] = value
    if ramp_iterations is not None:
        math_settings["maxelectricalitt_ramp"] = int(ramp_iterations)


def _ensure_oghma_runtime_defaults(data: dict[str, Any], *, newton_name: str | None = None) -> None:
    """Fill keys older OghmaNano templates omit but the v8 worker requires."""
    math = data.setdefault("math", {})
    if newton_name:
        math["newton_name"] = str(newton_name)
    math.setdefault("matrix_block_normalization", "False")
    math.setdefault("block_auto", "True")
    math.setdefault("block_phi_norm", 1e3)
    math.setdefault("block_Je_norm", 1e20)
    math.setdefault("block_Jh_norm", 1e20)
    math.setdefault("block_srh_e_norm", 1e20)
    math.setdefault("block_srh_h_norm", 1e20)
    math.setdefault("math_current_calc_at", "contacts")
    math.setdefault("math_dynamic_mesh", "False")
    math.setdefault("math_stop_on_convergence_problem", "False")
    math.setdefault("math_stop_on_inverted_fermi_level", "False")
    math.setdefault("solver_verbosity", "solver_verbosity_at_end")
    math.setdefault("matrix_threshold_enabled", "False")
    math.setdefault("matrix_threshold", 1e-20)
    matrix = math.setdefault("matrix", {})
    matrix.setdefault("solver_name", "umfpack")
    matrix.setdefault("core_max_threads", "all")
    matrix.setdefault("complex_solver_name", "complex_umfpack")
    matrix.setdefault("matrix_dump_error", "False")
    matrix.setdefault("matrix_dump_every_matrix", "False")
    matrix.setdefault("matrix_threshold_enabled", "False")
    matrix.setdefault("matrix_threshold", 1e-20)


def _extract_oghma_error(text: str) -> str | None:
    """Extract the last OghmaNano ``error:`` line from text/html logs."""
    plain = re.sub(r"<[^>]+>", "", text).replace("&nbsp;", " ")
    matches = re.findall(r"error:[^\n\r<]+", plain, flags=re.IGNORECASE)
    if not matches:
        return None
    error = matches[-1].strip()
    if "X connection" in error:
        error = error.split("X connection", 1)[0].strip()
    return error[:240]


# ── result parser ─────────────────────────────────────────────────────────────

def parse_oghma_sim_info(path: str | Path) -> dict[str, float] | None:
    """Parse OghmaNano ``sim_info.dat``.

    OghmaNano writes sim_info.dat as JSON with keys ``pce``, ``ff``, ``voc``,
    ``jsc`` (dimensionless / SI).  We normalise keys and units here.
    """
    path = Path(path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        # Try key=value line format (older OghmaNano versions)
        data = {}
        for line in path.read_text().splitlines():
            if "=" in line:
                k, _, v = line.partition("=")
                try:
                    data[k.strip()] = float(v.strip())
                except ValueError:
                    pass

    # Normalise keys to our naming convention
    pce = _float_or_none(data.get("pce") or data.get("pce_pct") or data.get("PCE"))
    voc = _float_or_none(data.get("voc") or data.get("Voc") or data.get("voc_V"))
    jsc = _float_or_none(data.get("jsc") or data.get("Jsc") or data.get("jsc_mA_cm2"))
    ff  = _float_or_none(data.get("ff")  or data.get("FF"))

    # OghmaNano reports PCE as 0–1 fraction; convert to percent if needed
    if pce is not None and pce <= 1.0:
        pce *= 100.0
    # jsc in A/m² → mA/cm² (×0.1)
    jsc = _normalise_jsc_to_mA_cm2(jsc, pce_pct=pce, voc_V=voc, ff=ff, source=path)

    if all(v is None for v in (pce, voc, jsc, ff)):
        return None
    return {"pce_pct": pce, "voc_V": voc, "jsc_mA_cm2": jsc, "ff": ff}


def _normalise_jsc_to_mA_cm2(
    jsc: float | None,
    *,
    pce_pct: float | None = None,
    voc_V: float | None = None,
    ff: float | None = None,
    source: Path | None = None,
) -> float | None:
    """Infer whether Oghma Jsc is already mA/cm2 or raw A/m2."""
    if jsc is None:
        return None
    if not np.isfinite(jsc):
        return jsc

    candidates = {
        "as_mA_cm2": jsc,
        "A_m2_to_mA_cm2": jsc * _A_M2_TO_MA_CM2,
    }
    expected = None
    if pce_pct and voc_V and ff and voc_V > 0 and ff > 0:
        expected = pce_pct * _PIN_MW_CM2 / (voc_V * ff) / 100.0
        candidates["pce_consistent"] = np.sign(jsc or 1.0) * expected

    best_label = "as_mA_cm2"
    if expected is not None and expected > 0:
        if abs(abs(jsc) - expected) / expected <= 0.05:
            best_label = "as_mA_cm2"
        else:
            best_label = min(candidates, key=lambda key: abs(abs(candidates[key]) - expected))
    elif abs(jsc) > 35.0:
        best_label = "A_m2_to_mA_cm2"

    corrected = float(candidates[best_label])
    if best_label != "as_mA_cm2":
        where = f" in {source}" if source else ""
        warnings.warn(
            f"Interpreting Oghma Jsc={jsc:g}{where} as A/m^2; "
            f"reporting {corrected:g} mA/cm^2.",
            RuntimeWarning,
            stacklevel=2,
        )
    if expected is not None and expected > 0:
        rel = abs(abs(corrected) - expected) / expected
        if rel > 0.05:
            warnings.warn(
                "Oghma PV metrics are not PCE-consistent: "
                f"|Jsc|={abs(corrected):.4g} mA/cm^2, expected {expected:.4g} "
                f"from PCE={pce_pct:.4g}%, Voc={voc_V:.4g} V, FF={ff:.4g}.",
                RuntimeWarning,
                stacklevel=2,
            )
    if abs(corrected) > 35.0:
        warnings.warn(
            f"Jsc={corrected:.4g} mA/cm^2 exceeds the defensive 35 mA/cm^2 "
            "threshold for Eg~1.59 eV without concentration.",
            RuntimeWarning,
            stacklevel=2,
        )
    return corrected


# ── device stack builder ──────────────────────────────────────────────────────

def build_device_stack_from_dft(
    phase_dir: str | Path,
    *,
    phase: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a simple perovskite device stack from completed DFT outputs."""
    phase_dir = Path(phase_dir)
    cfg = config or {}
    score = _read_json(phase_dir / "12_score" / "solar_score.json")
    sq = _read_json(phase_dir / "13_sq_limit" / "sq_limit.json")
    electronic = _read_json(phase_dir / "10_effective_masses" / "electronic_analysis.json")

    absorber_thickness = cfg.get("absorber_thickness_nm")
    if absorber_thickness is None:
        absorber_thickness = sq.get("thickness_nm", cfg.get("thickness_nm", 500.0))

    bandgap = (
        score.get("inputs", {}).get("bandgap_eV")
        or electronic.get("gap_eV")
        or cfg.get("absorber_bandgap_eV")
    )
    eps_r = score.get("inputs", {}).get("eps_r") or cfg.get("absorber_eps_r")

    default_layers = [
        {"name": "FTO",           "role": "front_contact", "thickness_nm": 50.0},
        {"name": "TiO2",          "role": "ETL",           "thickness_nm": 200.0, "bandgap_eV": 3.2},
        {
            "name": "CsPbI3",
            "role": "absorber",
            "thickness_nm": float(absorber_thickness),
            "bandgap_eV": bandgap,
            "dielectric_constant": eps_r,
        },
        {"name": "Spiro-OMeTAD",  "role": "HTL",           "thickness_nm": 200.0, "bandgap_eV": 3.0},
        {"name": "Au",            "role": "back_contact",  "thickness_nm": 100.0},
    ]
    layers = cfg.get("layers", default_layers)

    return {
        "simulator": "OghmaNano",
        "phase": phase,
        "formula": cfg.get("formula", "CsPbI3"),
        "method_type": "device_physics_drift_diffusion_not_ml",
        "layers": layers,
        "dft_inputs": {
            "bandgap_eV": bandgap,
            "dielectric_constant": eps_r,
            "effective_masses": {
                "m_e_m0": electronic.get("m_e_soc_m0") or electronic.get("m_e_m0"),
                "m_h_m0": electronic.get("m_h_soc_m0") or electronic.get("m_h_m0"),
            },
            "sq_limit_reference": {
                "pce_pct": sq.get("pce_pct"),
                "jsc_mA_cm2": sq.get("jsc_mA_cm2"),
                "voc_V": sq.get("voc_V"),
                "ff": sq.get("ff"),
            },
        },
        "source_files": {
            "solar_score":        str(phase_dir / "12_score" / "solar_score.json"),
            "sq_limit":           str(phase_dir / "13_sq_limit" / "sq_limit.json"),
            "electronic_analysis": str(phase_dir / "10_effective_masses" / "electronic_analysis.json"),
            "optical_frequencies": str(phase_dir / "11_optical" / "optical_frequencies.npy"),
            "absorption":         str(phase_dir / "11_optical" / "absorption_cm1.npy"),
            "n_omega":            str(phase_dir / "11_optical" / "n_omega.npy"),
            "k_omega":            str(phase_dir / "11_optical" / "k_omega.npy"),
        },
    }


# ── HTML comparison report ────────────────────────────────────────────────────

def write_oghma_method_comparison(
    step_dir: str | Path,
    stack: dict[str, Any],
    oghma_result: OghmaDeviceResult,
) -> Path:
    """Write an HTML comparison of DFT SQ, OghmaNano DD, and ML placeholders."""
    step_dir = Path(step_dir)
    sq_ref = stack.get("dft_inputs", {}).get("sq_limit_reference", {})
    records = [
        {
            "name": "DFT — Shockley-Queisser (detailed balance)",
            "method_type": "dft_postprocessed_detailed_balance",
            "pce_pct": sq_ref.get("pce_pct"),
            "voc_V":   sq_ref.get("voc_V"),
            "jsc_mA_cm2": sq_ref.get("jsc_mA_cm2"),
            "ff":      sq_ref.get("ff"),
            "flags":   ["REFERENCE_FROM_13_SQ_LIMIT"],
        },
        {
            "name": "OghmaNano — drift-diffusion device physics",
            "method_type": oghma_result.method_type,
            "pce_pct": oghma_result.pce_pct,
            "voc_V":   oghma_result.voc_V,
            "jsc_mA_cm2": oghma_result.jsc_mA_cm2,
            "ff":      oghma_result.ff,
            "flags":   oghma_result.flags,
        },
        {
            "name": "AINAGENT — ML surrogate",
            "method_type": "ml_property_model",
            "pce_pct": None, "voc_V": None, "jsc_mA_cm2": None, "ff": None,
            "flags": ["IMPORT_AINAGENT_RESULT_JSON_FOR_SIDE_BY_SIDE_COMPARISON"],
        },
    ]
    report_path = step_dir / "method_comparison.html"
    report_path.write_text(_render_comparison_html(records, title="DFT/OghmaNano/AINAGENT PV Comparison"), encoding="utf-8")
    return report_path


def _render_comparison_html(records: list[dict[str, Any]], *, title: str) -> str:
    max_pce = max([_float_or_none(row.get("pce_pct")) or 0.0 for row in records] + [30.0])
    cards = "\n".join(_render_card(row, max_pce=max_pce) for row in records)
    payload = html.escape(json.dumps(records, indent=2))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
  <style>
    body {{ margin:0; font-family:Arial,sans-serif; background:#f7f8fa; color:#17202a; }}
    main {{ max-width:1120px; margin:0 auto; padding:32px 20px; }}
    h1 {{ font-size:28px; margin:0 0 8px; }}
    p  {{ color:#4c5967; line-height:1.5; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:16px; }}
    .card {{ background:white; border:1px solid #d8dee6; border-radius:8px; padding:16px; }}
    .name {{ font-size:18px; font-weight:700; margin-bottom:6px; }}
    .method {{ font-family:monospace; font-size:13px; color:#526070; }}
    .metric {{ display:flex; justify-content:space-between; margin:12px 0 4px; }}
    .bar {{ height:10px; background:#e5e9ef; border-radius:999px; overflow:hidden; }}
    .fill {{ height:100%; background:#2374ab; }}
    .flags {{ margin-top:12px; font-size:12px; color:#8a4b08; word-break:break-all; }}
    pre {{ overflow:auto; background:#111827; color:#e5e7eb; padding:16px; border-radius:8px; }}
  </style>
</head>
<body>
<main>
  <h1>{html.escape(title)}</h1>
  <p>DFT Shockley-Queisser (detailed balance), OghmaNano drift-diffusion, and AINAGENT ML.
     OghmaNano includes recombination, transport, and ion migration beyond the SQ limit assumptions.</p>
  <section class="grid">{cards}</section>
  <h2>Raw Records</h2>
  <pre>{payload}</pre>
</main>
</body>
</html>
"""


def _render_card(row: dict[str, Any], *, max_pce: float) -> str:
    pce = _float_or_none(row.get("pce_pct"))
    width = 0.0 if pce is None else max(0.0, min(100.0, 100.0 * pce / max_pce))
    pce_label = "not yet run" if pce is None else f"{pce:.2f}%"
    flags = ", ".join(str(f) for f in row.get("flags", [])) or "none"
    return f"""<article class="card">
  <div class="name">{html.escape(str(row.get("name","??")))}</div>
  <div class="method">{html.escape(str(row.get("method_type","???")))}</div>
  <div class="metric"><span>PCE</span><strong>{html.escape(pce_label)}</strong></div>
  <div class="bar"><div class="fill" style="width:{width:.1f}%"></div></div>
  <div class="metric"><span>Voc</span><span>{_fmt(_float_or_none(row.get("voc_V"))," V")}</span></div>
  <div class="metric"><span>Jsc</span><span>{_fmt(_float_or_none(row.get("jsc_mA_cm2"))," mA/cm²")}</span></div>
  <div class="metric"><span>FF</span><span>{_fmt(_float_or_none(row.get("ff")),"")}</span></div>
  <div class="flags">Flags: {html.escape(flags)}</div>
</article>"""


def _fmt(value: float | None, suffix: str) -> str:
    return "not yet run" if value is None else f"{value:.3g}{suffix}"


# ── plots ────────────────────────────────────────────────────────────────────

def plot_oghma_results(
    step_dir: str | Path,
    sim_dir: str | Path,
    result: "OghmaDeviceResult",
) -> list[Path]:
    """Generate publication-style plots from OghmaNano outputs.

    Saves to step_dir:
      jv_curve.png        — J-V curve + power density + operating point
      generation_profile.png — carrier generation rate vs depth in device
    Returns list of paths written (skips silently if data is missing).
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.ticker as ticker
    except ImportError:
        return []

    step_dir = Path(step_dir)
    sim_dir = Path(sim_dir)
    written: list[Path] = []

    # ── shared style ─────────────────────────────────────────────────────────
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.size": 11,
        "axes.linewidth": 1.2,
        "axes.labelsize": 12,
        "legend.fontsize": 10,
        "figure.dpi": 150,
    })

    # ── 1. J-V curve ─────────────────────────────────────────────────────────
    jv_path = sim_dir / "jv.csv"
    if jv_path.exists():
        V, J_raw = _read_oghma_xy(jv_path)
        J = [j * 0.1 for j in J_raw]           # A/m² → mA/cm²
        P = [v * abs(j) for v, j in zip(V, J_raw) if j < 0]
        V_pce = [v for v, j in zip(V, J_raw) if j < 0]

        fig, ax1 = plt.subplots(figsize=(6, 4.5))
        ax2 = ax1.twinx()

        ax1.plot(V, J, "b-o", markersize=4, linewidth=2, label="J-V")
        ax1.axhline(0, color="k", linewidth=0.7, linestyle="--")
        ax1.axvline(0, color="k", linewidth=0.7, linestyle="--")

        if V_pce:
            ax2.plot(V_pce, [p * 0.1 for p in P], "r--", linewidth=1.5,
                     alpha=0.7, label="Power")
            pmax = max(P)
            v_pmax = V_pce[P.index(pmax)]
            j_pmax = J_raw[[v for v, j in zip(V, J_raw) if j < 0].index(j_pmax)
                            if False else P.index(pmax)]
            ax2.plot(v_pmax, pmax * 0.1, "rs", markersize=7, zorder=5)

        # Annotate key parameters
        pce  = result.pce_pct
        voc  = result.voc_V
        jsc  = result.jsc_mA_cm2
        ff   = result.ff
        info = "\n".join([
            f"PCE = {pce:.2f} %" if pce else "PCE = —",
            f"Voc = {voc:.3f} V"  if voc else "Voc = —",
            f"Jsc = {abs(jsc):.2f} mA/cm²" if jsc else "Jsc = —",
            f"FF  = {ff*100:.1f} %"   if ff  else "FF  = —",
        ])
        ax1.text(0.04, 0.05, info, transform=ax1.transAxes,
                 fontsize=9.5, family="monospace",
                 verticalalignment="bottom",
                 bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                           edgecolor="gray", alpha=0.85))

        ax1.set_xlabel("Voltage (V)")
        ax1.set_ylabel("Current density (mA cm⁻²)", color="b")
        ax2.set_ylabel("Power density (mW cm⁻²)", color="r")
        ax1.tick_params(axis="y", colors="b")
        ax2.tick_params(axis="y", colors="r")
        ax1.set_title("CsPbI₃ J-V Curve — OghmaNano drift-diffusion")

        lines1, lab1 = ax1.get_legend_handles_labels()
        lines2, lab2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, lab1 + lab2, loc="upper left")

        fig.tight_layout()
        out = step_dir / "jv_curve.png"
        fig.savefig(str(out), bbox_inches="tight")
        plt.close(fig)
        written.append(out)

    # ── 2. Generation rate profile ────────────────────────────────────────────
    g_path = sim_dir / "optical_output" / "G_y.csv"
    if g_path.exists():
        y_m, G = _read_oghma_xy(g_path)
        y_nm = [yi * 1e9 for yi in y_m]        # m → nm

        fig, ax = plt.subplots(figsize=(5.5, 4))
        ax.plot(y_nm, [gi * 1e-6 for gi in G], "g-", linewidth=2)
        ax.set_xlabel("Depth in device (nm)")
        ax.set_ylabel("Generation rate (×10⁶ m⁻³ s⁻¹)")
        ax.set_title("Carrier Generation Profile — OghmaNano")
        ax.xaxis.set_minor_locator(ticker.AutoMinorLocator())
        ax.yaxis.set_minor_locator(ticker.AutoMinorLocator())
        ax.tick_params(which="both", direction="in")
        fig.tight_layout()
        out = step_dir / "generation_profile.png"
        fig.savefig(str(out), bbox_inches="tight")
        plt.close(fig)
        written.append(out)

    return written


def _read_oghma_xy(path: Path) -> tuple[list[float], list[float]]:
    """Parse OghmaNano xy CSV (skip #-comment lines, space-separated floats)."""
    xs, ys = [], []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            try:
                xs.append(float(parts[0]))
                ys.append(float(parts[1]))
            except ValueError:
                pass
    return xs, ys


# ── helpers ───────────────────────────────────────────────────────────────────

def resolve_oghma_runner(explicit: str | None = None) -> str | None:
    """Resolve the oghma_core runner path."""
    candidates: list[str | None] = [
        explicit,
        os.environ.get("OGHMA_EXECUTABLE"),
        shutil.which("oghma_core"),
        shutil.which("oghma"),
    ]
    if sys.platform == "win32":
        candidates.extend([
            r"C:\Program Files (x86)\OghmaNano\oghma_core.exe",
            r"C:\Program Files\OghmaNano\oghma_core.exe",
            r"C:\OghmaNano\oghma_core.exe",
        ])
    for c in candidates:
        if c:
            return str(c)
    return None


def _append_unique_flag(flags: list[str], flag: str) -> None:
    if flag not in flags:
        flags.append(flag)


def _append_oghma_output_flags(
    step_dir: Path,
    sim_dir: Path,
    phase_dir: Path,
    stack: dict[str, Any],
    flags: list[str],
) -> None:
    """Add defensive interpretation flags from completed OghmaNano outputs."""
    sim_info = sim_dir / "sim_info.dat"
    try:
        raw = json.loads(sim_info.read_text(encoding="utf-8")) if sim_info.exists() else {}
    except json.JSONDecodeError:
        raw = {}
    raw_jsc = _float_or_none(raw.get("jsc") or raw.get("Jsc") or raw.get("jsc_mA_cm2"))
    parsed = parse_oghma_sim_info(sim_info)
    parsed_jsc = parsed.get("jsc_mA_cm2") if parsed else None
    if raw_jsc is not None and parsed_jsc is not None and abs(raw_jsc - parsed_jsc) > max(1e-9, abs(raw_jsc) * 0.1):
        _append_unique_flag(flags, "WARNING_JSC_SIM_INFO_INTERPRETED_AS_A_M2_AND_CONVERTED_TO_MA_CM2")

    opt_dir = phase_dir / "11_optical"
    optical_npy = [
        opt_dir / "optical_frequencies.npy",
        opt_dir / "absorption_cm1.npy",
        opt_dir / "n_omega.npy",
        opt_dir / "k_omega.npy",
    ]
    if not all(path.exists() for path in optical_npy):
        if (opt_dir / "dielectric_function.csv").exists():
            _append_unique_flag(flags, "WARNING_DFT_OPTICAL_NPY_FILES_MISSING_USED_DIELECTRIC_CSV")
        else:
            _append_unique_flag(flags, "WARNING_DFT_OPTICAL_NPY_FILES_MISSING_CURRENT_MATERIAL_USED_FALLBACK")

    g_path = sim_dir / "optical_output" / "G_y.csv"
    if not g_path.exists():
        return
    y_m, generation = _read_oghma_xy(g_path)
    if not y_m or not generation:
        return
    total_nm, absorber_start_nm, absorber_end_nm = _stack_bounds_nm(stack)
    if total_nm <= 0.0:
        return
    y_nm = np.asarray(y_m, dtype=float) * 1e9
    generation_arr = np.asarray(generation, dtype=float)
    depth_max = float(np.nanmax(y_nm))
    if abs(depth_max - total_nm) > max(25.0, 0.05 * total_nm):
        _append_unique_flag(flags, "WARNING_GENERATION_DEPTH_EXCLUDES_HTL_BACK_CONTACT_OR_USES_ACTIVE_OPTICAL_SUBREGION")
    if np.any(np.isfinite(generation_arr)):
        peak_nm = float(y_nm[int(np.nanargmax(generation_arr))])
        if not (absorber_start_nm <= peak_nm <= absorber_end_nm):
            _append_unique_flag(flags, "WARNING_GENERATION_PEAK_OUTSIDE_ABSORBER")


def _stack_bounds_nm(stack: dict[str, Any]) -> tuple[float, float, float]:
    total = 0.0
    absorber_start = float("nan")
    absorber_end = float("nan")
    for layer in stack.get("layers", []):
        dy = float(layer.get("thickness_nm") or 0.0)
        if layer.get("role") == "absorber":
            absorber_start = total
            absorber_end = total + dy
        total += dy
    return total, absorber_start, absorber_end


def _write_readme(step_dir: Path, *, runner: str | None) -> None:
    runner_text = runner or "<install OghmaNano: bash scripts/install_oghma_ubuntu.sh>"
    sim_path = str((step_dir / "sim").resolve())
    lockfile = str((step_dir / "sim" / "lock0.dat").resolve())
    (step_dir / "README_oghma_device.md").write_text(
        "# OghmaNano device step\n\n"
        "OghmaNano is a drift-diffusion + optics device physics solver (not ML).\n\n"
        "## Files generated\n\n"
        "- `device_stack.json` — DFT-derived device parameters\n"
        "- `sim/sim.json` — OghmaNano project (perovskite template + DFT params)\n"
        "- `sim/materials/CsPbI3/nk.csv` — DFT n(ω)/k(ω) optical data\n"
        "- `sim/materials/CsPbI3/mat.json` — material metadata\n\n"
        "## To run\n\n"
        "Either set `execute: true` in `configs/default_params.yaml` under `oghma_device:`\n"
        "and rerun the workflow, or run manually:\n\n"
        "```powershell\n"
        f"& \"{runner_text}\" --sim-root-path \"{sim_path}\" --gui --html "
        f"--simmode segment0@jv --lockfile \"{lockfile}\"\n"
        "```\n\n"
        "Linux/Wine runs use the same worker arguments, with `xvfb-run -a --` and the Wine S: drive mapping.\n\n"
        "Output `sim_info.dat` is parsed for PCE, Voc, Jsc, FF on next workflow run.\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
