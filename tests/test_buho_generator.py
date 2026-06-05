"""Tests para el generador heurístico de candidatos ABX3."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

CONFIG = ROOT / "config" / "generator.yaml"


def _gen(modes=None):
    """Crea un HeuristicGenerator con config mínima."""
    from buho.generator.heuristic_generator import HeuristicGenerator
    import yaml
    with open(CONFIG) as f:
        cfg = yaml.safe_load(f)
    if modes is not None:
        cfg["generation"]["modes"] = modes
    import tempfile, os
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as tf:
        import yaml as y
        y.dump(cfg, tf)
        tmp = tf.name
    gen = HeuristicGenerator(tmp)
    os.unlink(tmp)
    return gen


# ── Generación pura ────────────────────────────────────────────────────────────

def test_pure_count():
    """5 A-sites × 3 B-sites × 3 X-sites = 45 composiciones puras."""
    gen = _gen(modes={"pure": True, "A_mixed": False, "B_mixed": False,
                       "X_mixed": False, "multi_mixed": False})
    candidates = gen.generate()
    assert len(candidates) == 45, f"Esperados 45 puros, obtenidos {len(candidates)}"
    assert all(c.generation_mode == "pure" for c in candidates)


def test_pure_all_modes_correct():
    """Todas las composiciones puras tienen exactamente 1 especie por sitio."""
    gen = _gen(modes={"pure": True, "A_mixed": False, "B_mixed": False,
                       "X_mixed": False, "multi_mixed": False})
    for c in gen.generate():
        assert len(c.A_site_species) == 1
        assert len(c.B_site_species) == 1
        assert len(c.X_site_species) == 1


# ── Fracciones en mezclas ──────────────────────────────────────────────────────

def test_A_mixed_fractions_sum_to_one():
    """Las fracciones A-site suman exactamente 1 en mezclas."""
    gen = _gen(modes={"pure": False, "A_mixed": True, "B_mixed": False,
                       "X_mixed": False, "multi_mixed": False})
    for c in gen.generate():
        total = sum(c.fractions["A"].values())
        assert abs(total - 1.0) < 1e-6, f"{c.formula}: suma A = {total}"


def test_B_mixed_charge_neutral():
    """Las mezclas B-site preservan neutralidad de carga."""
    from ml_surrogate.features import CHARGES
    gen = _gen(modes={"pure": False, "A_mixed": False, "B_mixed": True,
                       "X_mixed": False, "multi_mixed": False})
    for c in gen.generate():
        qA = sum(CHARGES[sp] * c.fractions["A"].get(sp, 0) for sp in c.A_site_species)
        qB = sum(CHARGES[sp] * c.fractions["B"].get(sp, 0) for sp in c.B_site_species)
        qX = sum(CHARGES[sp] * c.fractions["X"].get(sp, 0) for sp in c.X_site_species)
        net = qA + qB + 3.0 * qX
        assert abs(net) < 0.05, f"{c.formula}: carga neta = {net:.4f}"


def test_X_mixed_fractions_sum_to_one():
    """Las fracciones X-site suman 1 en mezclas."""
    gen = _gen(modes={"pure": False, "A_mixed": False, "B_mixed": False,
                       "X_mixed": True, "multi_mixed": False})
    for c in gen.generate():
        total = sum(c.fractions["X"].values())
        assert abs(total - 1.0) < 1e-6, f"{c.formula}: suma X = {total}"


# ── Unicidad de IDs ────────────────────────────────────────────────────────────

def test_candidate_id_stable():
    """El mismo candidato generado dos veces produce el mismo ID."""
    from buho.generator.heuristic_generator import HeuristicGenerator
    gen = _gen()
    c1 = gen._make_candidate(
        A_sp=["Cs"], B_sp=["Pb"], X_sp=["I"],
        A_f={"Cs": 1.0}, B_f={"Pb": 1.0}, X_f={"I": 1.0},
        mode="pure",
    )
    c2 = gen._make_candidate(
        A_sp=["Cs"], B_sp=["Pb"], X_sp=["I"],
        A_f={"Cs": 1.0}, B_f={"Pb": 1.0}, X_f={"I": 1.0},
        mode="pure",
    )
    assert c1 is not None and c2 is not None
    assert c1.candidate_id == c2.candidate_id


def test_candidate_id_different_for_different_composition():
    """Composiciones distintas producen IDs distintos."""
    gen = _gen()
    c1 = gen._make_candidate(
        A_sp=["Cs"], B_sp=["Pb"], X_sp=["I"],
        A_f={"Cs": 1.0}, B_f={"Pb": 1.0}, X_f={"I": 1.0}, mode="pure",
    )
    c2 = gen._make_candidate(
        A_sp=["Cs"], B_sp=["Pb"], X_sp=["Br"],
        A_f={"Cs": 1.0}, B_f={"Pb": 1.0}, X_f={"Br": 1.0}, mode="pure",
    )
    assert c1 is not None and c2 is not None
    assert c1.candidate_id != c2.candidate_id


def test_deduplication():
    """El pipeline completo no contiene candidatos con IDs repetidos."""
    gen = _gen()
    candidates = gen.generate()
    ids = [c.candidate_id for c in candidates]
    assert len(ids) == len(set(ids)), "Hay candidatos duplicados después de deduplicate()"


# ── Serialización ──────────────────────────────────────────────────────────────

def test_jsonl_roundtrip(tmp_path):
    """Los candidatos se pueden guardar y cargar sin pérdida de datos."""
    from buho.generator.heuristic_generator import HeuristicGenerator
    gen = _gen(modes={"pure": True, "A_mixed": False, "B_mixed": False,
                       "X_mixed": False, "multi_mixed": False})
    candidates = gen.generate()[:5]

    out = tmp_path / "test.jsonl"
    HeuristicGenerator.save_jsonl(candidates, out)
    loaded = HeuristicGenerator.load_jsonl(out)

    assert len(loaded) == 5
    for orig, back in zip(candidates, loaded):
        assert orig.candidate_id == back.candidate_id
        assert orig.formula == back.formula
        assert abs(orig.tolerance_t - back.tolerance_t) < 1e-8
