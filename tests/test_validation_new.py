"""Tests validación/reporting sin GPAW."""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import numpy as np


def _build_mocks():
    """Inject minimal but completo gpaw + ase stubs into sys.modules."""

    # ASE Atoms stub
    class _Atoms:
        def __init__(self, *a, **kw):
            self._pos = np.zeros((5, 3))
            self._masses = np.array([132.9, 207.2, 126.9, 126.9, 126.9])
        def get_chemical_formula(self): return "CsPbI3"
        def __len__(self): return 5
        def get_volume(self): return 236.7
        def get_positions(self): return self._pos.copy()
        def set_positions(self, p): self._pos = np.array(p)
        def get_masses(self): return self._masses.copy()
        def get_forces(self): return np.zeros((5, 3))
        def get_atomic_numbers(self): return np.array([55, 82, 53, 53, 53])
        def get_chemical_symbols(self): return ["Cs", "Pb", "I", "I", "I"]
        def get_magnetic_moment(self): return 0.0
        def get_occupation_numbers(self): return np.ones(44)
        def copy(self): return self
        @property
        def calc(self): return self._calc if hasattr(self, "_calc") else None
        @calc.setter
        def calc(self, v): self._calc = v
        def get_potential_energy(self): return -100.0

    # ASE
    def _pkg(name, **attrs):
        """Crea fake package (module con __path__ so sub-imports trabajo)."""
        m = types.ModuleType(name)
        m.__path__ = []
        m.__package__ = name
        for k, v in attrs.items():
            setattr(m, k, v)
        return m

    ase_mod = _pkg("ase", Atoms=_Atoms)
    ase_io          = _pkg("ase.io",
                           read=MagicMock(return_value=_Atoms()),
                           write=MagicMock())
    ase_opt         = _pkg("ase.optimize", BFGS=MagicMock())
    ase_dft         = _pkg("ase.dft")
    ase_dft_kpoints = _pkg("ase.dft.kpoints", bandpath=MagicMock())
    ase_dft_dos     = _pkg("ase.dft.dos", DOS=MagicMock())
    ase_phonons_mod = _pkg("ase.phonons", Phonons=MagicMock())
    ase_vibrations_mod = _pkg("ase.vibrations", Vibrations=MagicMock())
    ase_build       = _pkg("ase.build",
                           make_supercell=MagicMock(return_value=_Atoms()),
                           crystal=MagicMock(return_value=_Atoms()))
    ase_spacegroup  = _pkg("ase.spacegroup",
                           crystal=MagicMock(return_value=_Atoms()))
    ase_atoms_mod   = _pkg("ase.atoms", Atoms=_Atoms)
    ase_units       = _pkg("ase.units", Bohr=0.529177)

    for mod_name, mod in [
        ("ase",              ase_mod),
        ("ase.atoms",        ase_atoms_mod),
        ("ase.io",           ase_io),
        ("ase.optimize",     ase_opt),
        ("ase.dft",          ase_dft),
        ("ase.dft.kpoints",  ase_dft_kpoints),
        ("ase.dft.dos",      ase_dft_dos),
        ("ase.phonons",      ase_phonons_mod),
        ("ase.vibrations",   ase_vibrations_mod),
        ("ase.build",        ase_build),
        ("ase.spacegroup",   ase_spacegroup),
        ("ase.units",        ase_units),
    ]:
        sys.modules[mod_name] = mod

    # GPAW stubs
    class _PW:
        def __init__(self, ecut): self.ecut = ecut

    class _Mixer:
        def __init__(self, **kw): pass

    class _GPAW:
        def __init__(self, *a, **kw): pass
        def get_potential_energy(self): return -100.0
        def get_fermi_level(self): return 1.5
        def get_number_of_electrons(self): return 44.0
        def get_homo_lumo(self): return (1.0, 2.44)
        def get_atoms(self): return _Atoms()
        def get_occupation_numbers(self): return np.ones(44)
        def get_magnetic_moment(self): return 0.0
        def get_eigenvalues(self, kpt=0): return np.linspace(-5, 5, 22)
        def write(self, path): pass
        def __del__(self): pass

    gpaw_mod = types.ModuleType("gpaw")
    gpaw_mod.GPAW = _GPAW
    gpaw_mod.PW = _PW
    gpaw_mod.Mixer = _Mixer
    spinorbit_mod = types.ModuleType("gpaw.spinorbit")
    spinorbit_mod.spinorbit_eigenvalues = MagicMock(
        return_value=(np.linspace(-5, 5, 88).reshape(1, 88), np.ones((1, 88)) * 0.1)
    )
    sys.modules.setdefault("gpaw", gpaw_mod)
    sys.modules.setdefault("gpaw.spinorbit", spinorbit_mod)

    # Other heavy deps
    pandas_mod = types.ModuleType("pandas")
    pandas_mod.DataFrame = MagicMock
    sys.modules.setdefault("pandas", pandas_mod)

    yaml_mod = types.ModuleType("yaml")
    yaml_mod.safe_load = MagicMock(return_value={
        "relax": {"ecut": 450, "xc": "PBEsol", "kpts": [6,6,6],
                  "convergence": {"energy": 1e-6, "forces": 0.01},
                  "mixer": {"beta": 0.05}, "maxiter": 333, "symmetry": "on"},
        "scf": {"ecut": 450, "xc": "PBEsol", "kpts": [6,6,6],
                "convergence": {"energy": 1e-8},
                "occupations": {"name": "fermi-dirac", "width": 0.05}},
        "bands": {"kpts_path": "XRMGR", "npoints": 40,
                  "convergence": {"bands": -10}},
        "dos": {"kpts": [12,12,12]},
        "soc": {"mode": "perturbative", "theta": 0, "phi": 0},
        "hse06": {"ecut": 450, "kpts": [4,4,4], "convergence": {"energy": 1e-6}},
        "paw_datasets": {"Cs": "Cs.9.PBE", "Pb": "Pb.14.PBE", "I": "I.7.PBE"},
        "cutoff": {"pw_ecut": 450, "convergence_range": [300, 350, 400, 450, 500]},
    })
    sys.modules.setdefault("yaml", yaml_mod)

    scipy_mod = types.ModuleType("scipy")
    sys.modules.setdefault("scipy", scipy_mod)
    sys.modules.setdefault("scipy.linalg", types.ModuleType("scipy.linalg"))
    sys.modules.setdefault("matplotlib", types.ModuleType("matplotlib"))
    sys.modules.setdefault("matplotlib.pyplot", types.ModuleType("matplotlib.pyplot"))
    sys.modules.setdefault("click", types.ModuleType("click"))


_build_mocks()

BASE = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(BASE))


# Tests

class TestStabilityClass(unittest.TestCase):

    def setUp(self):
        from dft_cspbi3.validation.stability import (
            StabilityClass, classify_from_phonons, classify_from_hessian,
            classify_combined, StabilityReport,
        )
        self.StabilityClass = StabilityClass
        self.classify_from_phonons = classify_from_phonons
        self.classify_from_hessian = classify_from_hessian
        self.classify_combined = classify_combined

    def _make_phonon_result(self, n_imaginary, max_imag_cm1):
        r = MagicMock()
        r.n_imaginary = n_imaginary
        r.max_imaginary_cm1 = max_imag_cm1
        r.frequencies_cm1 = np.array([max_imag_cm1, 50.0, 100.0, 200.0])
        r.flags = []
        return r

    def _make_hessian_result(self, n_negative, min_eigval):
        r = MagicMock()
        r.n_negative = n_negative
        r.min_eigenvalue = min_eigval
        r.stable = (n_negative == 0)
        r.flags = []
        return r

    def test_stable_phonons(self):
        ph = self._make_phonon_result(0, 5.0)  # 5 cm⁻¹ < umbral
        report = self.classify_from_phonons(ph)
        self.assertEqual(report.classification, self.StabilityClass.STABLE)

    def test_metastable_phonons(self):
        ph = self._make_phonon_result(2, -50.0)  # 50 cm⁻¹ < 100 umbral
        report = self.classify_from_phonons(ph)
        self.assertEqual(report.classification, self.StabilityClass.METASTABLE)

    def test_unstable_phonons(self):
        ph = self._make_phonon_result(3, -150.0)  # 150 cm⁻¹ > 100 umbral
        report = self.classify_from_phonons(ph)
        self.assertEqual(report.classification, self.StabilityClass.UNSTABLE)

    def test_stable_hessian(self):
        h = self._make_hessian_result(0, 0.01)
        report = self.classify_from_hessian(h)
        self.assertEqual(report.classification, self.StabilityClass.STABLE)

    def test_unstable_hessian(self):
        h = self._make_hessian_result(2, -0.5)
        report = self.classify_from_hessian(h)
        self.assertEqual(report.classification, self.StabilityClass.UNSTABLE)

    def test_combined_stable(self):
        ph = self._make_phonon_result(0, 5.0)
        h = self._make_hessian_result(0, 0.01)
        r = self.classify_combined(h, ph)
        self.assertEqual(r.classification, self.StabilityClass.STABLE)

    def test_combined_phonon_unstable_dominates(self):
        ph = self._make_phonon_result(2, -200.0)
        h = self._make_hessian_result(0, 0.01)
        r = self.classify_combined(h, ph)
        self.assertEqual(r.classification, self.StabilityClass.UNSTABLE)

    def test_stability_report_is_valid_structure(self):
        ph = self._make_phonon_result(0, 5.0)
        r = self.classify_from_phonons(ph)
        self.assertTrue(r.is_valid_structure)

    def test_unstable_not_valid_structure(self):
        ph = self._make_phonon_result(5, -300.0)
        r = self.classify_from_phonons(ph)
        self.assertFalse(r.is_valid_structure)

    def test_source_phonons(self):
        ph = self._make_phonon_result(0, 5.0)
        r = self.classify_from_phonons(ph)
        self.assertEqual(r.source, "phonons")

    def test_source_hessian(self):
        h = self._make_hessian_result(0, 0.01)
        r = self.classify_from_hessian(h)
        self.assertEqual(r.source, "hessian")

    def test_source_combined(self):
        ph = self._make_phonon_result(0, 5.0)
        h = self._make_hessian_result(0, 0.01)
        r = self.classify_combined(h, ph)
        self.assertEqual(r.source, "both")

    def test_recommendations_present_when_unstable(self):
        ph = self._make_phonon_result(3, -200.0)
        r = self.classify_from_phonons(ph)
        self.assertGreater(len(r.recommendations), 0)

    def test_no_recommendations_when_stable(self):
        ph = self._make_phonon_result(0, 5.0)
        r = self.classify_from_phonons(ph)
        self.assertEqual(len(r.recommendations), 0)


# Tests

class TestSCFReportDataclass(unittest.TestCase):

    def setUp(self):
        from dft_cspbi3.validation.scf import SCFReport
        self.SCFReport = SCFReport

    def test_valid_when_converged_no_oscillation_no_flags(self):
        r = self.SCFReport(
            converged=True,
            iterations=15,
            final_energy_change_eV=1e-9,
            oscillating=False,
        )
        self.assertTrue(r.valid)

    def test_invalid_when_not_converged(self):
        r = self.SCFReport(
            converged=False,
            iterations=333,
            final_energy_change_eV=1e-2,
            oscillating=False,
            flags=["SCF_DID_NOT_CONVERGE"],
        )
        self.assertFalse(r.valid)

    def test_invalid_when_oscillating(self):
        r = self.SCFReport(
            converged=True,
            iterations=50,
            final_energy_change_eV=1e-3,
            oscillating=True,
            flags=["SCF_OSCILLATING"],
        )
        self.assertFalse(r.valid)

    def test_file_not_found_returns_invalid(self):
        from dft_cspbi3.validation.scf import validate_scf
        r = validate_scf("/nonexistent/path/scf.txt")
        self.assertFalse(r.converged)
        self.assertTrue(any("FILE_NOT_FOUND" in f for f in r.flags))

    def test_parse_converged_output(self):
        from dft_cspbi3.validation.scf import validate_scf
        gpaw_output = (
            "iter:   1  12:00:01  -1234.5678   +inf   -1.00\n"
            "iter:   2  12:00:02  -1234.6789  -0.50   -0.80\n"
            "iter:   3  12:00:03  -1234.6890  -1.23   -1.40\n"
            "Converged\n"
        )
        with patch("builtins.open", mock_open(read_data=gpaw_output)):
            with patch("pathlib.Path.exists", return_value=True):
                with patch("pathlib.Path.read_text", return_value=gpaw_output):
                    r = validate_scf(Path("/fake/scf.txt"))
        self.assertTrue(r.converged)
        self.assertEqual(r.iterations, 3)
        self.assertAlmostEqual(r.energy_history[0], -1234.5678)

    def test_parse_not_converged_output(self):
        from dft_cspbi3.validation.scf import validate_scf
        gpaw_output = (
            "iter:   1  12:00:01  -1234.5678   +inf   -1.00\n"
            "Did not converge!\n"
        )
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value=gpaw_output):
                r = validate_scf(Path("/fake/scf.txt"))
        self.assertFalse(r.converged)
        self.assertIn("SCF_DID_NOT_CONVERGE", r.flags)

    def test_oscillation_detection(self):
        from dft_cspbi3.validation.scf import validate_scf
        # Alternating energies → debe detecta oscillation
        lines = "\n".join(
            f"iter:  {i+1}  12:00:{i:02d}  {e:.4f}   -1.00   -1.00"
            for i, e in enumerate([-100, -101, -100, -101, -100, -101, -100, -101])
        )
        gpaw_output = lines + "\nConverged\n"
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value=gpaw_output):
                r = validate_scf(Path("/fake/scf.txt"))
        self.assertTrue(r.oscillating)


# Tests

class TestPhysicalChecks(unittest.TestCase):

    def test_valid_calculation(self):
        from dft_cspbi3.validation.scf import validate_physical_checks
        pc = validate_physical_checks("/fake/scf.gpw")
        self.assertTrue(pc.energy_negative)
        self.assertAlmostEqual(pc.energy_eV, -100.0)
        self.assertTrue(pc.valid)

    def test_energy_negative_flag(self):
        from dft_cspbi3.validation.scf import validate_physical_checks
        # Patch GPAW mock devuelve positive energía
        import sys
        orig = sys.modules["gpaw"].GPAW
        class _BadGPAW(orig):
            def get_potential_energy(self): return +5.0
        sys.modules["gpaw"].GPAW = _BadGPAW
        try:
            pc = validate_physical_checks("/fake/scf.gpw")
            self.assertFalse(pc.energy_negative)
            self.assertIn("ENERGY_NOT_NEGATIVE", pc.flags)
        finally:
            sys.modules["gpaw"].GPAW = orig

    def test_electron_count_positive(self):
        from dft_cspbi3.validation.scf import validate_physical_checks
        pc = validate_physical_checks("/fake/scf.gpw")
        self.assertGreater(pc.n_electrons, 0)


# Tests

class TestSOCReport(unittest.TestCase):

    def setUp(self):
        from dft_cspbi3.validation.soc import SOCReport
        self.SOCReport = SOCReport

    def test_valid_soc_report(self):
        r = self.SOCReport(
            soc_applied=True,
            gap_no_soc_eV=1.44,
            gap_soc_eV=0.60,
            chi_soc_eV=-0.84,
            chi_soc_plausible=True,
            splitting_detected=True,
            spurious_magnetisation=False,
            n_kpts=8,
            n_bands_soc=88,
        )
        self.assertTrue(r.valid)

    def test_file_not_found(self):
        from dft_cspbi3.validation.soc import validate_soc
        r = validate_soc("/fake/scf.gpw", "/nonexistent/soc.npy", "/nonexistent/spin.npy")
        self.assertFalse(r.soc_applied)
        self.assertTrue(any("FILE_NOT_FOUND" in f for f in r.flags))

    def test_validate_soc_with_mocked_npy(self):
        from dft_cspbi3.validation.soc import validate_soc
        # soc_eigenvalues.npy
        e_kn = np.linspace(-5, 5, 8 * 88).reshape(8, 88)
        spin_kn = np.ones((8, 88)) * 0.3

        with patch("pathlib.Path.exists", return_value=True):
            with patch("numpy.load") as mock_load:
                mock_load.side_effect = [e_kn, spin_kn]
                r = validate_soc(
                    "/fake/scf.gpw",
                    "/fake/soc_eigenvalues.npy",
                    "/fake/soc_spin_projections.npy",
                )
        self.assertTrue(r.soc_applied)
        self.assertEqual(r.n_kpts, 8)
        self.assertEqual(r.n_bands_soc, 88)

    def test_chi_soc_sign(self):
        r = self.SOCReport(
            soc_applied=True,
            gap_no_soc_eV=1.44,
            gap_soc_eV=0.60,
            chi_soc_eV=-0.84,
            chi_soc_plausible=True,
            splitting_detected=True,
            spurious_magnetisation=False,
            n_kpts=8,
            n_bands_soc=88,
        )
        # For Pb systems, χSOC debe be negative
        self.assertLess(r.chi_soc_eV, 0)

    def test_out_of_range_chi_soc_invalid(self):
        r = self.SOCReport(
            soc_applied=True,
            gap_no_soc_eV=1.44,
            gap_soc_eV=2.5,    # SOC increases gap - physically wrong para Pb
            chi_soc_eV=+1.06,
            chi_soc_plausible=False,
            splitting_detected=True,
            spurious_magnetisation=False,
            n_kpts=8,
            n_bands_soc=88,
            flags=["CHI_SOC_OUT_OF_RANGE:+1.06eV"],
        )
        self.assertFalse(r.valid)


# Tests

class TestHessianResult(unittest.TestCase):

    def setUp(self):
        from dft_cspbi3.validation.hessian import HessianResult
        self.HessianResult = HessianResult

    def _make_result(self, eigenvalues, n_negative=None, n_zero=None):
        ev = np.array(eigenvalues)
        if n_negative is None:
            n_negative = int(np.sum(ev < -0.05))
        if n_zero is None:
            n_zero = int(np.sum(np.abs(ev) <= 0.05))
        N = len(ev) // 3
        return self.HessianResult(
            hessian=np.eye(len(ev)),
            eigenvalues=ev,
            eigenvectors=np.eye(len(ev)),
            dynamical_matrix=np.eye(len(ev)),
            n_atoms=N,
            fmax_initial_eV_Ang=0.005,
            delta_Ang=0.01,
            n_negative=n_negative,
            n_zero=n_zero,
            forces_converged=True,
        )

    def test_stable_all_positive(self):
        r = self._make_result([0.0, 0.0, 0.0, 0.1, 0.5, 1.0])  # 2 atoms, 3 zero, 3 pos
        self.assertTrue(r.stable)
        self.assertEqual(r.n_negative, 0)

    def test_unstable_negative_eigenvalue(self):
        r = self._make_result([-0.5, 0.0, 0.0, 0.1, 0.5, 1.0])
        self.assertFalse(r.stable)
        self.assertGreater(r.n_negative, 0)

    def test_min_eigenvalue(self):
        r = self._make_result([-0.5, -0.1, 0.0, 0.1, 0.5])
        self.assertAlmostEqual(r.min_eigenvalue, -0.5)

    def test_summary_contains_stable_when_stable(self):
        r = self._make_result([0.0, 0.0, 0.0, 0.5, 1.0, 2.0])
        self.assertIn("STABLE", r.summary)

    def test_summary_contains_unstable_when_not(self):
        r = self._make_result([-1.0, 0.0, 0.0, 0.5, 1.0, 2.0])
        self.assertIn("UNSTABLE", r.summary)

    def test_hessian_symmetry(self):
        from dft_cspbi3.validation.hessian import compute_hessian
        import types

        # Construye fake atoms object y calculator that returns known fuerzas
        atoms = MagicMock()
        atoms.__len__ = MagicMock(return_value=2)
        atoms.get_masses.return_value = np.array([1.0, 1.0])
        pos0 = np.zeros((2, 3))
        atoms.get_positions.return_value = pos0.copy()
        atoms.copy.return_value = atoms

        call_count = [0]
        def fake_forces():
            call_count[0] += 1
            # Devuelve small random fuerzas
            return np.random.default_rng(call_count[0]).random((2, 3)) * 0.001

        atoms.get_forces.side_effect = fake_forces
        atoms.set_positions.return_value = None

        calc = MagicMock()

        result = compute_hessian(atoms, calc, delta=0.01)
        # Revisa H symmetric (by construction - (H + H.T)/2)
        diff = np.max(np.abs(result.hessian - result.hessian.T))
        self.assertAlmostEqual(diff, 0.0, places=12)


# Tests

class TestPhononHelpers(unittest.TestCase):

    def test_eV_to_cm1_positive(self):
        from dft_cspbi3.validation.phonons import _eV_to_cm1_signed
        eV = np.array([0.01, 0.02, 0.03])
        cm1 = _eV_to_cm1_signed(eV)
        self.assertTrue(np.all(cm1 > 0))

    def test_eV_to_cm1_negative_preserved(self):
        from dft_cspbi3.validation.phonons import _eV_to_cm1_signed
        eV = np.array([-0.01, 0.02])
        cm1 = _eV_to_cm1_signed(eV)
        self.assertLess(cm1[0], 0)
        self.assertGreater(cm1[1], 0)

    def test_eV_to_cm1_conversion_factor(self):
        from dft_cspbi3.validation.phonons import _eV_to_cm1_signed
        # 1 eV = 8065.544 cm⁻¹
        result = float(_eV_to_cm1_signed(np.array([1.0]))[0])
        self.assertAlmostEqual(result, 8065.544, places=0)

    def test_phonon_result_stable(self):
        from dft_cspbi3.validation.phonons import PhononResult
        r = PhononResult(
            frequencies_cm1=np.array([10.0, 50.0, 100.0, 200.0]),
            n_imaginary=0,
            max_imaginary_cm1=0.0,
            n_atoms_unit_cell=5,
            supercell=(2, 2, 2),
            delta_Ang=0.05,
            band_structure=None,
            dos_frequencies_cm1=None,
            dos_weights=None,
        )
        self.assertTrue(r.stable)
        self.assertIn("STABLE", r.summary)

    def test_phonon_result_unstable(self):
        from dft_cspbi3.validation.phonons import PhononResult
        r = PhononResult(
            frequencies_cm1=np.array([-150.0, 50.0, 200.0]),
            n_imaginary=1,
            max_imaginary_cm1=-150.0,
            n_atoms_unit_cell=5,
            supercell=(2, 2, 2),
            delta_Ang=0.05,
            band_structure=None,
            dos_frequencies_cm1=None,
            dos_weights=None,
        )
        self.assertFalse(r.stable)
        self.assertIn("UNSTABLE", r.summary)


# Tests

class TestReportingMethodology(unittest.TestCase):

    def test_generate_methodology(self):
        import tempfile
        from dft_cspbi3.reporting.methodology import generate_methodology
        with tempfile.TemporaryDirectory() as tmpdir:
            path = generate_methodology(
                params={"xc": "PBEsol", "ecut_eV": 450, "kpts": [6, 6, 6]},
                output_dir=tmpdir,
            )
            self.assertTrue(path.exists())
            text = path.read_text(encoding="utf-8")
            self.assertIn("Kohn-Sham", text)
            self.assertIn("Born-Oppenheimer", text)
            self.assertIn("PBEsol", text)
            self.assertIn("450", text)
            self.assertIn("Hessian", text)
            self.assertIn("phonon", text.lower())

    def test_generate_assumptions(self):
        import tempfile
        from dft_cspbi3.reporting.assumptions import generate_assumptions
        with tempfile.TemporaryDirectory() as tmpdir:
            path = generate_assumptions(
                params={"ecut_eV": 450, "kpts": [6, 6, 6]},
                output_dir=tmpdir,
            )
            self.assertTrue(path.exists())
            text = path.read_text(encoding="utf-8")
            self.assertIn("PBE", text)
            self.assertIn("450", text)
            self.assertIn("reproducib", text.lower())

    def test_methodology_xc_note_pbe(self):
        from dft_cspbi3.reporting.methodology import _xc_note
        note = _xc_note("PBE")
        self.assertIn("PBE", note)
        self.assertIn("GGA", note)

    def test_methodology_xc_note_hse06(self):
        from dft_cspbi3.reporting.methodology import _xc_note
        note = _xc_note("HSE06")
        self.assertIn("HSE06", note)
        self.assertIn("hybrid", note)

    def test_methodology_xc_note_unknown(self):
        from dft_cspbi3.reporting.methodology import _xc_note
        note = _xc_note("UNKNOWN_XC")
        self.assertEqual(note, "")


# Tests

class TestValidationReport(unittest.TestCase):

    def _make_data(self, **overrides):
        from dft_cspbi3.reporting.validation_report import ValidationData
        defaults = dict(
            phase="alpha",
            formula="CsPbI3",
            n_atoms=5,
            volume_ang3=236.7,
            xc="PBEsol",
            ecut_eV=450,
            kpts=[6, 6, 6],
            total_energy_eV=-100.0,
            fermi_level_eV=1.5,
            bandgap_eV=1.44,
            electronic_type="semiconductor",
        )
        defaults.update(overrides)
        return ValidationData(**defaults)

    def test_report_creates_file(self):
        import tempfile
        from dft_cspbi3.reporting.validation_report import generate_validation_report
        with tempfile.TemporaryDirectory() as tmpdir:
            data = self._make_data()
            path = generate_validation_report(data, output_dir=tmpdir)
            self.assertTrue(path.exists())

    def test_report_contains_system_info(self):
        import tempfile
        from dft_cspbi3.reporting.validation_report import generate_validation_report
        with tempfile.TemporaryDirectory() as tmpdir:
            data = self._make_data()
            path = generate_validation_report(data, output_dir=tmpdir)
            text = path.read_text(encoding="utf-8")
            self.assertIn("CsPbI3", text)
            self.assertIn("alpha", text)
            self.assertIn("450", text)
            self.assertIn("k-point mesh", text)
            self.assertIn("6", text)

    def test_report_valid_status_when_no_flags(self):
        import tempfile
        from dft_cspbi3.reporting.validation_report import generate_validation_report
        with tempfile.TemporaryDirectory() as tmpdir:
            data = self._make_data()
            path = generate_validation_report(data, output_dir=tmpdir)
            text = path.read_text(encoding="utf-8")
            self.assertIn("VALID", text)
            self.assertNotIn("INVALID", text)

    def test_report_invalid_status_when_critical_flag(self):
        import tempfile
        from dft_cspbi3.reporting.validation_report import generate_validation_report
        with tempfile.TemporaryDirectory() as tmpdir:
            data = self._make_data(extra_flags=["SCF_DID_NOT_CONVERGE"])
            path = generate_validation_report(data, output_dir=tmpdir)
            text = path.read_text(encoding="utf-8")
            self.assertIn("INVALID", text)

    def test_report_bandgap_in_table(self):
        import tempfile
        from dft_cspbi3.reporting.validation_report import generate_validation_report
        with tempfile.TemporaryDirectory() as tmpdir:
            data = self._make_data(bandgap_eV=1.44)
            path = generate_validation_report(data, output_dir=tmpdir)
            text = path.read_text(encoding="utf-8")
            self.assertIn("1.4400", text)

    def test_fmt_opt_none(self):
        from dft_cspbi3.reporting.validation_report import _fmt_opt
        self.assertEqual(_fmt_opt(None, ".4f"), "N/A")

    def test_fmt_opt_value(self):
        from dft_cspbi3.reporting.validation_report import _fmt_opt
        self.assertEqual(_fmt_opt(1.44, ".4f"), "1.4400")


# Tests

class TestVibrationalReport(unittest.TestCase):

    def _make_phonon_result(self, n_imaginary=0, max_imag=0.0):
        r = MagicMock()
        r.n_imaginary = n_imaginary
        r.max_imaginary_cm1 = max_imag
        r.frequencies_cm1 = np.array([max_imag if max_imag < 0 else 5.0,
                                       50.0, 100.0, 200.0, 300.0])
        r.n_atoms_unit_cell = 5
        r.supercell = (2, 2, 2)
        r.delta_Ang = 0.05
        r.stable = (n_imaginary == 0)
        r.flags = []
        return r

    def _make_stability(self, cls_value="stable"):
        from dft_cspbi3.validation.stability import StabilityClass
        s = MagicMock()
        s.classification = StabilityClass(cls_value)
        s.diagnosis = "Test diagnosis."
        s.recommendations = []
        return s

    def test_creates_file(self):
        import tempfile
        from dft_cspbi3.reporting.vibrational_analysis import generate_vibrational_report
        with tempfile.TemporaryDirectory() as tmpdir:
            ph = self._make_phonon_result()
            path = generate_vibrational_report(phonon_result=ph, output_dir=tmpdir)
            self.assertTrue(path.exists())

    def test_raises_without_results(self):
        from dft_cspbi3.reporting.vibrational_analysis import generate_vibrational_report
        with self.assertRaises(ValueError):
            generate_vibrational_report()

    def test_stable_message_present(self):
        import tempfile
        from dft_cspbi3.reporting.vibrational_analysis import generate_vibrational_report
        with tempfile.TemporaryDirectory() as tmpdir:
            ph = self._make_phonon_result(0)
            st = self._make_stability("stable")
            path = generate_vibrational_report(phonon_result=ph, stability_report=st,
                                               output_dir=tmpdir)
            text = path.read_text(encoding="utf-8")
            self.assertIn("stable", text.lower())

    def test_unstable_warning_present(self):
        import tempfile
        from dft_cspbi3.reporting.vibrational_analysis import generate_vibrational_report
        with tempfile.TemporaryDirectory() as tmpdir:
            ph = self._make_phonon_result(3, -200.0)
            st = self._make_stability("unstable")
            path = generate_vibrational_report(phonon_result=ph, stability_report=st,
                                               output_dir=tmpdir)
            text = path.read_text(encoding="utf-8")
            self.assertIn("instabilit", text.lower())


# Tests

class TestSOCWasApplied(unittest.TestCase):

    def test_true_when_npy_exists(self):
        from dft_cspbi3.validation.soc import soc_was_applied
        with patch("pathlib.Path.exists", return_value=True):
            self.assertTrue(soc_was_applied("/fake/soc_dir"))

    def test_false_when_npy_missing(self):
        from dft_cspbi3.validation.soc import soc_was_applied
        with patch("pathlib.Path.exists", return_value=False):
            self.assertFalse(soc_was_applied("/fake/soc_dir"))


# Entry point

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in [
        TestStabilityClass,
        TestSCFReportDataclass,
        TestPhysicalChecks,
        TestSOCReport,
        TestHessianResult,
        TestPhononHelpers,
        TestReportingMethodology,
        TestValidationReport,
        TestVibrationalReport,
        TestSOCWasApplied,
    ]:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
