"""Runner aditivo para evaluacion surrogate."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from .cache import SQLiteCache, stable_key
from .candidates import ABX3Candidate


@dataclass(frozen=True)
class SurrogatePrediction:
    """Prediccion surrogate serializable."""

    material: str
    bandgap_eV: float
    uncertainty_eV: float
    total_score: float
    model_source: str
    in_pv_window: bool


class SurrogateRunner:
    """Evalua candidatos con el surrogate existente sin tocar DFT."""

    def __init__(self, beta: float = 1.0, cache_path: str | Path | None = None) -> None:
        self.beta = beta
        self.cache = SQLiteCache(cache_path) if cache_path else None
        self._acquisition = None

    @property
    def acquisition(self):
        """Carga diferida del surrogate para evitar dependencias en import."""
        if self._acquisition is None:
            from ml_surrogate.integration import SurrogateAcquisition

            self._acquisition = SurrogateAcquisition(beta=self.beta)
        return self._acquisition

    def score_candidate(self, candidate: ABX3Candidate) -> SurrogatePrediction:
        """Evalua un candidato ABX3 con cache opcional."""
        key = stable_key(("surrogate", str(self.beta), candidate.formula))
        if self.cache is not None:
            cached = self.cache.get(key)
            if cached is not None:
                return SurrogatePrediction(**cached)

        score = self.acquisition.score_one(candidate.formula, candidate.A, candidate.B, candidate.X)
        prediction = SurrogatePrediction(
            material=candidate.formula,
            bandgap_eV=float(score.Eg_pred),
            uncertainty_eV=float(score.Eg_uncertainty),
            total_score=float(score.total_score),
            model_source=str(score.model_source),
            in_pv_window=bool(score.in_pv_window),
        )
        if self.cache is not None:
            self.cache.set(key, asdict(prediction))
        return prediction

    def rank(self, candidates: Iterable[ABX3Candidate]) -> list[SurrogatePrediction]:
        """Ordena candidatos por score descendente."""
        predictions = [self.score_candidate(candidate) for candidate in candidates]
        return sorted(predictions, key=lambda item: item.total_score, reverse=True)

