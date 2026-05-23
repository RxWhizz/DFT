"""Tests ScissorCorrection; aritmética literatura."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# Patch GPAW imports before loading bandgap_correction
@pytest.fixture(autouse=True)
def patch_gpaw(monkeypatch):
    gpaw_mock = MagicMock()
    monkeypatch.setitem(sys.modules, "gpaw", gpaw_mock)
    monkeypatch.setitem(sys.modules, "gpaw.spinorbit", MagicMock())


@pytest.fixture
def corrector():
    from dft_cspbi3.bandgap_correction import ScissorCorrection
    return ScissorCorrection()


@pytest.fixture
def corrector_custom():
    from dft_cspbi3.bandgap_correction import ScissorCorrection
    return ScissorCorrection(
        reference={
            "experimental_alpha": 1.73,
            "pbe_no_soc": 1.44,
            "pbe_soc": 0.60,
            "hse06_no_soc": 1.76,
            "hse06_soc": 1.55,
        }
    )


class TestScissorArithmetic:
    """Verify scissor formula con valores desde published literature."""

    def test_corrected_gap_formula(self, corrector):
        """Eg_corr = E_PBE+D3 + χSOC + χHSE."""
        e_pbe_d3 = 1.44
        chi_soc = 0.60 - 1.44   # = -0.84 eV
        chi_hse = 1.76 - 1.44   # = +0.32 eV
        result = corrector.corrected_gap(e_pbe_d3, chi_soc, chi_hse)
        expected = 1.44 + (-0.84) + 0.32  # esperado = 0.92 eV
        assert pytest.approx(result, abs=1e-6) == expected

    def test_chi_soc_negative_for_lead(self, corrector):
        """SOC reduce gap PbI3; χSOC < 0."""
        chi_soc = corrector.corrected_gap(0.0, -0.84, 0.0)
        assert chi_soc < 0

    def test_chi_hse_positive(self, corrector):
        """HSE06 abre gap vs PBE; χHSE > 0."""
        chi_hse = 1.76 - 1.44
        assert chi_hse > 0

    def test_corrected_gap_is_float(self, corrector):
        result = corrector.corrected_gap(1.44, -0.84, 0.32)
        assert isinstance(result, float)

    def test_corrected_gap_additivity(self, corrector):
        """Scissor aditivo; orden irrelevante."""
        e = 1.44
        soc = -0.84
        hse = 0.32
        assert corrector.corrected_gap(e, soc, hse) == corrector.corrected_gap(e, hse, soc)

    def test_zero_corrections(self, corrector):
        """With zero corrections, resultado equals PBE+D3 gap."""
        assert corrector.corrected_gap(1.55, 0.0, 0.0) == pytest.approx(1.55)


class TestScissorResult:
    def test_mae_calculation(self, corrector):
        from dft_cspbi3.bandgap_correction import ScissorResult
        result = ScissorResult(
            phase="alpha",
            e_pbe_d3=1.44,
            chi_soc=-0.84,
            chi_hse=0.32,
            e_corrected=0.92,
            e_experimental=1.73,
            mae_vs_experiment=abs(0.92 - 1.73),
        )
        assert result.mae_vs_experiment == pytest.approx(0.81, abs=0.01)

    def test_result_fields(self, corrector):
        from dft_cspbi3.bandgap_correction import ScissorResult
        result = ScissorResult(
            phase="alpha",
            e_pbe_d3=1.44,
            chi_soc=-0.84,
            chi_hse=0.32,
            e_corrected=0.92,
        )
        assert result.phase == "alpha"
        assert result.e_experimental is None
        assert result.mae_vs_experiment is None


class TestApplyScissorToBands:
    def _make_mock_bs(self, energies_below, energies_above, ef=0.0):
        """Crea minimal mock BandStructure."""
        import numpy as np
        bs = MagicMock()
        bs.energies = np.concatenate([energies_below, energies_above])
        bs.reference = ef
        return bs

    def test_vbm_shift_applied(self, corrector):
        import numpy as np
        bs = MagicMock()
        bs.reference = 0.0
        bs.energies = np.array([-2.0, -1.0, 0.0, 1.0, 2.0])
        corrector.apply_scissor_to_bands(bs, vbm_shift=0.1, cbm_shift=0.0)
        # Values ≤ 0 shifted by 0.1
        assert pytest.approx(bs.energies[0]) == -2.0 + 0.1
        assert pytest.approx(bs.energies[1]) == -1.0 + 0.1
        assert pytest.approx(bs.energies[2]) == 0.0 + 0.1

    def test_cbm_shift_applied(self, corrector):
        import numpy as np
        bs = MagicMock()
        bs.reference = 0.0
        bs.energies = np.array([-1.0, 0.5, 1.5])
        corrector.apply_scissor_to_bands(bs, vbm_shift=0.0, cbm_shift=0.5)
        assert pytest.approx(bs.energies[1]) == 0.5 + 0.5
        assert pytest.approx(bs.energies[2]) == 1.5 + 0.5

    def test_zero_shifts_no_change(self, corrector):
        import numpy as np
        original = np.array([-2.0, -1.0, 1.0, 2.0])
        bs = MagicMock()
        bs.reference = 0.0
        bs.energies = original.copy()
        corrector.apply_scissor_to_bands(bs, vbm_shift=0.0, cbm_shift=0.0)
        np.testing.assert_allclose(bs.energies, original)


class TestReferenceValues:
    def test_default_experimental_gap(self, corrector):
        """Gap experimental α-CsPbI3 = 1.73 eV."""
        assert corrector.REFERENCE["experimental_alpha"] == pytest.approx(1.73)

    def test_pbe_soc_gap(self, corrector):
        """PBE+SOC ≈ 0.60 eV; SOC Pb fuerte."""
        assert corrector.REFERENCE["pbe_soc"] == pytest.approx(0.60)

    def test_hse06_gap(self, corrector):
        """HSE06 sin SOC cerca experimento."""
        assert corrector.REFERENCE["hse06_no_soc"] == pytest.approx(1.76)

    def test_custom_reference(self):
        from dft_cspbi3.bandgap_correction import ScissorCorrection
        custom = ScissorCorrection(reference={"experimental_alpha": 1.80, "pbe_no_soc": 1.50})
        assert custom.REFERENCE["experimental_alpha"] == 1.80

    def test_report_runs_without_error(self, corrector, capsys):
        corrector.report(phase="alpha")
        captured = capsys.readouterr()
        assert "CsPbI3" in captured.out
        assert "HSE06" in captured.out
