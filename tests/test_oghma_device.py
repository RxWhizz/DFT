import json

from dft_cspbi3.analysis.oghma_device import (
    build_device_stack_from_dft,
    parse_oghma_sim_info,
    prepare_oghma_device_step,
)


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


def test_oghma_sim_info_parser(tmp_path):
    sim_info = tmp_path / "sim_info.dat"
    sim_info.write_text(json.dumps({"pce": 18.5, "ff": 0.82, "voc": 1.02, "jsc": 22.1}))

    parsed = parse_oghma_sim_info(sim_info)

    assert parsed["pce_pct"] == 18.5
    assert parsed["ff"] == 0.82
    assert parsed["voc_V"] == 1.02
    assert parsed["jsc_mA_cm2"] == 22.1


def test_oghma_stack_uses_config_override(tmp_path):
    stack = build_device_stack_from_dft(
        tmp_path,
        phase="alpha",
        config={"absorber_thickness_nm": 350.0, "absorber_bandgap_eV": 1.4},
    )

    absorber = [layer for layer in stack["layers"] if layer["role"] == "absorber"][0]
    assert absorber["thickness_nm"] == 350.0
    assert absorber["bandgap_eV"] == 1.4
