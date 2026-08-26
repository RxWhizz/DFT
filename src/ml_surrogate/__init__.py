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
from ml_surrogate.features import BASE_FEATURES, from_candidate
from ml_surrogate.features import extract as extract_features
from ml_surrogate.integration import SurrogateAcquisition, SurrogateScore
from ml_surrogate.model import SurrogateEnsemble, make_prediction_record

# ── GNN backend (structure-based, optional) ───────────────────────────────────
# Carga perezosa (PEP 562): gnn_predictor importa torch, que este mismo
# docstring declara innecesario para el surrogate composicional. Importarlo de
# forma eager obligaba a instalar torch para predecir con un RandomForest, y
# rompía el `python -m src.ml_surrogate.predict` que documenta predict.py.
# `from ml_surrogate import GNNPredictor` sigue funcionando igual.
_LAZY_ATTRS = {
    "GNNPredictor": "ml_surrogate.gnn_predictor",
    "GNNResult": "ml_surrogate.gnn_predictor",
    "PerovskiteStructureBuilder": "ml_surrogate.structure_builder",
    "GNNAcquisition": "ml_surrogate.bayes_optimizer",
    "AcquisitionScore": "ml_surrogate.bayes_optimizer",
    "GNNPredictionCache": "ml_surrogate.dataset",
    "PredictionRecord": "ml_surrogate.dataset",
}


def __getattr__(name: str):
    module_name = _LAZY_ATTRS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    return getattr(importlib.import_module(module_name), name)


def __dir__() -> list[str]:
    return sorted(__all__)

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
