"""GNN-based Bayesian acquisition — replaces semi-empirical step_ainagent_score().

Old heuristic (removed):
  band_score = exp(-0.5 * ((B_BASE[B] + X_SHIFT[X] - 1.45) / 0.35)^2)
  gold_score = exp(-0.5 * ((t_Goldschmidt - 0.90) / 0.12)^2)
  ai_score   = band_score + gold_score   # [0, 2]

New GNN-based UCB:
  band_score = exp(-0.5 * ((Eg_GNN - 1.45) / sigma_E)^2)   # [0, 1] from MEGNet
  stab_score = sigmoid(-Eform_GNN / kT_scale)               # [0, 1] from Eform ensemble
  ucb_bonus  = beta * Eform_std                              # [0, ~] exploration
  gnn_score  = band_score + stab_score + ucb_bonus           # [0, 3]

The feature vector for the surrogate MLP is extended from 6D to 8D:
  old: [r_A, r_B, r_X, charge_A, charge_B, charge_X]
  new: [r_A, r_B, r_X, charge_A, charge_B, charge_X, Eg_GNN, Eform_GNN]
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

from ml_surrogate.gnn_predictor import GNNResult

_PV_CENTER = 1.45   # eV — Shockley-Queisser optimum
_PV_SIGMA  = 0.35   # eV
_STAB_SCALE = 0.5   # eV/atom — Eform sigmoid scale factor


@dataclass(frozen=True)
class AcquisitionScore:
    material: str
    Eg_gnn: float
    Eform_gnn: Optional[float]
    Eform_std: Optional[float]
    band_score: float    # Gaussian proximity to PV window center
    stab_score: float    # sigmoid stability from Eform
    ucb_bonus: float     # beta * Eform ensemble uncertainty
    total_score: float
    in_pv_window: bool
    is_stable: bool
    structure_source: str


class GNNAcquisition:
    """UCB acquisition on GNN-predicted bandgap and formation energy.

    No heuristic inputs (no B_BASE, no Goldschmidt t factor).

    Parameters
    ----------
    beta : float
        UCB exploration coefficient. 0 → pure exploitation; 1–2 → balanced.
    sigma_E : float
        Bandgap Gaussian width (eV). Default 0.35 (half PV-window width).
    stability_scale : float
        Eform sigmoid scale (eV/atom). Controls how steeply stability drops
        near Eform=0. Default 0.5 eV/atom.
    """

    def __init__(
        self,
        beta: float = 1.0,
        sigma_E: float = _PV_SIGMA,
        stability_scale: float = _STAB_SCALE,
    ) -> None:
        self.beta = beta
        self.sigma_E = sigma_E
        self.stability_scale = stability_scale

    def score_one(self, mat: str, result: GNNResult) -> AcquisitionScore:
        Eg = result.Eg_eV

        band_score = float(np.exp(-0.5 * ((Eg - _PV_CENTER) / self.sigma_E) ** 2))

        if result.Eform_eV_atom is not None:
            stab_score = float(1.0 / (1.0 + math.exp(result.Eform_eV_atom / self.stability_scale)))
        else:
            stab_score = 0.5

        ucb_bonus = (
            self.beta * float(result.Eform_std_eV_atom)
            if result.Eform_std_eV_atom is not None
            else 0.0
        )

        total = band_score + stab_score + ucb_bonus

        return AcquisitionScore(
            material=mat,
            Eg_gnn=Eg,
            Eform_gnn=result.Eform_eV_atom,
            Eform_std=result.Eform_std_eV_atom,
            band_score=round(band_score, 4),
            stab_score=round(stab_score, 4),
            ucb_bonus=round(ucb_bonus, 4),
            total_score=round(total, 4),
            in_pv_window=result.in_pv_window,
            is_stable=result.is_stable,
            structure_source=result.structure_source,
        )

    def rank(
        self,
        materials: Sequence[str],
        results: Sequence[GNNResult],
    ) -> list[AcquisitionScore]:
        """Return list of AcquisitionScore sorted by total_score descending."""
        return sorted(
            (self.score_one(m, r) for m, r in zip(materials, results)),
            key=lambda s: s.total_score,
            reverse=True,
        )

    def to_feature_vector(self, result: GNNResult, candidate) -> list[float]:
        """Build 8D feature vector for surrogate MLP input.

        Extends HTSCandidate.to_feature_vector() (6D) with GNN predictions.
        Update HTSSurrogateNode input_dim to 8 when using this.
        """
        base = candidate.to_feature_vector()          # [r_A, r_B, r_X, q_A, q_B, q_X]
        Eg = result.Eg_eV if _finite(result.Eg_eV) else 1.5
        Ef = result.Eform_eV_atom if result.Eform_eV_atom is not None else 0.0
        return base + [Eg, Ef]


def _finite(v: float) -> bool:
    try:
        return math.isfinite(v)
    except Exception:
        return False
