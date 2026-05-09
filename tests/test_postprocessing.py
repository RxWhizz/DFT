"""Test técnico."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# Fixtures

@pytest.fixture(autouse=True)
def patch_gpaw_imports(monkeypatch):
    """Parchea gpaw; importa sin GPAW."""
    gpaw_mock = MagicMock()
    spinorbit_mock = MagicMock()
    ase_dos_mock = MagicMock()

    monkeypatch.setitem(sys.modules, "gpaw", gpaw_mock)
    monkeypatch.setitem(sys.modules, "gpaw.spinorbit", spinorbit_mock)
    monkeypatch.setitem(sys.modules, "ase.dft.dos", ase_dos_mock)
    return {"gpaw": gpaw_mock, "spinorbit": spinorbit_mock, "ase_dos": ase_dos_mock}


def _make_mock_calc(
    homo: float = -0.2,
    lumo: float = 1.3,
    fermi: float = 0.55,
    total_energy: float = -100.0,
    natoms: int = 5,
    symbols: list | None = None,
):
    """Devuelve calculadora GPAW mock."""
    symbols = symbols or ["Cs", "Pb", "I", "I", "I"]
    atoms_mock = MagicMock()
    atoms_mock.get_chemical_symbols.return_value = symbols
    atoms_mock.__len__ = MagicMock(return_value=natoms)
    atoms_mock.get_volume.return_value = float(6.18**3)
    atoms_mock.get_chemical_formula.return_value = "CsPbI3"

    calc = MagicMock()
    calc.get_homo_lumo.return_value = (homo, lumo)
    calc.get_fermi_level.return_value = fermi
    calc.get_potential_energy.return_value = total_energy
    calc.get_atoms.return_value = atoms_mock
    calc.get_number_of_electrons.return_value = natoms * 2
    return calc


# Tests para get_bandgap

class TestGetBandgap:
    def test_returns_lumo_minus_homo(self, patch_gpaw_imports):
        from dft_cspbi3 import postprocessing as pp

        mock_calc = _make_mock_calc(homo=-0.1, lumo=1.6)
        patch_gpaw_imports["gpaw"].GPAW.return_value = mock_calc

        gap = pp.get_bandgap("dummy.gpw", soc=False)
        assert pytest.approx(gap) == 1.7

    def test_gap_is_float(self, patch_gpaw_imports):
        from dft_cspbi3 import postprocessing as pp

        mock_calc = _make_mock_calc(homo=-0.2, lumo=1.3)
        patch_gpaw_imports["gpaw"].GPAW.return_value = mock_calc

        gap = pp.get_bandgap("dummy.gpw")
        assert isinstance(gap, float)

    def test_gap_positive_for_semiconductor(self, patch_gpaw_imports):
        from dft_cspbi3 import postprocessing as pp

        mock_calc = _make_mock_calc(homo=-0.5, lumo=1.2)
        patch_gpaw_imports["gpaw"].GPAW.return_value = mock_calc

        gap = pp.get_bandgap("dummy.gpw")
        assert gap > 0


# Tests para get_soc_bandgap

class TestGetSOCBandgap:
    def test_soc_gap_from_eigenvalues(self, patch_gpaw_imports):
        from dft_cspbi3 import postprocessing as pp

        nkpts, nbands = 8, 10
        e_kn = np.zeros((nkpts, nbands))
        # Fill
        e_kn[:, :4] = -1.0
        e_kn[:, 4:] = 1.5  # cbm = 1.5, vbm = -1.0, gap = 2.5

        mock_calc = _make_mock_calc()
        mock_calc.get_fermi_level.return_value = 0.0
        mock_calc.get_number_of_electrons.return_value = 8  # 4 bands × 2

        patch_gpaw_imports["gpaw"].GPAW.return_value = mock_calc
        patch_gpaw_imports["spinorbit"].spinorbit_eigenvalues.return_value = (e_kn, np.zeros_like(e_kn))

        gap = pp.get_soc_bandgap("dummy.gpw")
        # With 8 electrons → nelectrons = 8, occupied[:8], unoccupied[8:]
        # e_kn shape (8,10)
        # vbm = max occupied = -1.0, cbm = min unoccupied =
        # This tests that function runs y returns float
        assert isinstance(gap, float)


# Tests para get_fermi_level y get_total_energy

class TestScalarExtractors:
    def test_fermi_level(self, patch_gpaw_imports):
        from dft_cspbi3 import postprocessing as pp

        mock_calc = _make_mock_calc(fermi=0.75)
        patch_gpaw_imports["gpaw"].GPAW.return_value = mock_calc

        ef = pp.get_fermi_level("dummy.gpw")
        assert pytest.approx(ef) == 0.75

    def test_total_energy(self, patch_gpaw_imports):
        from dft_cspbi3 import postprocessing as pp

        mock_calc = _make_mock_calc(total_energy=-123.456)
        patch_gpaw_imports["gpaw"].GPAW.return_value = mock_calc

        e = pp.get_total_energy("dummy.gpw")
        assert pytest.approx(e) == -123.456

    def test_homo_lumo_tuple(self, patch_gpaw_imports):
        from dft_cspbi3 import postprocessing as pp

        mock_calc = _make_mock_calc(homo=-0.3, lumo=1.4)
        patch_gpaw_imports["gpaw"].GPAW.return_value = mock_calc

        homo, lumo = pp.get_homo_lumo("dummy.gpw")
        assert pytest.approx(homo) == -0.3
        assert pytest.approx(lumo) == 1.4


# Tests para extract_summary

class TestExtractSummary:
    def test_summary_keys(self, patch_gpaw_imports):
        from dft_cspbi3 import postprocessing as pp

        mock_calc = _make_mock_calc()
        patch_gpaw_imports["gpaw"].GPAW.return_value = mock_calc

        summary = pp.extract_summary("dummy.gpw")
        for key in ("formula", "natoms", "total_energy_eV", "fermi_level_eV", "bandgap_eV"):
            assert key in summary, f"Missing key: {key}"

    def test_summary_natoms(self, patch_gpaw_imports):
        from dft_cspbi3 import postprocessing as pp

        mock_calc = _make_mock_calc(natoms=5)
        patch_gpaw_imports["gpaw"].GPAW.return_value = mock_calc

        summary = pp.extract_summary("dummy.gpw")
        assert summary["natoms"] == 5

    def test_summary_bandgap(self, patch_gpaw_imports):
        from dft_cspbi3 import postprocessing as pp

        mock_calc = _make_mock_calc(homo=-0.1, lumo=1.62)
        patch_gpaw_imports["gpaw"].GPAW.return_value = mock_calc

        summary = pp.extract_summary("dummy.gpw")
        assert pytest.approx(summary["bandgap_eV"], abs=1e-4) == 1.72

    def test_summary_formula(self, patch_gpaw_imports):
        from dft_cspbi3 import postprocessing as pp

        mock_calc = _make_mock_calc()
        patch_gpaw_imports["gpaw"].GPAW.return_value = mock_calc

        summary = pp.extract_summary("dummy.gpw")
        assert summary["formula"] == "CsPbI3"
