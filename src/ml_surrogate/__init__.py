"""ML surrogate for ABX3 halide perovskite screening — BUHO pipeline.

Two interchangeable backends:

  1. SurrogateEnsemble (RF + GBR, composition-only)  ← PRIMARY, no GNN required
     Trained on 26 ABX3 materials from Materials Project + experimental literature.
     Predicts experimental bandgap with LOO-CV MAE ≈ 0.15–0.25 eV.
     Usage: python -m src.ml_surrogate.train / predict

  2. GNNAcquisition (MEGNet + M3GNet via MATGL)  ← GNN backend, structure required
     Requires crystal structure; predicts formation energy for stability score.
     Usage: python -m src.ml_surrogate.inference

Heuristics replaced by this module:
  - Bandgap (B_BASE + X_SHIFT)           →  SurrogateEnsemble
  - AINAGENT acquisition (band+gold)     →  SurrogateAcquisition / GNNAcquisition
  - Goldschmidt stability (t factor)     →  SurrogateAcquisition (stab_score)
"""
from __future__ import annotations

# ── Surrogate (composition-only, primary) ─────────────────────────────────────
from ml_surrogate.config import SurrogateConfig
from ml_surrogate.features import extract as extract_features, from_candidate, BASE_FEATURES
from ml_surrogate.model import SurrogateEnsemble, make_prediction_record
from ml_surrogate.integration import SurrogateAcquisition, SurrogateScore

# ── GNN backend (structure-based, optional) ───────────────────────────────────
from ml_surrogate.gnn_predictor import GNNPredictor, GNNResult
from ml_surrogate.structure_builder import PerovskiteStructureBuilder
from ml_surrogate.bayes_optimizer import GNNAcquisition, AcquisitionScore
from ml_surrogate.dataset import GNNPredictionCache, PredictionRecord

__all__ = [
    # Surrogate (composition-only)
    "SurrogateConfig",
    "SurrogateEnsemble",
    "SurrogateAcquisition",
    "SurrogateScore",
    "extract_features",
    "from_candidate",
    "BASE_FEATURES",
    "make_prediction_record",
    # GNN backend
    "GNNPredictor",
    "GNNResult",
    "PerovskiteStructureBuilder",
    "GNNAcquisition",
    "AcquisitionScore",
    "GNNPredictionCache",
    "PredictionRecord",
]
