"""Pruebas para seleccion conservadora de modos."""

from __future__ import annotations

import pytest

from dft_cspbi3.pipeline_modes import PipelineMode, mode_requires_dft, normalize_mode, plan_for_mode


def test_normalize_mode_accepts_hyphen_alias() -> None:
    assert normalize_mode("surrogate-only") is PipelineMode.SURROGATE_ONLY


def test_surrogate_only_plan_skips_dft() -> None:
    plan = plan_for_mode("surrogate_only")
    assert plan.run_surrogate is True
    assert plan.run_dft is False
    assert plan.allow_candidate_filtering is True


def test_dft_only_plan_skips_surrogate() -> None:
    plan = plan_for_mode("dft_only")
    assert plan.run_surrogate is False
    assert plan.run_dft is True
    assert plan.allow_candidate_filtering is False


def test_hybrid_plan_runs_both() -> None:
    plan = plan_for_mode("hybrid")
    assert plan.run_surrogate is True
    assert plan.run_dft is True
    assert mode_requires_dft("hybrid") is True


def test_invalid_mode_raises_clear_error() -> None:
    with pytest.raises(ValueError, match="Modo de pipeline desconocido"):
        normalize_mode("unknown")

