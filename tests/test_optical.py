import importlib.util
import sys
from pathlib import Path

import numpy as np

_OPTICAL_PATH = Path(__file__).resolve().parents[1] / "src" / "dft_cspbi3" / "analysis" / "optical.py"
_spec = importlib.util.spec_from_file_location("_optical_test_import", _OPTICAL_PATH)
assert _spec and _spec.loader
_optical = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _optical
_spec.loader.exec_module(_optical)

_absorption_from_k = _optical._absorption_from_k
_apply_onset_override = _optical._apply_onset_override
compute_optical_spectrum = _optical.compute_optical_spectrum
load_optical_result = _optical.load_optical_result


def test_apply_onset_override_adds_urbach_tail():
    omega = np.array([1.0, 1.5, 1.6, 2.0])
    k = np.array([0.2, 0.1, 0.3, 0.4])

    corrected = _apply_onset_override(omega, k, 1.5858, urbach_energy_meV=25.0)

    assert corrected[0] > 0.0
    assert corrected[1] > corrected[0]
    assert corrected[1] < corrected[2]
    assert corrected[2:].tolist() == [0.3, 0.4]


def test_absorption_from_k_units_are_cm_inverse():
    omega = np.array([2.0])
    k = np.array([0.1])

    alpha = _absorption_from_k(omega, k)

    wavelength_cm = 1.239841984e-4 / 2.0
    assert np.isclose(alpha[0], 4.0 * np.pi * 0.1 / wavelength_cm)


def test_compute_optical_spectrum_reuses_csv_and_writes_required_npy(tmp_path: Path):
    omega = np.array([0.0, 1.0, 1.5, 1.6, 2.0])
    eps1 = np.full_like(omega, 4.0)
    eps2 = np.array([0.0, 0.3, 0.3, 0.3, 0.3])
    data = np.column_stack([omega, eps1, eps2, eps1, eps2])
    np.savetxt(tmp_path / "dielectric_function.csv", data, delimiter=",")

    result = compute_optical_spectrum(
        tmp_path / "unused.gpw",
        tmp_path,
        omega_max_eV=2.0,
        d_omega_eV=0.5,
        onset_eV_override=1.5858,
    )

    for name in (
        "optical_frequencies.npy",
        "eps1.npy",
        "eps2.npy",
        "n_omega.npy",
        "k_omega.npy",
        "absorption_cm1.npy",
    ):
        assert (tmp_path / name).exists()

    assert "FROM_CSV" in result.flags
    assert any(flag.startswith("ONSET_OVERRIDE:") for flag in result.flags)
    assert "URBACH_TAIL:25.0meV" in result.flags
    subgap = result.frequencies_eV < 1.5858
    assert np.any(result.k_omega[subgap] > 0.0)
    assert np.any(result.absorption_cm1[subgap] > 0.0)
    assert result.absorption_cm1[result.frequencies_eV == 1.5][0] < result.absorption_cm1[result.frequencies_eV == 2.0][0]
    assert np.any(result.absorption_cm1[result.frequencies_eV >= 1.5858] > 0.0)

    loaded = load_optical_result(tmp_path)
    assert loaded is not None
    assert loaded.n_omega.shape == loaded.k_omega.shape == loaded.frequencies_eV.shape
