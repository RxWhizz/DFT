"""Construye ASE Atoms para polimorfos CsPbI3 (α, β, γ, δ) y superceldas."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import numpy as np
from ase import Atoms
from ase.build import make_supercell
from ase.io import read
from ase.spacegroup import crystal

STRUCTURES_DIR = Path(__file__).parent.parent.parent / "structures"


class StructureBuilder:
    """Factory para estructuras cristalinas CsPbI3."""

    # Parametros red experimento/literatura.
    _ALPHA_A0 = 6.2965  # Å, Pm-3m

    _BETA_PARAMS = {"a": 8.8269, "c": 6.299}  # Å, P4/mbm
    _GAMMA_PARAMS = {"a": 8.855, "b": 8.579, "c": 12.47}  # Å, Pnma
    _DELTA_PARAMS = {"a": 10.47, "b": 4.80, "c": 17.77}    # Å, Pnma

    @classmethod
    def build_alpha(cls, a0: float = _ALPHA_A0) -> Atoms:
        """α-CsPbI3 cubica (Pm-3m, grupo 221, 5 atomos/celda)."""
        atoms = crystal(
            symbols=["Cs", "Pb", "I"],
            basis=[
                (0.5, 0.5, 0.5),   # Cs 1b
                (0.0, 0.0, 0.0),   # Pb 1a
                (0.5, 0.0, 0.0),   # I 3d (one representativo)
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
        """β-CsPbI3 tetragonal (P4/mbm, grupo 127, 10 atomos/celda)."""
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
        """γ-CsPbI3 ortorrombica (Pnma, grupo 62, 20 atomos/celda)."""
        # Posiciones Wyckoff 4c para Cs, Pb.
        cs_basis = [(0.9837, 0.25, 0.0192)]    # Cs 4c
        pb_basis = [(0.0, 0.0, 0.5)]            # Pb 4a
        i1_basis = [(0.1958, 0.25, 0.5768)]    # I1 4c (apical)
        i2_basis = [(0.3044, 0.0452, 0.3004)]  # I2 8d (equatorial)

        atoms = crystal(
            symbols=["Cs", "Pb", "I", "I"],
            basis=cs_basis + pb_basis + i1_basis + i2_basis,
            spacegroup=62,
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
        """δ-CsPbI3 ortorrombica (Pnma, 20 atomos/celda), fase amarilla."""
        cs_basis = [(0.6448, 0.25, 0.5713)]
        pb_basis = [(0.0, 0.0, 0.0)]
        i1_basis = [(0.1618, 0.25, 0.1032)]
        i2_basis = [(0.1265, 0.0195, 0.6605)]

        atoms = crystal(
            symbols=["Cs", "Pb", "I", "I"],
            basis=cs_basis + pb_basis + i1_basis + i2_basis,
            spacegroup=62,
            cellpar=[a, b, c, 90.0, 90.0, 90.0],
        )
        atoms.info["phase"] = "delta_orthorhombic"
        atoms.info["space_group"] = "Pnma"
        atoms.info["space_group_number"] = 62
        atoms.info["connectivity"] = "edge-sharing_octahedra"
        return atoms

    @classmethod
    def build_supercell(cls, atoms: Atoms, scaling_matrix) -> Atoms:
        """Expande atomos a supercelda con matriz 3×3 o lista diagonal."""
        if not isinstance(scaling_matrix, np.ndarray):
            scaling_matrix = np.array(scaling_matrix)
        if scaling_matrix.ndim == 1:
            scaling_matrix = np.diag(scaling_matrix)
        supercell = make_supercell(atoms, scaling_matrix)
        supercell.info["supercell_matrix"] = scaling_matrix.tolist()
        return supercell

    @classmethod
    def from_json(cls, json_path: str | Path) -> Atoms:
        """Carga Atoms desde JSON ASE/simple."""
        with open(json_path, encoding="utf-8") as fh:
            data = json.load(fh)
        entry = data.get("1", data)

        def _arr(value):
            if isinstance(value, dict) and "__ndarray__" in value:
                shape, dtype, flat = value["__ndarray__"]
                return np.array(flat, dtype=dtype).reshape(shape)
            if isinstance(value, dict) and "array" in value:
                return _arr(value["array"])
            return np.array(value)

        atoms = Atoms(
            numbers=_arr(entry["numbers"]).astype(int),
            positions=_arr(entry["positions"]).astype(float),
            cell=_arr(entry["cell"]).astype(float),
            pbc=_arr(entry.get("pbc", [True, True, True])).astype(bool),
        )
        atoms.info.update(entry.get("info", {}))
        return atoms

    @classmethod
    def save_json(cls, atoms: Atoms, json_path: str | Path) -> None:
        """Serializa Atoms a JSON simple."""
        path = Path(json_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        def _jsonable(value):
            if isinstance(value, np.ndarray):
                return value.tolist()
            if isinstance(value, np.generic):
                return value.item()
            if isinstance(value, dict):
                return {str(k): _jsonable(v) for k, v in value.items()}
            if isinstance(value, (list, tuple)):
                return [_jsonable(v) for v in value]
            try:
                json.dumps(value)
            except TypeError:
                return str(value)
            return value

        payload = {
            "1": {
                "numbers": atoms.get_atomic_numbers().tolist(),
                "positions": atoms.get_positions().tolist(),
                "cell": atoms.cell.array.tolist(),
                "pbc": atoms.pbc.tolist(),
                "info": _jsonable(dict(atoms.info)),
            }
        }
        path.write_text(json.dumps(payload, indent=4), encoding="utf-8")

    @classmethod
    def build_perovskite_cubic(
        cls,
        A: str,
        B: str,
        X: str,
        a0: float,
    ) -> Atoms:
        """Perovskita cubica ABX3 generica, Pm-3m (grupo 221)."""
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
        """Carga estructura desde CIF archivo."""
        return read(str(cif_path), format="cif")

    @classmethod
    def load_phase_generic(
        cls,
        phase: str,
        structures_dir: str | Path | None = None,
    ) -> Atoms:
        """Carga fase por nombre desde JSON o CIF."""
        if structures_dir is None and phase in ("alpha", "beta", "gamma", "delta"):
            return cls.load_phase(phase)
        sdir = Path(structures_dir) if structures_dir else STRUCTURES_DIR
        for ext in ("json", "cif"):
            p = sdir / f"{phase}.{ext}"
            if p.exists():
                return read(str(p))
        raise FileNotFoundError(
            f"No existe archivo estructura para fase '{phase}' en {sdir}\n"
            "Da JSON/CIF o usa build_perovskite_cubic() para fases cubicas."
        )

    @classmethod
    def load_phase(cls, phase: str) -> Atoms:
        """Carga estructura CsPbI3 precomputada desde structures/."""
        mapping = {
            "alpha": STRUCTURES_DIR / "alpha_cubic.json",
            "beta": STRUCTURES_DIR / "beta_tetra.json",
            "gamma": STRUCTURES_DIR / "gamma_ortho.json",
            "delta": STRUCTURES_DIR / "delta_ortho.json",
        }
        if phase not in mapping:
            raise ValueError(f"Fase desconocida '{phase}'. Opciones: {list(mapping)}")
        path = mapping[phase]
        if not path.exists():
            raise FileNotFoundError(
                f"No existe archivo estructura: {path}\n"
                "Ejecuta StructureBuilder.build_<phase>() y save_json() primero."
            )
        return cls.from_json(path)

    @classmethod
    def generate_all(cls, output_dir: Optional[Path] = None) -> dict[str, Atoms]:
        """Construye fases y opcionalmente guarda JSON."""
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
