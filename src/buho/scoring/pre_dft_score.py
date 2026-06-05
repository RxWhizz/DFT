"""Score preliminar pre-DFT para seleccionar candidatos a calcular.

El score es un indicador heurístico normalizado [0, 1] que combina:
  - Cercanía del factor de Goldschmidt a 1 (estructura más estable)
  - Factor octaédrico dentro del rango favorable
  - Confiabilidad del elemento B (datos experimentales disponibles)
  - Volumen estimado razonable
  - Bonus de diversidad por modo de generación

NO representa una predicción de bandgap ni de estabilidad — es solo un
criterio de selección para priorizar cálculos DFT básicos.

Uso:
    scorer = PreDFTScorer(config)
    scores = scorer.score_all(candidates)
    top500 = scorer.select_top(candidates, n=500)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from buho.generator.heuristic_generator import GeneratedCandidate


@dataclass
class ScoredCandidate:
    candidate: GeneratedCandidate
    pre_dft_score: float
    t_score: float
    mu_score: float
    b_score: float
    vol_score: float
    mode_bonus: float


# Confiabilidad de elemento B (datos de literatura disponibles)
_B_RELIABILITY = {"Pb": 1.0, "Sn": 0.90, "Ge": 0.70}
_B_DEFAULT = 0.50

# Bonus por diversidad de modo de generación
_MODE_BONUS = {
    "pure": 0.0,
    "A_mixed": 0.05,
    "B_mixed": 0.03,
    "X_mixed": 0.05,
    "multi_mixed": 0.02,
}


class PreDFTScorer:
    """Asigna y ordena candidatos por score pre-DFT.

    Parámetros
    ----------
    config : dict completo de generator.yaml (usa secciones "filters" y "scoring")
    """

    def __init__(self, config: dict):
        f = config.get("filters", {})
        self._mu_min = float(f.get("octahedral", {}).get("min", 0.40))
        self._mu_max = float(f.get("octahedral", {}).get("max", 0.90))
        self._vol_min = float(f.get("volume_A3", {}).get("min", 50.0))
        self._vol_max = float(f.get("volume_A3", {}).get("max", 2000.0))

    def score_one(self, c: GeneratedCandidate) -> ScoredCandidate:
        t = c.tolerance_t
        mu = c.oct_factor
        vol = c.vol_est_A3

        # Goldschmidt: Gaussiana centrada en t=1.0, σ=0.10
        t_score = math.exp(-((t - 1.0) / 0.10) ** 2)

        # Octaédrico: 1.0 si dentro del rango, 0.0 si no
        mu_score = 1.0 if self._mu_min <= mu <= self._mu_max else 0.0

        # Confiabilidad del B-site
        b_scores = [_B_RELIABILITY.get(sp, _B_DEFAULT) for sp in c.B_site_species]
        b_score = sum(
            b_scores[i] * c.fractions["B"].get(c.B_site_species[i], 0.0)
            for i in range(len(c.B_site_species))
        )

        # Volumen: lineal dentro del rango, penalización suave fuera
        v_range = self._vol_max - self._vol_min
        if self._vol_min <= vol <= self._vol_max:
            vol_score = 1.0
        else:
            dist = min(abs(vol - self._vol_min), abs(vol - self._vol_max))
            vol_score = max(0.0, 1.0 - dist / v_range)

        mode_bonus = _MODE_BONUS.get(c.generation_mode, 0.0)

        score = (0.40 * t_score
               + 0.25 * mu_score
               + 0.20 * b_score
               + 0.10 * vol_score
               + 0.05 * mode_bonus)

        return ScoredCandidate(
            candidate=c,
            pre_dft_score=round(score, 5),
            t_score=round(t_score, 5),
            mu_score=round(mu_score, 5),
            b_score=round(b_score, 5),
            vol_score=round(vol_score, 5),
            mode_bonus=round(mode_bonus, 5),
        )

    def score_all(self, candidates: list[GeneratedCandidate]) -> list[ScoredCandidate]:
        return [self.score_one(c) for c in candidates]

    def select_top(
        self, candidates: list[GeneratedCandidate], n: int
    ) -> list[ScoredCandidate]:
        scored = self.score_all(candidates)
        scored.sort(key=lambda s: -s.pre_dft_score)
        return scored[:n]

    @staticmethod
    def to_dataframe(scored: list[ScoredCandidate]) -> pd.DataFrame:
        rows = []
        for s in scored:
            c = s.candidate
            rows.append({
                "candidate_id": c.candidate_id,
                "formula": c.formula,
                "reduced_formula": c.reduced_formula,
                "generation_mode": c.generation_mode,
                "A_sites": "|".join(c.A_site_species),
                "B_sites": "|".join(c.B_site_species),
                "X_sites": "|".join(c.X_site_species),
                "is_organic_A": c.is_organic_A,
                "tolerance_t": c.tolerance_t,
                "oct_factor": c.oct_factor,
                "a0_est_A": c.a0_est_A,
                "vol_est_A3": c.vol_est_A3,
                "pre_dft_score": s.pre_dft_score,
                "t_score": s.t_score,
                "mu_score": s.mu_score,
                "b_score": s.b_score,
                "vol_score": s.vol_score,
                "mode_bonus": s.mode_bonus,
            })
        return pd.DataFrame(rows)
