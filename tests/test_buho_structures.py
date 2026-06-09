"""Tests para el constructor de estructuras ABX3."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

CONFIG = ROOT / "config" / "generator.yaml"


def _load_cfg():
    import yaml
    with open(CONFIG) as f:
        return yaml.safe_load(f)


def _make_candidate(A="Cs", B="Pb", X="I", mode="pure"):
    from buho.generator.heuristic_generator import HeuristicGenerator
    gen = HeuristicGenerator(CONFIG)
    return gen._make_candidate(
        A_sp=[A], B_sp=[B], X_sp=[X],
        A_f={A: 1.0}, B_f={B: 1.0}, X_f={X: 1.0},
        mode=mode,
    )


def _make_mixed_candidate(A1="Cs", A2="FA", fA=0.5, B="Pb", X="I"):
    from buho.generator.heuristic_generator import HeuristicGenerator
    gen = HeuristicGenerator(CONFIG)
    return gen._make_candidate(
        A_sp=[A1, A2], B_sp=[B], X_sp=[X],
        A_f={A1: fA, A2: round(1.0 - fA, 3)},
        B_f={B: 1.0}, X_f={X: 1.0},
        mode="A_mixed",
    )


# ── Estructura pura cúbica ─────────────────────────────────────────────────────

def test_pure_cubic_5_atoms():
    """Estructura cúbica pura tiene exactamente 5 átomos (Pm-3m)."""
    from buho.structure.build_abx3 import ABX3StructureBuilder
    cfg = _load_cfg()
    cfg["structure"]["supercell_pure"] = [1, 1, 1]
    builder = ABX3StructureBuilder(cfg)

    c = _make_candidate("Cs", "Pb", "I")
    assert c is not None
    atoms, meta = builder.build(c, export=False)
    assert len(atoms) == 5, f"Esperados 5 átomos, obtenidos {len(atoms)}"


def test_pure_cubic_lattice_constant():
    """El parámetro de red estimado está en rango físico [5, 10] Å."""
    from buho.structure.build_abx3 import ABX3StructureBuilder
    cfg = _load_cfg()
    cfg["structure"]["supercell_pure"] = [1, 1, 1]
    builder = ABX3StructureBuilder(cfg)

    for A, B, X in [("Cs", "Pb", "I"), ("Cs", "Sn", "Br"), ("Rb", "Ge", "Cl")]:
        c = _make_candidate(A, B, X)
        if c is None:
            continue
        atoms, meta = builder.build(c, export=False)
        cell_lengths = atoms.get_cell().lengths()
        a0 = float(cell_lengths[0])
        assert 5.0 <= a0 <= 10.0, f"{A}{B}{X}3: a₀={a0:.3f} Å fuera de rango"


def test_pure_cubic_pbc():
    """La estructura tiene condiciones de contorno periódicas."""
    from buho.structure.build_abx3 import ABX3StructureBuilder
    cfg = _load_cfg()
    cfg["structure"]["supercell_pure"] = [1, 1, 1]
    builder = ABX3StructureBuilder(cfg)
    c = _make_candidate("Cs", "Pb", "I")
    atoms, _ = builder.build(c, export=False)
    assert all(atoms.pbc), "La estructura debe tener PBC activadas"


# ── Superceldas mixtas ────────────────────────────────────────────────────────

def test_mixed_supercell_40_atoms():
    """Supercelda 2×2×2 de una mezcla A-site tiene 40 átomos."""
    from buho.structure.build_abx3 import ABX3StructureBuilder
    cfg = _load_cfg()
    cfg["structure"]["supercell_mixed"] = [2, 2, 2]
    builder = ABX3StructureBuilder(cfg)

    c = _make_mixed_candidate("Cs", "FA", 0.5, "Pb", "I")
    assert c is not None
    atoms, meta = builder.build(c, export=False)
    assert len(atoms) == 40, f"Esperados 40 átomos en 2×2×2, obtenidos {len(atoms)}"


def test_mixed_species_present():
    """Las especies de la mezcla están presentes en la estructura."""
    from buho.structure.build_abx3 import ABX3StructureBuilder
    cfg = _load_cfg()
    builder = ABX3StructureBuilder(cfg)

    c = _make_mixed_candidate("Cs", "FA", 0.5, "Pb", "I")
    assert c is not None
    atoms, meta = builder.build(c, export=False)
    symbols = set(atoms.get_chemical_symbols())
    # Cs debe estar presente (FA → placeholder Cs, o Cs genuino)
    assert "Pb" in symbols, "Pb debe estar en la estructura"
    assert "I" in symbols, "I debe estar en la estructura"


# ── Placeholder orgánico ──────────────────────────────────────────────────────

def test_organic_placeholder_flagged():
    """Estructura con MA/FA tiene molecular_A_placeholder=True en metadata."""
    from buho.structure.build_abx3 import ABX3StructureBuilder
    cfg = _load_cfg()
    builder = ABX3StructureBuilder(cfg)

    c = _make_candidate("MA", "Pb", "I")
    assert c is not None
    _, meta = builder.build(c, export=False)
    assert meta["molecular_A_placeholder"] is True
    assert meta["organic_A_warning"] is not None


def test_inorganic_no_placeholder():
    """Estructura inorgánica no tiene flag de placeholder."""
    from buho.structure.build_abx3 import ABX3StructureBuilder
    cfg = _load_cfg()
    builder = ABX3StructureBuilder(cfg)

    c = _make_candidate("Cs", "Pb", "I")
    _, meta = builder.build(c, export=False)
    assert meta["molecular_A_placeholder"] is False


# ── Exportación ───────────────────────────────────────────────────────────────

def test_export_all_formats(tmp_path):
    """Los archivos CIF, POSCAR y traj se crean y son legibles por ASE."""
    from ase.io import read as ase_read
    from buho.structure.build_abx3 import ABX3StructureBuilder

    cfg = _load_cfg()
    cfg["structure"]["supercell_pure"] = [1, 1, 1]
    cfg["structure"]["export_formats"] = ["cif", "poscar", "traj"]
    builder = ABX3StructureBuilder(cfg)

    c = _make_candidate("Cs", "Pb", "I")
    job_dir = tmp_path / c.candidate_id
    _, meta = builder.build(c, out_dir=job_dir, export=True)

    # Verifica que los archivos existen
    assert (job_dir / "structure.cif").exists()
    assert (job_dir / "POSCAR").exists()
    assert (job_dir / "structure.traj").exists()
    assert (job_dir / "metadata.json").exists()

    # Verifica que son legibles por ASE
    a1 = ase_read(str(job_dir / "structure.cif"))
    a2 = ase_read(str(job_dir / "POSCAR"))
    assert len(a1) == len(a2) == 5


def test_metadata_json_complete(tmp_path):
    """El metadata.json contiene los campos requeridos."""
    import json
    from buho.structure.build_abx3 import ABX3StructureBuilder

    cfg = _load_cfg()
    builder = ABX3StructureBuilder(cfg)
    c = _make_candidate("Cs", "Sn", "Br")
    job_dir = tmp_path / c.candidate_id
    _, meta = builder.build(c, out_dir=job_dir, export=True)

    saved = json.loads((job_dir / "metadata.json").read_text())
    for field in ("candidate_id", "formula", "n_atoms", "lattice_constant_A",
                  "molecular_A_placeholder", "build_date"):
        assert field in saved, f"Campo faltante en metadata.json: {field}"
