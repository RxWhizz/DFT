import json
import importlib.util
from pathlib import Path
import sys

from dft_cspbi3.analysis.oghma_device import (
    _apply_bandgap_absorption_onset,
    _extract_oghma_error,
    _wine_env,
    build_device_stack_from_dft,
    build_oghma_worker_command,
    ensure_oghma_local_links,
    parse_oghma_sim_info,
    prepare_oghma_device_step,
    write_oghma_sim_dir,
)
import numpy as np


def _load_debug_outputs_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "debug_oghma_outputs.py"
    spec = importlib.util.spec_from_file_location("_debug_oghma_outputs_test", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_oghma_device_step_prepares_dft_handoff(tmp_path):
    phase_dir = tmp_path / "alpha"
    (phase_dir / "12_score").mkdir(parents=True)
    (phase_dir / "13_sq_limit").mkdir()
    (phase_dir / "10_effective_masses").mkdir()
    (phase_dir / "12_score" / "solar_score.json").write_text(json.dumps({
        "inputs": {"bandgap_eV": 1.58, "eps_r": 6.2}
    }))
    (phase_dir / "13_sq_limit" / "sq_limit.json").write_text(json.dumps({
        "thickness_nm": 500.0,
        "pce_pct": 27.2,
        "jsc_mA_cm2": 23.9,
        "voc_V": 1.26,
        "ff": 0.90,
    }))
    (phase_dir / "10_effective_masses" / "electronic_analysis.json").write_text(json.dumps({
        "m_e_m0": 0.11,
        "m_h_m0": 0.15,
    }))

    result = prepare_oghma_device_step(
        phase_dir,
        phase_dir / "14_oghma_device",
        phase="alpha",
        config={"execute": False},
    )

    assert result.status == "prepared"
    assert result.method_type == "device_physics_drift_diffusion_not_ml"
    assert "OGHMANANO_IS_DEVICE_PHYSICS_NOT_ML" in result.flags
    assert (phase_dir / "14_oghma_device" / "method_comparison.html").exists()
    stack = json.loads((phase_dir / "14_oghma_device" / "device_stack.json").read_text())
    absorber = [layer for layer in stack["layers"] if layer["role"] == "absorber"][0]
    assert absorber["bandgap_eV"] == 1.58
    assert absorber["thickness_nm"] == 500.0


def test_debug_power_curve_is_signed_not_clipped():
    module = _load_debug_outputs_module()
    voltage = np.array([0.0, 0.7, 0.9, 1.0])
    current_a_m2 = np.array([-200.0, -180.0, 0.0, 50.0])

    power_mw_cm2 = module._pv_power_mw_cm2(voltage, current_a_m2)
    pv_voltage, pv_power = module._pv_quadrant_power_mw_cm2(voltage, current_a_m2)

    assert np.allclose(power_mw_cm2, [0.0, 12.6, 0.0, -5.0])
    assert np.allclose(pv_voltage, [0.0, 0.7, 0.9])
    assert np.allclose(pv_power, [0.0, 12.6, 0.0])


def test_oghma_sim_info_parser(tmp_path):
    sim_info = tmp_path / "sim_info.dat"
    sim_info.write_text(json.dumps({"pce": 18.5, "ff": 0.82, "voc": 1.02, "jsc": 22.1}))

    parsed = parse_oghma_sim_info(sim_info)

    assert parsed["pce_pct"] == 18.5
    assert parsed["ff"] == 0.82
    assert parsed["voc_V"] == 1.02
    assert parsed["jsc_mA_cm2"] == 22.1


def test_oghma_sim_info_parser_converts_summary_a_m2_by_pce(tmp_path):
    sim_info = tmp_path / "sim_info.dat"
    sim_info.write_text(json.dumps({
        "pce": 5.340069,
        "ff": 0.800864,
        "voc": 0.8814283,
        "jsc": -75.64863,
    }))

    parsed = parse_oghma_sim_info(sim_info)

    assert abs(parsed["jsc_mA_cm2"] + 7.564863) < 1e-5


def test_oghma_stack_uses_config_override(tmp_path):
    stack = build_device_stack_from_dft(
        tmp_path,
        phase="alpha",
        config={"absorber_thickness_nm": 350.0, "absorber_bandgap_eV": 1.4},
    )

    absorber = [layer for layer in stack["layers"] if layer["role"] == "absorber"][0]
    assert absorber["thickness_nm"] == 350.0
    assert absorber["bandgap_eV"] == 1.4


def test_bandgap_absorption_onset_adds_urbach_tail():
    energy = np.array([1.0, 1.5, 1.7, 2.0])
    k = np.array([0.2, 0.1, 0.3, 0.4])

    corrected = _apply_bandgap_absorption_onset(energy, k, eg_eV=1.5858)

    assert corrected[0] > 0.0
    assert corrected[1] > corrected[0]
    assert corrected[1] < corrected[2]
    assert corrected[2:].tolist() == [0.3, 0.4]


def test_oghma_worker_command_uses_xvfb_and_worker_args(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    cmd = build_oghma_worker_command(
        "/usr/lib/oghma_core/oghma_core.exe",
        {"simmode": "segment0@jv", "lockfile": r"S:\lock0.dat"},
    )

    assert cmd[:3] == ["xvfb-run", "-a", "--"]
    assert cmd[3:5] == ["wine", "/usr/lib/oghma_core/oghma_core.exe"]
    assert "S:\\" in cmd
    assert "--simmode" in cmd
    assert "segment0@jv" in cmd
    assert "--lockfile" in cmd
    assert r"S:\lock0.dat" in cmd
    assert "DISPLAY" not in _wine_env()


def test_oghma_worker_command_uses_native_windows_paths(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")

    cmd = build_oghma_worker_command(
        r"C:\Program Files (x86)\OghmaNano\oghma_core.exe",
        {
            "sim_root_path": r"C:\tmp\oghma\sim",
            "simmode": "segment0@jv",
            "lockfile": r"C:\tmp\oghma\sim\lock0.dat",
        },
    )

    assert cmd[0] == r"C:\Program Files (x86)\OghmaNano\oghma_core.exe"
    assert "xvfb-run" not in cmd
    assert "wine" not in cmd
    assert "--sim-root-path" in cmd
    assert r"C:\tmp\oghma\sim" in cmd
    assert r"C:\tmp\oghma\sim\lock0.dat" in cmd
    assert _wine_env() == {}


def test_oghma_sim_writer_fast_mode_writes_json_inp(monkeypatch, tmp_path):
    from dft_cspbi3.analysis import oghma_device

    monkeypatch.setattr(oghma_device, "_get_perovskite_template", oghma_device._minimal_perovskite_template)
    stack = build_device_stack_from_dft(
        tmp_path,
        phase="alpha",
        config={"absorber_thickness_nm": 500.0, "absorber_bandgap_eV": 1.58},
    )

    write_oghma_sim_dir(
        tmp_path / "sim",
        stack,
        tmp_path,
        config={
            "fast_mode": True,
            "fast_vstep": 0.01,
            "jv_vstop": 1.2,
            "fast_ion_density": 0.0,
            "electrical_mesh_points": 120,
            "solver_max_iterations": 500,
            "solver_ramp_iterations": 500,
        },
    )

    data = json.loads((tmp_path / "sim" / "json.inp").read_text())
    assert (tmp_path / "sim" / "sim.json").exists()
    assert (tmp_path / "sim" / "materials" / "data.json").exists()
    assert (tmp_path / "sim" / "materials" / "CsPbI3" / "data.json").exists()
    assert (tmp_path / "sim" / "materials" / "CsPbI3" / "n.csv").exists()
    assert (tmp_path / "sim" / "materials" / "CsPbI3" / "alpha.csv").exists()
    assert (tmp_path / "sim" / "materials" / "CsPbI3" / "nk.csv").exists()
    segment0 = data["sims"]["jv"]["segment0"]
    if "config" in segment0:
        assert segment0["config"]["Vstep"] == 0.01
        assert segment0["config"]["Vstop"] == 1.2
    else:
        assert segment0["Vstep"] == 0.01
        assert segment0["Vstop"] == 1.2
    mesh_y = data.get("electrical_solver", {}).get("mesh", {}).get("mesh_y")
    if mesh_y is None:
        mesh_y = data["mesh"]["mesh_y"]
    assert mesh_y["segment0"]["points"] == 120
    assert data["math"]["max_newton_iterations"] == 500
    assert data["math"]["maxelectricalitt"] == 500
    assert data["math"]["maxelectricalitt_ramp"] == 500
    assert data["epitaxy"]["segment2"]["shape_dos"]["ion_density"] == 0.0


def test_oghma_local_links_add_material_overlay(tmp_path):
    root = tmp_path / "oghma_local"
    overlay = tmp_path / "sim" / "materials"
    (overlay / "CsPbI3").mkdir(parents=True)
    (overlay / "CsPbI3" / "n.csv").write_text("n")

    ensure_oghma_local_links(root, materials_overlay=overlay)

    assert (root / "materials").is_dir()
    assert (root / "materials" / "CsPbI3" / "n.csv").read_text() == "n"


def test_extract_oghma_error_from_html_log():
    text = "<font>error:There is a shape (Au) covering the electrical mesh</font>"

    assert _extract_oghma_error(text) == "error:There is a shape (Au) covering the electrical mesh"
