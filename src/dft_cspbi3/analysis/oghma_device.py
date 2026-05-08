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
    stack_path.write_text(json.dumps(stack, indent=2))

    runner = resolve_oghma_runner(cfg.get("executable"))
    execute = bool(cfg.get("execute", False)) and not dry_run
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
    manifest_path.write_text(json.dumps(manifest, indent=2))
    _write_readme(step_dir, runner=runner)

    # ── parse pre-existing sim_info.dat ──────────────────────────────────────
    parsed = parse_oghma_sim_info(sim_info_path)
    if parsed:
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
        result_path.write_text(json.dumps(out.to_dict(), indent=2))
        return out

    # ── run oghma_core ────────────────────────────────────────────────────────
    if execute and runner and "OGHMA_PROJECT_WRITTEN" in flags:
        ensure_oghma_local_links(materials_overlay=sim_dir / "materials")
        ensure_wine_drive_links(sim_dir)
        wine_env = _wine_env()
        worker_cmd = build_oghma_worker_command(runner, cfg)
        _remove_stale_lockfile(sim_dir, cfg.get("lockfile", r"S:\lock0.dat"))
        try:
            completed = subprocess.run(
                worker_cmd,
                cwd=str(sim_dir),
                check=False,
                capture_output=True,
                text=True,
                timeout=int(cfg.get("timeout_s", 600)),
                env={**os.environ, **wine_env},
            )
            (step_dir / "oghma_stdout.log").write_text(completed.stdout)
            (step_dir / "oghma_stderr.log").write_text(completed.stderr)
            parsed = parse_oghma_sim_info(sim_info_path)
            status = "completed" if completed.returncode == 0 else "failed"
            if completed.returncode != 0:
                flags.append(f"OGHMANANO_RETURN_CODE:{completed.returncode}")
                if error := _extract_oghma_error(completed.stdout + "\n" + completed.stderr):
                    flags.append(f"OGHMANANO_ERROR:{error}")
        except subprocess.TimeoutExpired as exc:
            (step_dir / "oghma_stdout.log").write_text((exc.stdout or "") if isinstance(exc.stdout, str) else "")
            (step_dir / "oghma_stderr.log").write_text((exc.stderr or "") if isinstance(exc.stderr, str) else "")
            parsed = parse_oghma_sim_info(sim_info_path)
            status = "timeout"
            flags.append(f"OGHMANANO_TIMEOUT:{int(cfg.get('timeout_s', 600))}s")
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
        result_path.write_text(json.dumps(out.to_dict(), indent=2))
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

    Creates:
      sim_dir/
        sim.json/json.inp — full OghmaNano project (perovskite template + DFT params)
        materials/
          data.json       — local material database index
          CsPbI3/
            data.json     — material metadata in OghmaNano format
            n.csv         — DFT n(lambda), wavelength in meters
            alpha.csv     — DFT alpha(lambda), wavelength in meters, alpha in m^-1
            nk.csv        — convenience copy for inspection: wavelength_nm, n, k
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

    # ── fetch perovskite template ─────────────────────────────────────────────
    sim_json = _get_perovskite_template()

    # ── patch simulation mode ─────────────────────────────────────────────────
    simmode = str(cfg.get("simmode", "segment0@jv"))
    sim_json["sim"]["simmode"] = simmode

    # ── patch epitaxy layers ──────────────────────────────────────────────────
    epi = sim_json["epitaxy"]
    for seg_key, seg_val in epi.items():
        if not (seg_key.startswith("segment") and isinstance(seg_val, dict)):
            continue
        name = seg_val.get("name", "").lower()
        dos = seg_val.get("shape_dos", {})
        if name in {"au", "ag", "al"}:
            # Metal contacts: obj_type="contact" with dd_enabled=True.
            # Setting dd_enabled=False causes the light-solver to throw
            # "shape covering electrical mesh with no electrical parameters".
            seg_val["obj_type"] = "contact"
            dos.setdefault("dd_enabled", "True")
            seg_val["shape_dos"] = dos
            se = seg_val.setdefault("shape_electrical", {})
            se["enabled"] = "True"
            se.setdefault("work_function", _METAL_WORK_FUNCTION.get(name, 5.0))
        if "perovskite" in name:
            seg_val["dy"] = thickness_m
            dos["Eg"] = float(bandgap_eV)
            dos["epsilonr"] = float(eps_r)
            dos["mue_y"] = _mobility_from_mass(m_e)
            dos["muh_y"] = _mobility_from_mass(m_h)
            dos["mue_x"] = dos["mue_y"]
            dos["mue_z"] = dos["mue_y"]
            dos["muh_x"] = dos["muh_y"]
            dos["muh_z"] = dos["muh_y"]
            # Apply literature transport defaults
            for k, v in _CSPBI3_TRANSPORT.items():
                if k not in ("Eg", "epsilonr", "mue_y", "muh_y"):
                    dos.setdefault(k, v)
            seg_val["shape_dos"] = dos
            # Point to DFT nk material
            seg_val["optical_material"] = "CsPbI3"
    _reposition_epitaxy_layers(epi)
    _normalize_contact_shapes(epi)
    _enable_shape_electrical_blocks(sim_json)
    _patch_electrical_mesh_y(epi, sim_json)

    fast_mode = bool(cfg.get("fast_mode", True))
    if fast_mode:
        gen_model = cfg.get("fast_generation_model", "light_constant")
        _apply_fast_oghma_settings(
            sim_json,
            vstep=float(cfg.get("fast_vstep", 0.1)),
            ion_density=float(cfg.get("fast_ion_density", 0.0)),
            generation_model=gen_model,
        )
        if gen_model == "light_constant":
            _disable_light_source_shapes(sim_json)
            # Use flat optical model to bypass TMM light pointer array construction
            # (full TMM triggers an Au shape check that fails under Wine/headless).
            sim_json.setdefault("optical", {}).setdefault("light", {})["light_model"] = "flat"
    _ensure_oghma_runtime_defaults(
        sim_json,
        newton_name=cfg.get("newton_name", "newton_simple" if fast_mode else None),
    )

    # ── write sim.json ────────────────────────────────────────────────────────
    (sim_dir / "sim.json").write_text(json.dumps(sim_json, indent=2))
    (sim_dir / "json.inp").write_text(json.dumps(sim_json, indent=2))

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


def _get_perovskite_template() -> dict[str, Any]:
    """Return the OghmaNano perovskite template (cached after first download)."""
    cache = Path("/tmp/_oghma_perovskite_template.json")
    if cache.exists():
        return json.loads(cache.read_text())
    url = (
        "https://raw.githubusercontent.com/roderickmackenzie/OghmaNano"
        "/master/oghma_data/device_lib/perovskite/perovskite.json"
    )
    try:
        result = subprocess.run(
            ["wget", "-q", "--timeout=20", "-O", str(cache), url],
            check=True, capture_output=True,
        )
        return json.loads(cache.read_text())
    except Exception:
        # Return a minimal working template if download fails
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


def _write_nk_csv(path: Path, rows: list[tuple[float, float, float]]) -> None:
    """Export n(lambda), k(lambda) for human inspection: wavelength_nm, n, k."""
    lines = ["#wavelength_nm n k\n"]
    for wl, n, k in rows:
        lines.append(f"{wl:.4f} {n:.6f} {k:.6f}\n")
    path.write_text("".join(lines))


def _cauchy_nk_rows() -> list[tuple[float, float, float]]:
    """Analytical Cauchy n(lambda) + Urbach k(lambda) for CsPbI3 offline fallback."""
    wl = np.linspace(300, 1000, 200)  # nm
    # Cauchy: n ~= 2.25 + 0.02/lambda^2(um)
    n = 2.25 + 0.02 / (wl * 1e-3) ** 2
    # Urbach tail: k exponential above Eg=1.59 eV (lambda < 780 nm)
    E = 1239.84 / wl
    k = np.where(E > 1.59, 0.5 * np.exp((E - 1.59) / 0.1), 0.0)
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
    path.write_text("".join(lines))


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
    path.write_text("".join(lines))


def _write_materials_index_json(path: Path) -> None:
    """Write the local material database index that OghmaNano probes first."""
    template = Path("/usr/share/oghma_data/materials/data.json")
    if template.exists():
        path.write_text(template.read_text())
        return
    path.write_text(json.dumps({"item_type": "material_db", "status": "public"}, indent=2))


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
    path.write_text(json.dumps(mat, indent=2))


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

    DISPLAY is intentionally not set here; xvfb-run owns it.
    """
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
    simmode = str(cfg.get("simmode", "segment0@jv"))
    lockfile = str(cfg.get("lockfile", r"S:\lock0.dat"))
    sim_root_path = str(cfg.get("sim_root_path", cfg.get("sim_path_arg", "S:\\")))
    base: list[str]
    if runner.endswith(".exe"):
        base = ["wine", runner]
    else:
        base = [runner]
    cmd = [*base]
    if sim_root_path:
        cmd.extend(["--sim-root-path", sim_root_path])
    if bool(cfg.get("html_log", True)):
        cmd.extend(["--gui", "--html"])
    cmd.extend(["--simmode", simmode, "--lockfile", lockfile])
    if bool(cfg.get("use_xvfb", True)):
        return ["xvfb-run", "-a", "--", *cmd]
    return cmd


def _remove_stale_lockfile(sim_dir: Path, lockfile: Any) -> None:
    lock_text = str(lockfile)
    if lock_text.lower().startswith("s:\\"):
        local_name = lock_text[3:].replace("\\", "/")
        path = sim_dir / local_name
    else:
        path = sim_dir / Path(lock_text).name
    if path.exists():
        path.unlink()


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
        dest.symlink_to(source.resolve())


def _apply_fast_oghma_settings(
    data: Any,
    *,
    vstep: float,
    ion_density: float,
    generation_model: str | None,
) -> None:
    """Reduce runtime for smoke tests by simplifying JV and ion settings."""
    if isinstance(data, dict):
        for key, value in list(data.items()):
            key_lower = str(key).lower()
            if key == "Vstep":
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
                    vstep=vstep,
                    ion_density=ion_density,
                    generation_model=generation_model,
                )
    elif isinstance(data, list):
        for item in data:
            _apply_fast_oghma_settings(
                item,
                vstep=vstep,
                ion_density=ion_density,
                generation_model=generation_model,
            )


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
    if jsc is not None and jsc > 100:
        jsc *= 0.1

    if all(v is None for v in (pce, voc, jsc, ff)):
        return None
    return {"pce_pct": pce, "voc_V": voc, "jsc_mA_cm2": jsc, "ff": ff}


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
        {"name": "FTO",           "role": "front_contact", "thickness_nm": 500.0},
        {"name": "SnO2",          "role": "ETL",           "thickness_nm": 50.0, "bandgap_eV": 3.6},
        {
            "name": "CsPbI3",
            "role": "absorber",
            "thickness_nm": float(absorber_thickness),
            "bandgap_eV": bandgap,
            "dielectric_constant": eps_r,
        },
        {"name": "Spiro-OMeTAD",  "role": "HTL",           "thickness_nm": 200.0, "bandgap_eV": 3.0},
        {"name": "Au",            "role": "back_contact",  "thickness_nm": 80.0},
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
    report_path.write_text(_render_comparison_html(records, title="DFT/OghmaNano/AINAGENT PV Comparison"))
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


# ── helpers ───────────────────────────────────────────────────────────────────

def resolve_oghma_runner(explicit: str | None = None) -> str | None:
    """Resolve the oghma_core runner path."""
    candidates = [
        explicit,
        os.environ.get("OGHMA_EXECUTABLE"),
        shutil.which("oghma_core"),
        shutil.which("oghma"),
    ]
    for c in candidates:
        if c:
            return str(c)
    return None


def _write_readme(step_dir: Path, *, runner: str | None) -> None:
    runner_text = runner or "<install OghmaNano: bash scripts/install_oghma_ubuntu.sh>"
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
        f"```bash\ncd sim && {runner_text}\n```\n\n"
        "Output `sim_info.dat` is parsed for PCE, Voc, Jsc, FF on next workflow run.\n"
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
