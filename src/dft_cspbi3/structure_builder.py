"""Build ASE Atoms objects for CsPbI3 polymorphs (α, β, γ, δ) and supercells."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import numpy as np
from ase import Atoms
from ase.build import make_supercell
from ase.io import read, write
from ase.spacegroup import crystal

STRUCTURES_DIR = Path(__file__).parent.parent.parent / "structures"


class StructureBuilder:
    """Factory for CsPbI3 crystal structures."""

    # Experimental / literature lattice parameters
    _ALPHA_A0 = 6.2965  # Å, Pm-3m

    _BETA_PARAMS = {"a": 8.8269, "c": 6.299}  # Å, P4/mbm
    _GAMMA_PARAMS = {"a": 8.855, "b": 8.579, "c": 12.47}  # Å, Pnma
    _DELTA_PARAMS = {"a": 10.47, "b": 4.80, "c": 17.77}    # Å, Pnma

    @classmethod
    def build_alpha(cls, a0: float = _ALPHA_A0) -> Atoms:
        """Cubic α-CsPbI3 (Pm-3m, space group 221, 5 atoms/cell).

        Wyckoff positions:
          Cs  1b  (1/2, 1/2, 1/2) — but ASE crystal uses origin choice
          Pb  1a  (0, 0, 0)
          I   3d  (1/2, 0, 0) + permutations
        """
        atoms = crystal(
            symbols=["Cs", "Pb", "I"],
            basis=[
                (0.5, 0.5, 0.5),   # Cs  1b
                (0.0, 0.0, 0.0),   # Pb  1a
                (0.5, 0.0, 0.0),   # I   3d (one representative)
            ],
            spacegroup=221,        # Pm-3m
            cellpar=[a0, a0, a0, 90.0, 90.0, 90.0],
        )
        atoms.info["phase"] = "alpha_cubic"
        atoms.info["space_group"] = "Pm-3m"
        atoms.info["space_group_number"] = 221
        return atoms

    @classmethod
    def build_beta(
        cls,
        a: float = _BETA_PARAMS["a"],
        c: float = _BETA_PARAMS["c"],
        i2_x: float = 0.225,
    ) -> Atoms:
        """Tetragonal β-CsPbI3 (P4/mbm, space group 127, 10 atoms/cell).

        This is an in-phase a0a0c+ tilted perovskite starting model.
        Lattice constants are a conventional tetragonal cell; ``i2_x`` controls
        the equatorial iodine tilt coordinate.
        """
        cs_basis = [(0.0, 0.5, 0.0)]
        pb_basis = [(0.0, 0.0, 0.5)]
        i1_basis = [(0.0, 0.0, 0.0)]
        i2_basis = [(i2_x, 0.5 - i2_x, 0.5)]

        atoms = crystal(
            symbols=["Cs", "Pb", "I", "I"],
            basis=cs_basis + pb_basis + i1_basis + i2_basis,
            spacegroup=127,  # P4/mbm
            cellpar=[a, a, c, 90.0, 90.0, 90.0],
        )
        atoms.info["phase"] = "beta_tetragonal"
        atoms.info["space_group"] = "P4/mbm"
        atoms.info["space_group_number"] = 127
        atoms.info["glazer_tilt"] = "a0a0c+"
        return atoms

    @classmethod
    def build_gamma(
        cls,
        a: float = _GAMMA_PARAMS["a"],
        b: float = _GAMMA_PARAMS["b"],
        c: float = _GAMMA_PARAMS["c"],
    ) -> Atoms:
        """Orthorhombic γ-CsPbI3 (Pnma, space group 62, 20 atoms/cell).

        Glazer tilt system a⁻b⁺a⁻. Fractional coordinates from literature
        (Sutton et al., ACS Energy Lett. 2018).
        """
        # Wyckoff 4c positions for Cs, Pb; 4c + 8d for I
        cs_basis = [(0.9837, 0.25, 0.0192)]    # Cs  4c
        pb_basis = [(0.0, 0.0, 0.5)]            # Pb  4a
        i1_basis = [(0.1958, 0.25, 0.5768)]    # I1  4c (apical)
        i2_basis = [(0.3044, 0.0452, 0.3004)]  # I2  8d (equatorial)

        atoms = crystal(
            symbols=["Cs", "Pb", "I", "I"],
            basis=cs_basis + pb_basis + i1_basis + i2_basis,
            spacegroup=62,   # Pnma
            cellpar=[a, b, c, 90.0, 90.0, 90.0],
        )
        atoms.info["phase"] = "gamma_orthorhombic"
        atoms.info["space_group"] = "Pnma"
        atoms.info["space_group_number"] = 62
        atoms.info["glazer_tilt"] = "a-b+a-"
        return atoms

    @classmethod
    def build_delta(
        cls,
        a: float = _DELTA_PARAMS["a"],
        b: float = _DELTA_PARAMS["b"],
        c: float = _DELTA_PARAMS["c"],
    ) -> Atoms:
        """Orthorhombic δ-CsPbI3 (Pnma, 20 atoms/cell) — non-perovskite yellow phase.

        Edge-sharing PbI6 octahedra, thermodynamically stable at room temperature.
        """
        cs_basis = [(0.6448, 0.25, 0.5713)]
        pb_basis = [(0.0, 0.0, 0.0)]
        i1_basis = [(0.1618, 0.25, 0.1032)]
        i2_basis = [(0.1265, 0.0195, 0.6605)]

        atoms = crystal(
            symbols=["Cs", "Pb", "I", "I"],
            basis=cs_basis + pb_basis + i1_basis + i2_basis,
            spacegroup=62,   # Pnma
            cellpar=[a, b, c, 90.0, 90.0, 90.0],
        )
        atoms.info["phase"] = "delta_orthorhombic"
        atoms.info["space_group"] = "Pnma"
        atoms.info["space_group_number"] = 62
        atoms.info["connectivity"] = "edge-sharing_octahedra"
        return atoms

    @classmethod
    def build_supercell(cls, atoms: Atoms, scaling_matrix) -> Atoms:
        """Expand atoms into a supercell using a 3×3 scaling matrix or diagonal list."""
        if not isinstance(scaling_matrix, np.ndarray):
            scaling_matrix = np.array(scaling_matrix)
        if scaling_matrix.ndim == 1:
            scaling_matrix = np.diag(scaling_matrix)
        supercell = make_supercell(atoms, scaling_matrix)
        supercell.info["supercell_matrix"] = scaling_matrix.tolist()
        return supercell

    @classmethod
    def from_json(cls, json_path: str | Path) -> Atoms:
        """Load an Atoms object from an ASE JSON file."""
        return read(str(json_path), format="json")

    @classmethod
    def save_json(cls, atoms: Atoms, json_path: str | Path) -> None:
        """Serialize an Atoms object to ASE JSON format."""
        write(str(json_path), atoms, format="json")

    @classmethod
    def build_perovskite_cubic(
        cls,
        A: str,
        B: str,
        X: str,
        a0: float,
    ) -> Atoms:
        """Generic cubic ABX3 perovskite, Pm-3m (spacegroup 221).

        Wyckoff positions: A at 1b (1/2,1/2,1/2), B at 1a (0,0,0), X at 3d (1/2,0,0).
        A, B, X must be valid atomic symbols (Cs, Rb, K, Pb, Sn, I, Br, Cl …).
        For organic A-sites (MA, FA) load from a CIF via from_cif() instead.
        """
        atoms = crystal(
            symbols=[A, B, X],
            basis=[(0.5, 0.5, 0.5), (0.0, 0.0, 0.0), (0.5, 0.0, 0.0)],
            spacegroup=221,
            cellpar=[a0, a0, a0, 90.0, 90.0, 90.0],
        )
        atoms.info["phase"] = "cubic"
        atoms.info["space_group"] = "Pm-3m"
        atoms.info["composition"] = f"{A}{B}{X}3"
        return atoms

    @classmethod
    def from_cif(cls, cif_path: str | Path) -> Atoms:
        """Load structure from a CIF file."""
        return read(str(cif_path), format="cif")

    @classmethod
    def load_phase_generic(
        cls,
        phase: str,
        structures_dir: str | Path | None = None,
    ) -> Atoms:
        """Load any phase by name from a directory of JSON or CIF files.

        Searches <structures_dir>/<phase>.json then <phase>.cif.
        Falls back to load_phase() for alpha/beta/gamma/delta (CsPbI3 backwards compat).
        """
        if structures_dir is None and phase in ("alpha", "beta", "gamma", "delta"):
            return cls.load_phase(phase)
        sdir = Path(structures_dir) if structures_dir else STRUCTURES_DIR
        for ext in ("json", "cif"):
            p = sdir / f"{phase}.{ext}"
            if p.exists():
                return read(str(p))
        raise FileNotFoundError(
            f"No structure file for phase '{phase}' in {sdir}\n"
            "Provide a JSON or CIF file, or use build_perovskite_cubic() for cubic phases."
        )

    @classmethod
    def load_phase(cls, phase: str) -> Atoms:
        """Load a pre-computed CsPbI3 structure from the structures/ directory.

        Args:
            phase: One of 'alpha', 'beta', 'gamma', 'delta'.
        """
        mapping = {
            "alpha": STRUCTURES_DIR / "alpha_cubic.json",
            "beta": STRUCTURES_DIR / "beta_tetra.json",
            "gamma": STRUCTURES_DIR / "gamma_ortho.json",
            "delta": STRUCTURES_DIR / "delta_ortho.json",
        }
        if phase not in mapping:
            raise ValueError(f"Unknown phase '{phase}'. Choose from: {list(mapping)}")
        path = mapping[phase]
        if not path.exists():
            raise FileNotFoundError(
                f"Structure file not found: {path}\n"
                "Run StructureBuilder.build_<phase>() and save_json() first."
            )
        return cls.from_json(path)

    @classmethod
    def generate_all(cls, output_dir: Optional[Path] = None) -> dict[str, Atoms]:
        """Build all three phases and optionally save them to JSON files."""
        output_dir = output_dir or STRUCTURES_DIR
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        phases = {
            "alpha": cls.build_alpha(),
            "beta": cls.build_beta(),
            "gamma": cls.build_gamma(),
            "delta": cls.build_delta(),
        }
        filenames = {
            "alpha": "alpha_cubic.json",
            "beta": "beta_tetra.json",
            "gamma": "gamma_ortho.json",
            "delta": "delta_ortho.json",
        }
        for phase, atoms in phases.items():
            cls.save_json(atoms, Path(output_dir) / filenames[phase])
        return phases
