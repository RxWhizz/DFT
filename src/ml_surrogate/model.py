"""Surrogate ML model: ensemble of RandomForest + GradientBoosting.

Design decisions:
  - RF + GBR ensemble: robust for small datasets (n≈26), no XGBoost dependency
  - Bootstrap uncertainty: resample training data B times, compute std of predictions
  - Imputation: median fill for optional NaN features at predict time
  - Regularization: shallow trees (max_depth=4), min_samples_leaf=2 prevent overfitting
  - Targets: bandgap (primary), formation energy proxy (secondary, optional)

Output schema per prediction:
  {
    "bandgap_pred": float,
    "bandgap_uncertainty": float,
    "stability_score": float,   # sigmoid(-Eform / 0.5)
    "solar_score": float,       # Gaussian proximity to 1.45 eV
    "in_pv_window": bool,       # 1.1 ≤ Eg ≤ 1.8 eV
    "model_name": str,
    "features_used": List[str],
  }
"""
from __future__ import annotations

import math
import pickle
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.utils import resample

_PV_CENTER = 1.45   # eV — Shockley-Queisser optimum
_PV_SIGMA  = 0.35   # eV
_STAB_SCALE = 0.5   # eV/atom


class SurrogateEnsemble:
    """RF + GBR ensemble surrogate with bootstrap uncertainty.

    Parameters
    ----------
    n_estimators : number of trees per model
    max_depth : max tree depth (keep shallow for small datasets)
    n_bootstrap : number of bootstrap resamplings for uncertainty
    random_state : reproducibility seed
    """

    def __init__(
        self,
        n_estimators: int = 200,
        max_depth: int = 4,
        min_samples_leaf: int = 2,
        n_bootstrap: int = 100,
        random_state: int = 42,
    ) -> None:
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.n_bootstrap = n_bootstrap
        self.random_state = random_state

        self._rf: Optional[Pipeline] = None
        self._gbr: Optional[Pipeline] = None
        self._bootstrap_preds: Optional[np.ndarray] = None
        self.feature_cols: List[str] = []
        self._trained = False

    # ── Training ────────────────────────────────────────────────────────────

    def fit(self, X: np.ndarray, y: np.ndarray, feature_cols: List[str]) -> "SurrogateEnsemble":
        """Fit RF + GBR on full dataset. Bootstrap samples for uncertainty."""
        self.feature_cols = list(feature_cols)
        rng = np.random.RandomState(self.random_state)

        def _pipe(estimator):
            return Pipeline([
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                ("model", estimator),
            ])

        self._rf = _pipe(RandomForestRegressor(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            min_samples_leaf=self.min_samples_leaf,
            random_state=self.random_state,
            n_jobs=-1,
        )).fit(X, y)

        self._gbr = _pipe(GradientBoostingRegressor(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            min_samples_leaf=self.min_samples_leaf,
            learning_rate=0.05,
            subsample=0.8,
            random_state=self.random_state,
        )).fit(X, y)

        # Bootstrap: fit B shallow RF models on resampled data → std = uncertainty
        bootstrap_models = []
        for i in range(self.n_bootstrap):
            X_b, y_b = resample(X, y, random_state=rng.randint(0, 10_000))
            m = Pipeline([
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                ("model", RandomForestRegressor(
                    n_estimators=50,
                    max_depth=self.max_depth,
                    min_samples_leaf=self.min_samples_leaf,
                    random_state=rng.randint(0, 10_000),
                    n_jobs=1,
                )),
            ]).fit(X_b, y_b)
            bootstrap_models.append(m)
        self._bootstrap_models = bootstrap_models
        self._trained = True
        return self

    # ── Prediction ────────────────────────────────────────────────────────

    def predict_single(self, x: np.ndarray) -> Tuple[float, float]:
        """Predict mean bandgap and uncertainty for one sample.

        Parameters
        ----------
        x : (n_features,) array (already imputed, no NaN)

        Returns
        -------
        (mean_pred, std_uncertainty)
        """
        if not self._trained:
            raise RuntimeError("Model not trained. Call fit() first.")
        x2d = x.reshape(1, -1)
        rf_pred = float(self._rf.predict(x2d)[0])
        gbr_pred = float(self._gbr.predict(x2d)[0])
        mean_pred = (rf_pred + gbr_pred) / 2.0

        bootstrap_vals = np.array([m.predict(x2d)[0] for m in self._bootstrap_models])
        std = float(np.std(bootstrap_vals))

        return mean_pred, std

    def predict_batch(self, X: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Predict mean and uncertainty for a batch of samples.

        Returns
        -------
        means : (N,) array
        stds  : (N,) array
        """
        if not self._trained:
            raise RuntimeError("Model not trained.")
        rf_preds = self._rf.predict(X)
        gbr_preds = self._gbr.predict(X)
        means = (rf_preds + gbr_preds) / 2.0

        bootstrap_preds = np.column_stack([m.predict(X) for m in self._bootstrap_models])
        stds = np.std(bootstrap_preds, axis=1)

        return means, stds

    def feature_importances(self) -> Dict[str, float]:
        """Average RF + GBR feature importances (normalized)."""
        if not self._trained:
            return {}
        rf_imp = self._rf.named_steps["model"].feature_importances_
        gbr_imp = self._gbr.named_steps["model"].feature_importances_
        avg = (rf_imp + gbr_imp) / 2.0
        avg /= avg.sum()
        return dict(zip(self.feature_cols, avg.tolist()))

    # ── Persistence ────────────────────────────────────────────────────────

    def save(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self, f, protocol=pickle.HIGHEST_PROTOCOL)

    @classmethod
    def load(cls, path: str | Path) -> "SurrogateEnsemble":
        with open(path, "rb") as f:
            obj = pickle.load(f)
        if not isinstance(obj, cls):
            raise TypeError(f"Expected SurrogateEnsemble, got {type(obj)}")
        return obj


# ── Scoring helpers ────────────────────────────────────────────────────────────


def make_prediction_record(
    mat: str,
    A: str,
    B: str,
    X: str,
    bandgap_pred: float,
    bandgap_std: float,
    Eform_pred: Optional[float],
    feature_cols: List[str],
    model_name: str = "SurrogateEnsemble-RF+GBR",
) -> dict:
    """Build standardized prediction output record."""
    solar_score = float(np.exp(-0.5 * ((bandgap_pred - _PV_CENTER) / _PV_SIGMA) ** 2))
    in_pv = 1.1 <= bandgap_pred <= 1.8

    if Eform_pred is not None and math.isfinite(Eform_pred):
        stability_score = float(1.0 / (1.0 + math.exp(Eform_pred / _STAB_SCALE)))
    else:
        stability_score = 0.5

    return {
        "material": mat,
        "A": A, "B": B, "X": X,
        "bandgap_pred": round(bandgap_pred, 4),
        "bandgap_uncertainty": round(bandgap_std, 4),
        "stability_score": round(stability_score, 4),
        "solar_score": round(solar_score, 4),
        "in_pv_window": in_pv,
        "model_name": model_name,
        "features_used": list(feature_cols),
    }
