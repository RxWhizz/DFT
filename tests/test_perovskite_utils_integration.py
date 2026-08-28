"""Contrato de integración gradual con perovskite-utils."""
from __future__ import annotations

from pathlib import Path

from perovowl.generate import HeuristicGenerator as PerovowlGenerator

from buho.generator.heuristic_generator import HeuristicGenerator as LegacyGenerator

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "generator.yaml"


def _cspbi3(gen: LegacyGenerator | PerovowlGenerator):
    return gen._make_candidate(
        A_sp=["Cs"],
        B_sp=["Pb"],
        X_sp=["I"],
        A_f={"Cs": 1.0},
        B_f={"Pb": 1.0},
        X_f={"I": 1.0},
        mode="pure",
    )


def test_perovskite_utils_pin_exports_generator() -> None:
    assert PerovowlGenerator.__name__ == "HeuristicGenerator"
    assert PerovowlGenerator.__module__.startswith("perovowl.")


def test_legacy_and_perovowl_generators_keep_candidate_contract() -> None:
    legacy = _cspbi3(LegacyGenerator(CONFIG))
    perovowl = _cspbi3(PerovowlGenerator(CONFIG))

    assert legacy is not None
    assert perovowl is not None
    assert legacy.formula == perovowl.formula == "CsPbI3"
    assert legacy.reduced_formula == perovowl.reduced_formula
    assert legacy.candidate_id == perovowl.candidate_id == "96ceaca4b84921f7"
