"""Tests for StructureBuilder — verifies geometry and symmetry of CsPbI3 phases."""

import numpy as np
import pytest

# StructureBuilder is importable without GPAW installed
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dft_cspbi3.structure_builder import StructureBuilder


class TestAlphaCubic:
    def setup_method(self):
        self.atoms = StructureBuilder.build_alpha()

    def test_atom_count(self):
        """α-CsPbI3 primitive cell must have exactly 5 atoms."""
        assert len(self.atoms) == 5

    def test_chemical_formula(self):
        symbols = sorted(self.atoms.get_chemical_symbols())
        assert symbols.count("Cs") == 1
        assert symbols.count("Pb") == 1
        assert symbols.count("I") == 3

    def test_lattice_parameter(self):
        """Cubic a₀ should match the experimental α-CsPbI3 reference."""
        cell = self.atoms.get_cell()
        lengths = np.sqrt((cell**2).sum(axis=1))
        assert pytest.approx(lengths[0], abs=0.01) == 6.2965
        assert pytest.approx(lengths[1], abs=0.01) == 6.2965
        assert pytest.approx(lengths[2], abs=0.01) == 6.2965

    def test_cubic_angles(self):
        """Cell angles must be 90° for the cubic phase."""
        cell = self.atoms.get_cell()
        a, b, c = cell[0], cell[1], cell[2]
        angle_ab = np.degrees(np.arccos(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))))
        angle_bc = np.degrees(np.arccos(np.dot(b, c) / (np.linalg.norm(b) * np.linalg.norm(c))))
        assert pytest.approx(angle_ab, abs=0.1) == 90.0
        assert pytest.approx(angle_bc, abs=0.1) == 90.0

    def test_phase_info(self):
        assert self.atoms.info.get("phase") == "alpha_cubic"
        assert self.atoms.info.get("space_group_number") == 221

    def test_pbc(self):
        assert all(self.atoms.pbc)

    def test_custom_lattice_parameter(self):
        atoms = StructureBuilder.build_alpha(a0=6.30)
        cell = atoms.get_cell()
        lengths = np.sqrt((cell**2).sum(axis=1))
        assert pytest.approx(lengths[0], abs=0.01) == 6.30

    def test_volume(self):
        """Volume should be close to a₀³."""
        vol = self.atoms.get_volume()
        expected = 6.2965**3
        assert pytest.approx(vol, rel=0.01) == expected

    def test_saved_alpha_matches_builder(self):
        loaded = StructureBuilder.load_phase("alpha")
        assert len(loaded) == len(self.atoms)
        np.testing.assert_allclose(loaded.get_cell(), self.atoms.get_cell(), atol=1e-6)
        np.testing.assert_allclose(loaded.get_positions(), self.atoms.get_positions(), atol=5e-5)


class TestGammaOrthorhombic:
    def setup_method(self):
        self.atoms = StructureBuilder.build_gamma()

    def test_atom_count(self):
        """γ-CsPbI3 unit cell must have 20 atoms (4 formula units)."""
        assert len(self.atoms) == 20

    def test_chemical_composition(self):
        symbols = self.atoms.get_chemical_symbols()
        assert symbols.count("Cs") == 4
        assert symbols.count("Pb") == 4
        assert symbols.count("I") == 12

    def test_lattice_parameters(self):
        cell = self.atoms.get_cell()
        lengths = np.sqrt((cell**2).sum(axis=1))
        # a ≈ 8.855, b ≈ 8.579, c ≈ 12.47 Å
        assert pytest.approx(lengths[0], abs=0.05) == 8.855
        assert pytest.approx(lengths[1], abs=0.05) == 8.579
        assert pytest.approx(lengths[2], abs=0.05) == 12.47

    def test_orthorhombic_angles(self):
        cell = self.atoms.get_cell()
        for i, j in [(0, 1), (1, 2), (0, 2)]:
            cos_angle = np.dot(cell[i], cell[j]) / (np.linalg.norm(cell[i]) * np.linalg.norm(cell[j]))
            assert pytest.approx(abs(cos_angle), abs=1e-4) == 0.0

    def test_phase_info(self):
        assert self.atoms.info.get("phase") == "gamma_orthorhombic"
        assert self.atoms.info.get("space_group_number") == 62

    def test_glazer_tilt(self):
        assert self.atoms.info.get("glazer_tilt") == "a-b+a-"

    def test_saved_gamma_matches_builder(self):
        loaded = StructureBuilder.load_phase("gamma")
        assert len(loaded) == len(self.atoms)
        np.testing.assert_allclose(loaded.get_cell(), self.atoms.get_cell(), atol=1e-6)
        np.testing.assert_allclose(loaded.get_positions(), self.atoms.get_positions(), atol=5e-5)


class TestBetaTetragonal:
    def setup_method(self):
        self.atoms = StructureBuilder.build_beta()

    def test_atom_count(self):
        """β-CsPbI3 conventional tetragonal cell must have 10 atoms."""
        assert len(self.atoms) == 10

    def test_chemical_composition(self):
        symbols = self.atoms.get_chemical_symbols()
        assert symbols.count("Cs") == 2
        assert symbols.count("Pb") == 2
        assert symbols.count("I") == 6

    def test_lattice_parameters(self):
        cell = self.atoms.get_cell()
        lengths = np.sqrt((cell**2).sum(axis=1))
        assert pytest.approx(lengths[0], abs=0.05) == 8.8269
        assert pytest.approx(lengths[1], abs=0.05) == 8.8269
        assert pytest.approx(lengths[2], abs=0.05) == 6.299

    def test_phase_info(self):
        assert self.atoms.info.get("phase") == "beta_tetragonal"
        assert self.atoms.info.get("space_group_number") == 127
        assert self.atoms.info.get("glazer_tilt") == "a0a0c+"

    def test_saved_beta_matches_builder(self):
        loaded = StructureBuilder.load_phase("beta")
        assert len(loaded) == len(self.atoms)
        np.testing.assert_allclose(loaded.get_cell(), self.atoms.get_cell(), atol=1e-6)
        np.testing.assert_allclose(loaded.get_positions(), self.atoms.get_positions(), atol=5e-5)


class TestDeltaOrthorhombic:
    def setup_method(self):
        self.atoms = StructureBuilder.build_delta()

    def test_atom_count(self):
        """δ-CsPbI3 unit cell must have 20 atoms."""
        assert len(self.atoms) == 20

    def test_chemical_composition(self):
        symbols = self.atoms.get_chemical_symbols()
        assert symbols.count("Cs") == 4
        assert symbols.count("Pb") == 4
        assert symbols.count("I") == 12

    def test_phase_info(self):
        assert self.atoms.info.get("phase") == "delta_orthorhombic"
        assert self.atoms.info.get("connectivity") == "edge-sharing_octahedra"


class TestSupercell:
    def test_2x2x2_alpha(self):
        atoms = StructureBuilder.build_alpha()
        sc = StructureBuilder.build_supercell(atoms, [2, 2, 2])
        assert len(sc) == 5 * 8

    def test_diagonal_matrix(self):
        atoms = StructureBuilder.build_alpha()
        sc = StructureBuilder.build_supercell(atoms, [3, 3, 3])
        assert len(sc) == 5 * 27

    def test_2x2x2_gamma(self):
        atoms = StructureBuilder.build_gamma()
        sc = StructureBuilder.build_supercell(atoms, [2, 2, 2])
        assert len(sc) == 20 * 8


class TestSerialisation:
    def test_round_trip(self, tmp_path):
        """Atoms written to JSON and read back should be identical."""
        atoms = StructureBuilder.build_alpha()
        json_path = tmp_path / "alpha.json"
        StructureBuilder.save_json(atoms, json_path)
        loaded = StructureBuilder.from_json(json_path)
        assert len(loaded) == len(atoms)
        np.testing.assert_allclose(
            loaded.get_positions(),
            atoms.get_positions(),
            atol=1e-6,
        )
        np.testing.assert_allclose(
            loaded.get_cell(),
            atoms.get_cell(),
            atol=1e-6,
        )
