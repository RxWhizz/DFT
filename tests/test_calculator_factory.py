"""Tests GPAWCalculatorFactory; valida parámetros sin GPAW."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

CONFIG_PATH = Path(__file__).parent.parent / "configs" / "default_params.yaml"


def _load_config():
    with open(CONFIG_PATH) as fh:
        return yaml.safe_load(fh)


# Fixtures

@pytest.fixture
def mock_gpaw_module(monkeypatch):
    """Parchea gpaw; importa sin GPAW."""
    gpaw_mock = MagicMock()
    gpaw_mock.GPAW = MagicMock(side_effect=lambda **kwargs: MagicMock(_kwargs=kwargs))
    gpaw_mock.Mixer = MagicMock(side_effect=lambda **kwargs: MagicMock(_kwargs=kwargs))
    gpaw_mock.PW = MagicMock(side_effect=lambda ecut: MagicMock(_ecut=ecut))
    monkeypatch.setitem(sys.modules, "gpaw", gpaw_mock)
    monkeypatch.setitem(sys.modules, "gpaw.spinorbit", MagicMock())
    return gpaw_mock


@pytest.fixture
def factory(mock_gpaw_module):
    # Import after patching
    from dft_cspbi3.calculator_factory import GPAWCalculatorFactory
    return GPAWCalculatorFactory(CONFIG_PATH)


@pytest.fixture
def alpha_atoms():
    from dft_cspbi3.structure_builder import StructureBuilder
    return StructureBuilder.build_alpha()


# Config loading

class TestConfigLoading:
    def test_config_loaded(self, factory):
        cfg = factory.config
        assert "relax" in cfg
        assert "scf" in cfg
        assert "bands" in cfg
        assert "hse06" in cfg

    def test_paw_datasets(self, factory):
        paw = factory.config["paw_datasets"]
        assert paw["Cs"] == "Cs.9.PBE"
        assert paw["Pb"] == "Pb.14.PBE"
        assert paw["I"] == "I.7.PBE"

    def test_ecut_value(self, factory):
        assert factory.config["cutoff"]["pw_ecut"] == 450

    def test_convergence_range(self, factory):
        cr = factory.config["cutoff"]["convergence_range"]
        assert 300 in cr
        assert 550 in cr


# Calculator creation

class TestRelaxCalc:
    def test_returns_gpaw_object(self, factory, mock_gpaw_module):
        calc = factory.create("relax")
        assert calc is not None
        mock_gpaw_module.GPAW.assert_called_once()

    def test_xc_is_pbesol(self, factory, mock_gpaw_module):
        factory.create("relax")
        kwargs = mock_gpaw_module.GPAW.call_args.kwargs
        assert kwargs["xc"] == "PBEsol"

    def test_ecut_is_pw_mode(self, factory, mock_gpaw_module):
        factory.create("relax")
        kwargs = mock_gpaw_module.GPAW.call_args.kwargs
        # PW(450) debe have been llamado
        mock_gpaw_module.PW.assert_called_with(450)

    def test_kpoints(self, factory, mock_gpaw_module):
        factory.create("relax")
        kwargs = mock_gpaw_module.GPAW.call_args.kwargs
        assert kwargs["kpts"]["size"] == [6, 6, 6]
        assert kwargs["kpts"]["gamma"] is True

    def test_mixer_beta(self, factory, mock_gpaw_module):
        factory.create("relax")
        # Mixer debe have been construido con beta=0.05
        mock_gpaw_module.Mixer.assert_called_with(beta=0.05, nmaxold=5, weight=50.0)

    def test_maxiter(self, factory, mock_gpaw_module):
        factory.create("relax")
        kwargs = mock_gpaw_module.GPAW.call_args.kwargs
        assert kwargs["maxiter"] == 333


class TestSCFCalc:
    def test_energy_convergence(self, factory, mock_gpaw_module):
        factory.create("scf")
        kwargs = mock_gpaw_module.GPAW.call_args.kwargs
        assert kwargs["convergence"]["energy"] == pytest.approx(1e-8)

    def test_fermi_dirac_smearing(self, factory, mock_gpaw_module):
        factory.create("scf")
        kwargs = mock_gpaw_module.GPAW.call_args.kwargs
        assert kwargs["occupations"]["name"] == "fermi-dirac"
        assert kwargs["occupations"]["width"] == pytest.approx(0.05)


class TestBandsCalc:
    def test_requires_atoms(self, factory):
        with pytest.raises(ValueError, match="atoms must be provided"):
            factory.create("bands", atoms=None)

    def test_fixdensity_true(self, factory, mock_gpaw_module, alpha_atoms):
        factory.create("bands", atoms=alpha_atoms)
        kwargs = mock_gpaw_module.GPAW.call_args.kwargs
        assert kwargs["fixdensity"] is True

    def test_symmetry_off(self, factory, mock_gpaw_module, alpha_atoms):
        factory.create("bands", atoms=alpha_atoms)
        kwargs = mock_gpaw_module.GPAW.call_args.kwargs
        assert kwargs["symmetry"] == "off"


class TestHSE06Calc:
    def test_xc_dict(self, factory, mock_gpaw_module):
        factory.create("hse06")
        kwargs = mock_gpaw_module.GPAW.call_args.kwargs
        assert isinstance(kwargs["xc"], dict)
        assert kwargs["xc"]["name"] == "HSE06"

    def test_omega_value(self, factory, mock_gpaw_module):
        """HSE06 screening parámetro omega = 0.11 Bohr⁻¹."""
        factory.create("hse06")
        kwargs = mock_gpaw_module.GPAW.call_args.kwargs
        assert kwargs["xc"]["omega"] == pytest.approx(0.11)

    def test_reduced_kpoints(self, factory, mock_gpaw_module):
        """HSE06 usa 4×4×4 k-mesh reduce O(N³) cost."""
        factory.create("hse06")
        kwargs = mock_gpaw_module.GPAW.call_args.kwargs
        assert kwargs["kpts"]["size"] == [4, 4, 4]


class TestParamsOverride:
    def test_override_applied(self, factory, mock_gpaw_module):
        factory.create("relax", params_override={"maxiter": 999})
        kwargs = mock_gpaw_module.GPAW.call_args.kwargs
        assert kwargs["maxiter"] == 999

    def test_invalid_calc_type(self, factory):
        with pytest.raises(ValueError, match="Unknown calc_type"):
            factory.create("invalid_type")


class TestPAWSetups:
    def test_setups_included(self, factory, mock_gpaw_module):
        factory.create("scf")
        kwargs = mock_gpaw_module.GPAW.call_args.kwargs
        assert "setups" in kwargs
        assert kwargs["setups"]["Cs"] == "Cs.9.PBE"
        assert kwargs["setups"]["Pb"] == "Pb.14.PBE"
        assert kwargs["setups"]["I"] == "I.7.PBE"

    def test_parallel_domain(self, factory, mock_gpaw_module):
        factory.create("scf")
        kwargs = mock_gpaw_module.GPAW.call_args.kwargs
        assert kwargs["parallel"]["domain"] == 1
