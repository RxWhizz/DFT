"""Surrogate-based Bayesian acquisition — drop-in replacement for GNNAcquisition.

SurrogateAcquisition is backward-compatible with GNNAcquisition:
  - Same output: AcquisitionScore dataclass
  - Same rank() and score_one() API
  - Works with HTSCandidate objects from hts-perovskite
  - Trained on experimental bandgap data (26 materials from MP + literature)

Difference from GNNAcquisition:
  - No crystal structure required (composition-only)
  - No MATGL / MEGNet dependency
  - Explicit uncertainty from bootstrap ensemble
  - Falls back to heuristic scoring if model not trained yet
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import pandas as pd

from ml_surrogate.config import SurrogateConfig
from ml_surrogate.features import BASE_FEATURES, build_X, extract, from_candidate, from_dict
from ml_surrogate.model import SurrogateEnsemble

_PV_CENTER = 1.45
_PV_SIGMA  = 0.35
_STAB_SCALE = 0.5


@dataclass(frozen=True)
class SurrogateScore:
    """Per-candidate acquisition score from the surrogate model."""
    material: str
    Eg_pred: float
    Eg_uncertainty: float
    Eform_pred: Optional[float]
    band_score: float       # Gaussian proximity to PV optimum
    stab_score: float       # sigmoid stability score
    ucb_bonus: float        # beta * uncertainty
    total_score: float
    in_pv_window: bool
    model_source: str       # "surrogate" | "heuristic_fallback"


class SurrogateAcquisition:
    """UCB acquisition driven by the trained surrogate ensemble.

    Parameters
    ----------
    beta : UCB exploration weight (higher → more exploration)
    cfg  : SurrogateConfig (auto-loads from configs/surrogate.yaml if None)
    model_path : direct path to .pkl model file (overrides cfg)
    """

    def __init__(
        self,
        beta: float = 1.0,
        cfg: Optional[SurrogateConfig] = None,
        model_path: Optional[Path] = None,
    ) -> None:
        self.beta = beta
        self._cfg = cfg or SurrogateConfig()
        self._model: Optional[SurrogateEnsemble] = None
        self._model_path = model_path or self._cfg.model_path
        self._load_model()

    def _load_model(self) -> None:
        if self._model_path.exists():
            try:
                self._model = SurrogateEnsemble.load(self._model_path)
            except Exception as e:
                import warnings
                warnings.warn(f"SurrogateAcquisition: could not load model: {e}. "
                              f"Using heuristic fallback.")
                self._model = None
        else:
            import warnings
            warnings.warn(
                f"SurrogateAcquisition: model not found at {self._model_path}. "
                f"Train first: python -m src.ml_surrogate.train\n"
                f"Using heuristic fallback (B_BASE + X_SHIFT).",
                stacklevel=2,
            )

    def _score_heuristic(self, mat: str, A: str, B: str, X: str) -> SurrogateScore:
        """Legacy heuristic fallback when model not available."""
        _B_BASE = {"Pb": 1.50, "Sn": 1.30, "Ge": 2.00}
        _X_SHIFT = {"I": 0.00, "Br": 0.30, "Cl": 0.60}
        Eg = _B_BASE.get(B, 1.5) + _X_SHIFT.get(X, 0.0)
        band_score = float(np.exp(-0.5 * ((Eg - _PV_CENTER) / _PV_SIGMA) ** 2))
        return SurrogateScore(
            material=mat, Eg_pred=Eg, Eg_uncertainty=0.5,
            Eform_pred=None, band_score=round(band_score, 4),
            stab_score=0.5, ucb_bonus=round(self.beta * 0.5, 4),
            total_score=round(band_score + 0.5 + self.beta * 0.5, 4),
            in_pv_window=(1.1 <= Eg <= 1.8), model_source="heuristic_fallback",
        )

    def score_one(self, mat: str, A: str, B: str, X: str,
                  candidate=None, extra_feats: Optional[dict] = None) -> SurrogateScore:
        """Score one candidate material.

        Parameters
        ----------
        mat : material label (e.g. "CsPbI3")
        A, B, X : site elements
        candidate : optional HTSCandidate object (uses x_I/x_Br/x_Cl fractions)
        extra_feats : optional dict with keys a_lat_mp_A, E_mace_eV_atom, etc.
        """
        if self._model is None:
            return self._score_heuristic(mat, A, B, X)

        # Build feature dict
        if candidate is not None:
            feat_dict = from_candidate(candidate)
        else:
            feat_dict = extract(A, B, X)

        if extra_feats:
            for k, v in extra_feats.items():
                if k in feat_dict:
                    feat_dict[k] = v

        # Build feature matrix using model's expected column order
        df_row = pd.DataFrame([feat_dict])
        try:
            X_arr = build_X(df_row, self._model.feature_cols)
            Eg, std = self._model.predict_single(X_arr[0])
        except Exception as e:
            import warnings
            warnings.warn(f"Surrogate prediction failed for {mat}: {e}")
            return self._score_heuristic(mat, A, B, X)

        band_score = float(np.exp(-0.5 * ((Eg - _PV_CENTER) / _PV_SIGMA) ** 2))
        stab_score = 0.5   # no Eform from composition-only surrogate
        ucb_bonus = self.beta * std

        return SurrogateScore(
            material=mat,
            Eg_pred=round(Eg, 4),
            Eg_uncertainty=round(std, 4),
            Eform_pred=None,
            band_score=round(band_score, 4),
            stab_score=stab_score,
            ucb_bonus=round(ucb_bonus, 4),
            total_score=round(band_score + stab_score + ucb_bonus, 4),
            in_pv_window=(1.1 <= Eg <= 1.8),
            model_source="surrogate",
        )

    def score_from_dict(self, mat: str, d: dict) -> SurrogateScore:
        """Score from a flat dict (e.g. ai_predictions.json row)."""
        feat_dict = from_dict(d)
        A, B, X = d["A"], d["B"], d.get("X", "I")
        if self._model is None:
            return self._score_heuristic(mat, A, B, X)

        df_row = pd.DataFrame([feat_dict])
        try:
            X_arr = build_X(df_row, self._model.feature_cols)
            Eg, std = self._model.predict_single(X_arr[0])
        except Exception:
            return self._score_heuristic(mat, A, B, X)

        band_score = float(np.exp(-0.5 * ((Eg - _PV_CENTER) / _PV_SIGMA) ** 2))
        ucb_bonus = self.beta * std
        return SurrogateScore(
            material=mat, Eg_pred=round(Eg, 4), Eg_uncertainty=round(std, 4),
            Eform_pred=None, band_score=round(band_score, 4),
            stab_score=0.5, ucb_bonus=round(ucb_bonus, 4),
            total_score=round(band_score + 0.5 + ucb_bonus, 4),
            in_pv_window=(1.1 <= Eg <= 1.8), model_source="surrogate",
        )

    def rank(
        self,
        materials: Sequence[str],
        candidates,   # Sequence of HTSCandidate or dicts
    ) -> list[SurrogateScore]:
        """Rank all candidates by total_score descending."""
        scores = []
        for mat, cand in zip(materials, candidates):
            if hasattr(cand, "A"):
                s = self.score_one(mat, cand.A, cand.B, cand.X, candidate=cand)
            elif isinstance(cand, dict):
                s = self.score_from_dict(mat, cand)
            else:
                s = self._score_heuristic(mat, str(mat)[:2], "Pb", "I")
            scores.append(s)
        return sorted(scores, key=lambda s: s.total_score, reverse=True)

    def to_feature_vector(self, candidate, extra_feats: Optional[dict] = None) -> list[float]:
        """8D feature vector for HTSSurrogateNode MLP.

        Extends HTSCandidate.to_feature_vector() (6D) with [Eg_pred, 0.0].
        """
        base = candidate.to_feature_vector()     # [r_A, r_B, r_X, q_A, q_B, q_X]
        mat = getattr(candidate, "formula", f"{candidate.A}{candidate.B}{candidate.X}3")
        score = self.score_one(mat, candidate.A, candidate.B, candidate.X,
                               candidate=candidate, extra_feats=extra_feats)
        return base + [score.Eg_pred, 0.0]       # Eform slot: 0.0 (not predicted)
