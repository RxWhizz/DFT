"""Tests del muestreo continuo + dedup por batches + cascada (Tier 0-1)."""
import os
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from buho.generator.heuristic_generator import HeuristicGenerator
from ml_surrogate.features import CHARGES

CONFIG = ROOT / "config" / "generator.yaml"


def _continuous_gen(n_samples=3):
    cfg = yaml.safe_load(CONFIG.read_text())
    cfg["generation"]["fraction_mode"] = "continuous"
    cfg["generation"]["n_samples_per_combo"] = n_samples
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as tf:
        yaml.safe_dump(cfg, tf)
        tmp = tf.name
    g = HeuristicGenerator(tmp)
    os.unlink(tmp)
    return g


def _charge_imbalance(c):
    qA = sum(CHARGES[s] * f for s, f in c.fractions["A"].items())
    qB = sum(CHARGES[s] * f for s, f in c.fractions["B"].items())
    qX = sum(CHARGES[s] * f for s, f in c.fractions["X"].items())
    return abs(qA + qB + 3.0 * qX)


def test_continuous_fractions_in_range():
    """Las fracciones de mezcla están en (0,1) y no en la grilla discreta."""
    g = _continuous_gen()
    batch = g.generate_batch(0, batch_size=300)
    mixed = [c for c in batch if c.generation_mode != "pure"]
    assert mixed, "debe haber candidatos mixtos"
    grid = {0.125, 0.25, 0.5, 0.75, 0.875}
    off_grid = 0
    for c in mixed:
        for site in ("A", "B", "X"):
            for f in c.fractions[site].values():
                assert 0.0 < f < 1.0001
                if 0.01 < f < 0.99 and round(f, 3) not in grid:
                    off_grid += 1
    assert off_grid > 0, "el muestreo continuo debe producir fracciones fuera de la grilla"


def test_continuous_charge_neutral():
    g = _continuous_gen()
    batch = g.generate_batch(0, batch_size=300)
    assert max(_charge_imbalance(c) for c in batch) < 0.05


def test_cross_batch_dedup_via_registry(tmp_path):
    """El registro persistente evita IDs repetidos entre batches."""
    g = _continuous_gen()
    reg = tmp_path / "registry.txt"
    b0 = g.generate_batch(0, batch_size=150, registry_path=reg)
    b1 = g.generate_batch(1, batch_size=150, registry_path=reg)
    ids0 = {c.candidate_id for c in b0}
    ids1 = {c.candidate_id for c in b1}
    assert ids0 and ids1
    assert ids0.isdisjoint(ids1), "no debe haber IDs repetidos entre batches"
    # el registro contiene la unión
    seen = {ln.strip() for ln in reg.read_text().splitlines() if ln.strip()}
    assert ids0 | ids1 <= seen


def test_batch_reproducible():
    """Mismo batch_id ⇒ mismos candidate_ids."""
    g1 = _continuous_gen()
    g2 = _continuous_gen()
    a = {c.candidate_id for c in g1.generate_batch(5, batch_size=100)}
    b = {c.candidate_id for c in g2.generate_batch(5, batch_size=100)}
    assert a == b


def test_batch_size_cap():
    g = _continuous_gen(n_samples=8)
    batch = g.generate_batch(0, batch_size=50)
    assert len(batch) <= 50


def test_discrete_mode_unchanged():
    """El modo discreto sigue dando exactamente 45 puros (5×3×3)."""
    cfg = yaml.safe_load(CONFIG.read_text())
    cfg["generation"]["fraction_mode"] = "discrete"
    cfg["generation"]["modes"] = {"pure": True, "A_mixed": False,
                                  "B_mixed": False, "X_mixed": False,
                                  "multi_mixed": False}
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as tf:
        yaml.safe_dump(cfg, tf)
        tmp = tf.name
    g = HeuristicGenerator(tmp)
    os.unlink(tmp)
    assert len(g.generate()) == 45


def test_cascade_tier01_smoke():
    """La cascada Tier 0-1 (sin MLFF) puebla los indicadores baratos."""
    from buho.screening.cascade import ScreeningCascade
    cfg = yaml.safe_load(CONFIG.read_text())
    g = _continuous_gen(n_samples=1)
    batch = g.generate_batch(0, batch_size=10)
    casc = ScreeningCascade(cfg, project_root=ROOT)
    df = casc.screen(batch, run_mlff=False)
    assert len(df) > 0
    for col in ("Eg_surrogate_eV", "band_score", "total_score", "tier_reached"):
        assert col in df.columns
    assert df["total_score"].is_monotonic_decreasing  # rankeado desc
