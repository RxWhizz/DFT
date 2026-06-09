"""Tests para los filtros físicos de candidatos ABX3."""
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
    """Helper: crea un candidato simple."""
    from buho.generator.heuristic_generator import HeuristicGenerator
    gen = HeuristicGenerator(CONFIG)
    return gen._make_candidate(
        A_sp=[A], B_sp=[B], X_sp=[X],
        A_f={A: 1.0}, B_f={B: 1.0}, X_f={X: 1.0},
        mode=mode,
    )


def _make_filter(overrides=None):
    from buho.filters.physical_filters import PhysicalFilter
    cfg = _load_cfg()
    if overrides:
        for k, v in overrides.items():
            cfg["filters"][k] = v
    return PhysicalFilter(cfg)


# ── Neutralidad de carga ───────────────────────────────────────────────────────

def test_charge_neutral_passes():
    """CsPbI3 pasa el filtro de carga."""
    filt = _make_filter()
    c = _make_candidate("Cs", "Pb", "I")
    assert c is not None
    ok, reason = filt._check_charge(c)
    assert ok, f"Debería pasar: {reason}"


def test_invalid_species_rejected():
    """Candidato con especie sin datos es rechazado antes que pase a otros filtros."""
    from buho.generator.heuristic_generator import GeneratedCandidate
    # Crear candidato con especie inventada
    c = GeneratedCandidate(
        formula="XxPbI3", reduced_formula="XxPbI3",
        composition_dict={}, A_site_species=["Xx"],
        B_site_species=["Pb"], X_site_species=["I"],
        fractions={"A": {"Xx": 1.0}, "B": {"Pb": 1.0}, "X": {"I": 1.0}},
        candidate_id="fakeid", generation_mode="pure",
        tolerance_t=0.9, oct_factor=0.54,
        a0_est_A=6.3, vol_est_A3=250.0, is_organic_A=False,
    )
    filt = _make_filter()
    ok, reason = filt._check_species(c)
    assert not ok, "Especie inválida debería ser rechazada"
    assert "Xx" in reason


# ── Goldschmidt ───────────────────────────────────────────────────────────────

def test_goldschmidt_in_range_passes():
    """CsPbI3 tiene t ≈ 0.81, debe pasar con default [0.80, 1.10]."""
    filt = _make_filter()
    c = _make_candidate("Cs", "Pb", "I")
    ok, reason = filt._check_goldschmidt(c)
    assert ok, f"CsPbI3 debería pasar Goldschmidt: t={c.tolerance_t}"


def test_goldschmidt_below_min_rejected():
    """Factor t muy bajo es rechazado."""
    from buho.generator.heuristic_generator import GeneratedCandidate
    c = _make_candidate("Cs", "Ge", "Cl")  # Ge/Cl → t pequeño
    if c is None:
        pytest.skip("Combinación inválida de carga")
    filt = _make_filter({"goldschmidt": {"min": 0.95, "max": 1.10}})
    ok, reason = filt._check_goldschmidt(c)
    if c.tolerance_t < 0.95:
        assert not ok
    else:
        assert ok  # si pasa el rango, es correcto también


def test_goldschmidt_above_max_rejected():
    """Factor t muy alto es rechazado."""
    from buho.generator.heuristic_generator import GeneratedCandidate
    c = _make_candidate("FA", "Pb", "I")  # FA tiene r_A grande → t alto
    if c is None:
        pytest.skip("Candidato inválido")
    filt = _make_filter({"goldschmidt": {"min": 0.80, "max": 0.88}})
    # FAPbI3 t ≈ 0.99 → debe ser rechazado con max=0.88
    ok, _ = filt._check_goldschmidt(c)
    if c.tolerance_t > 0.88:
        assert not ok


# ── Factor octaédrico ─────────────────────────────────────────────────────────

def test_octahedral_in_range_passes():
    """CsPbI3 μ = r_Pb/r_I ≈ 0.54, debe estar en [0.40, 0.90]."""
    filt = _make_filter()
    c = _make_candidate("Cs", "Pb", "I")
    ok, _ = filt._check_octahedral(c)
    assert ok, f"CsPbI3 debería pasar octaédrico: μ={c.oct_factor}"


def test_octahedral_ge_cl_small():
    """CsGeCl3: r_Ge=0.73, r_Cl=1.81 → μ=0.40, borderline."""
    filt = _make_filter()
    c = _make_candidate("Cs", "Ge", "Cl")
    if c is None:
        pytest.skip("CsGeCl3 inválido de carga")
    # μ ≈ 0.73/1.81 ≈ 0.403 → debería pasar con min=0.40
    ok, _ = filt._check_octahedral(c)
    assert ok or c.oct_factor < 0.40  # tolerable en borde


# ── Pipeline completo ─────────────────────────────────────────────────────────

def test_filter_pipeline_20_candidates():
    """Pipeline completo con 20 candidatos: al menos algunos pasan."""
    from buho.generator.heuristic_generator import HeuristicGenerator
    from buho.filters.physical_filters import PhysicalFilter

    gen = HeuristicGenerator(CONFIG)
    candidates = gen._generate_pure()[:20]

    cfg = _load_cfg()
    filt = PhysicalFilter(cfg)
    result = filt.apply(candidates)

    assert result.n_passed + result.n_rejected == len(candidates)
    assert result.n_passed > 0, "Al menos algunos candidatos deberían pasar"
    assert "goldschmidt" in result.stats


def test_filter_stats_complete():
    """El resultado incluye estadísticas de cada filtro."""
    from buho.generator.heuristic_generator import HeuristicGenerator
    from buho.filters.physical_filters import PhysicalFilter

    gen = HeuristicGenerator(CONFIG)
    candidates = gen.generate()[:50]
    cfg = _load_cfg()
    result = PhysicalFilter(cfg).apply(candidates)

    for key in ("goldschmidt", "octahedral", "total_in", "total_passed"):
        assert key in result.stats, f"Falta estadística: {key}"
