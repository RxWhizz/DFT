"""Seleccion de modos del pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PipelineMode(str, Enum):
    """Modos soportados por el pipeline."""

    SURROGATE_ONLY = "surrogate_only"
    DFT_ONLY = "dft_only"
    HYBRID = "hybrid"


@dataclass(frozen=True)
class PipelinePlan:
    """Plan minimo derivado del modo de ejecucion."""

    mode: PipelineMode
    run_surrogate: bool
    run_dft: bool
    allow_candidate_filtering: bool


def normalize_mode(mode: str | PipelineMode) -> PipelineMode:
    """Valida y normaliza el modo del pipeline."""
    if isinstance(mode, PipelineMode):
        return mode
    normalized = str(mode).strip().lower().replace("-", "_")
    try:
        return PipelineMode(normalized)
    except ValueError as exc:
        valid = ", ".join(item.value for item in PipelineMode)
        raise ValueError(f"Modo de pipeline desconocido: {mode!r}. Opciones: {valid}") from exc


def plan_for_mode(mode: str | PipelineMode) -> PipelinePlan:
    """Devuelve las acciones habilitadas para un modo."""
    selected = normalize_mode(mode)
    if selected is PipelineMode.SURROGATE_ONLY:
        return PipelinePlan(selected, run_surrogate=True, run_dft=False, allow_candidate_filtering=True)
    if selected is PipelineMode.DFT_ONLY:
        return PipelinePlan(selected, run_surrogate=False, run_dft=True, allow_candidate_filtering=False)
    return PipelinePlan(selected, run_surrogate=True, run_dft=True, allow_candidate_filtering=True)


def mode_requires_dft(mode: str | PipelineMode) -> bool:
    """Indica si el modo requiere ejecutar o preparar DFT."""
    return plan_for_mode(mode).run_dft

