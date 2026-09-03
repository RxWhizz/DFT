"""Finite chemical-space enumeration for autonomous discovery."""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from buho.filters.physical_filters import PhysicalFilter
from buho.generator.heuristic_generator import GeneratedCandidate, HeuristicGenerator


@dataclass(frozen=True)
class SpaceStats:
    total_generated: int
    physically_viable: int
    rejected_physical: int
    fraction_step: float
    min_fraction: float
    max_fraction: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_generated": self.total_generated,
            "physically_viable": self.physically_viable,
            "rejected_physical": self.rejected_physical,
            "fraction_step": self.fraction_step,
            "min_fraction": self.min_fraction,
            "max_fraction": self.max_fraction,
        }


def fraction_grid(min_fraction: float, max_fraction: float, step: float) -> list[float]:
    """Build a stable composition grid inside the open mixed-composition range."""
    if step <= 0:
        raise ValueError("fraction_step must be positive")
    start = math.ceil((min_fraction - 1e-9) / step)
    end = math.floor((max_fraction + 1e-9) / step)
    values = [round(i * step, 4) for i in range(start, end + 1)]
    return [v for v in values if 0.0 < v < 1.0]


class ChemicalSpaceEnumerator:
    """Enumerate a finite ABX3 space using the existing generator semantics."""

    def __init__(self, config_path: str | Path | dict[str, Any] = "config/generator.yaml"):
        if isinstance(config_path, dict):
            self.config_path = None
            self.config = copy.deepcopy(config_path)
        else:
            self.config_path = Path(config_path)
            with self.config_path.open(encoding="utf-8") as fh:
                self.config = yaml.safe_load(fh) or {}
        disc = self.config.get("discovery", {}) or {}
        space = disc.get("space", {}) or {}
        self.fraction_step = float(space.get("fraction_step", 0.01))
        self.min_fraction = float(space.get("min_fraction", 0.05))
        self.max_fraction = float(space.get("max_fraction", 0.95))
        self.include_multi_mixed = bool(space.get("include_multi_mixed", False))

    def enumeration_config(self) -> dict[str, Any]:
        """Return a config copy that turns stochastic sampling into a finite grid."""
        cfg = copy.deepcopy(self.config)
        gen = cfg.setdefault("generation", {})
        gen["fraction_mode"] = "discrete"
        gen["fractions"] = fraction_grid(self.min_fraction, self.max_fraction, self.fraction_step)
        modes = dict(gen.get("modes", {}) or {})
        modes.setdefault("pure", True)
        modes.setdefault("A_mixed", True)
        modes.setdefault("B_mixed", True)
        modes.setdefault("X_mixed", True)
        modes["multi_mixed"] = self.include_multi_mixed
        gen["modes"] = modes
        return cfg

    def enumerate(self, *, physical_viable_only: bool = True) -> tuple[list[GeneratedCandidate], SpaceStats]:
        cfg = self.enumeration_config()
        candidates = HeuristicGenerator(cfg).generate()
        filtered = PhysicalFilter(cfg).apply(candidates)
        viable = filtered.passed if physical_viable_only else candidates
        stats = SpaceStats(
            total_generated=len(candidates),
            physically_viable=len(filtered.passed),
            rejected_physical=len(filtered.rejected),
            fraction_step=self.fraction_step,
            min_fraction=self.min_fraction,
            max_fraction=self.max_fraction,
        )
        return viable, stats
