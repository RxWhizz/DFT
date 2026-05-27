"""CLI trainer for the ABX3 perovskite surrogate.

Usage
-----
    python -m src.ml_surrogate.train --config configs/surrogate.yaml
    python -m src.ml_surrogate.train --config configs/surrogate.yaml --cv
    python -m src.ml_surrogate.train --data data/surrogate_training.csv --out models/

The trainer:
  1. Loads and validates the training CSV
  2. Builds feature matrix (base + optional available features)
  3. Cross-validates (LOO for n≤15, k-fold otherwise)
  4. Fits the final SurrogateEnsemble on the full dataset
  5. Saves the model to disk
  6. Prints feature importances and CV metrics
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import KFold, LeaveOneOut, cross_val_predict

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ml_surrogate.config import SurrogateConfig
from ml_surrogate.features import BASE_FEATURES, OPTIONAL_FEATURES, build_X
from ml_surrogate.model import SurrogateEnsemble


def _load_data(csv_path: Path, target_col: str) -> tuple[pd.DataFrame, np.ndarray]:
    df = pd.read_csv(csv_path)
    required = set(BASE_FEATURES) | {target_col}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Training CSV missing columns: {missing}")
    y = df[target_col].values.astype(float)
    return df, y


def _select_features(df: pd.DataFrame, cfg: SurrogateConfig) -> list[str]:
    """Use base + optional features that are available and not all-NaN."""
    cols = list(cfg.base_features)
    for c in cfg.optional_features:
        if c in df.columns and df[c].notna().any():
            cols.append(c)
    return cols


def _cv_evaluate(X: np.ndarray, y: np.ndarray, cfg: SurrogateConfig) -> dict:
    """Cross-validate: LOO when n≤15, k-fold otherwise."""
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.ensemble import RandomForestRegressor

    n = len(y)
    cv = LeaveOneOut() if n <= 15 else KFold(n_splits=min(cfg.cv_folds, n), shuffle=True,
                                              random_state=cfg.random_state)

    rf_pipe = Pipeline([
        ("scaler", StandardScaler()),
        ("model", RandomForestRegressor(
            n_estimators=cfg.n_estimators,
            max_depth=cfg.max_depth,
            min_samples_leaf=cfg.min_samples_leaf,
            random_state=cfg.random_state,
            n_jobs=-1,
        )),
    ])

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        y_pred = cross_val_predict(rf_pipe, X, y, cv=cv)

    mae = float(mean_absolute_error(y, y_pred))
    r2 = float(r2_score(y, y_pred))
    rmse = float(np.sqrt(np.mean((y - y_pred) ** 2)))
    cv_name = "LOO" if n <= 15 else f"{min(cfg.cv_folds, n)}-fold"
    return {"cv": cv_name, "MAE_eV": mae, "RMSE_eV": rmse, "R2": r2, "n_samples": n}


def train(cfg: SurrogateConfig, run_cv: bool = True, verbose: bool = True) -> SurrogateEnsemble:
    """Train surrogate and save model. Returns fitted SurrogateEnsemble."""
    csv_path = cfg.training_data_path
    if not csv_path.exists():
        raise FileNotFoundError(f"Training data not found: {csv_path}")

    df, y = _load_data(csv_path, cfg.target_col)
    feature_cols = _select_features(df, cfg)
    X = build_X(df, feature_cols)

    if verbose:
        print(f"Training: {len(y)} samples | {len(feature_cols)} features")
        print(f"Target: {cfg.target_col} — range [{y.min():.2f}, {y.max():.2f}] eV")
        print(f"Features: {feature_cols}")

    cv_metrics = None
    if run_cv:
        cv_metrics = _cv_evaluate(X, y, cfg)
        if verbose:
            print(f"\nCV ({cv_metrics['cv']}):")
            print(f"  MAE  = {cv_metrics['MAE_eV']:.4f} eV")
            print(f"  RMSE = {cv_metrics['RMSE_eV']:.4f} eV")
            print(f"  R²   = {cv_metrics['R2']:.4f}")

    model = SurrogateEnsemble(
        n_estimators=cfg.n_estimators,
        max_depth=cfg.max_depth,
        min_samples_leaf=cfg.min_samples_leaf,
        n_bootstrap=cfg.n_bootstrap,
        random_state=cfg.random_state,
    ).fit(X, y, feature_cols)

    # Save model
    model_path = cfg.model_path
    model.save(model_path)
    if verbose:
        print(f"\nModel saved: {model_path}")

    # Feature importances
    importances = model.feature_importances()
    if verbose:
        print("\nFeature importances (top 10):")
        for feat, imp in sorted(importances.items(), key=lambda x: -x[1])[:10]:
            bar = "█" * int(imp * 40)
            print(f"  {feat:20s} {imp:.4f}  {bar}")

    # Training set predictions (not CV — just fit quality)
    y_train_pred, y_train_std = model.predict_batch(X)
    train_mae = float(mean_absolute_error(y, y_train_pred))
    if verbose:
        print(f"\nTrain MAE (in-sample) = {train_mae:.4f} eV")
        print("\nPer-sample predictions:")
        print(f"  {'A':3} {'B':3} {'X':3}  {'Eg_exp':>8}  {'Eg_pred':>8}  {'±':>6}  {'err':>6}")
        print("  " + "-" * 52)
        for i, (_, row) in enumerate(df.iterrows()):
            err = y_train_pred[i] - y[i]
            print(f"  {row['A']:3} {row['B']:3} {row['X']:3}  "
                  f"{y[i]:8.3f}  {y_train_pred[i]:8.3f}  {y_train_std[i]:6.3f}  {err:+6.3f}")

    # Save metrics JSON alongside model
    metrics_path = model_path.with_suffix(".metrics.json")
    metrics = {
        "cv": cv_metrics,
        "train_MAE_eV": train_mae,
        "n_samples": len(y),
        "n_features": len(feature_cols),
        "features": feature_cols,
        "model_type": "SurrogateEnsemble-RF+GBR",
        "target": cfg.target_col,
    }
    metrics_path.write_text(json.dumps(metrics, indent=2))

    return model


def main() -> None:
    pa = argparse.ArgumentParser(description="Train ABX3 perovskite surrogate ML model")
    pa.add_argument("--config", type=Path, default="configs/surrogate.yaml",
                    help="YAML config file (default: configs/surrogate.yaml)")
    pa.add_argument("--data", type=Path, help="Override training CSV path")
    pa.add_argument("--out", type=Path, help="Override model output directory")
    pa.add_argument("--no-cv", action="store_true", help="Skip cross-validation")
    pa.add_argument("--quiet", action="store_true")
    args = pa.parse_args()

    cfg_path = ROOT / args.config if not Path(args.config).is_absolute() else args.config
    if cfg_path.exists():
        cfg = SurrogateConfig.from_yaml(cfg_path)
    else:
        cfg = SurrogateConfig()

    if args.data:
        cfg.training_data = str(args.data)
    if args.out:
        cfg.model_dir = str(args.out)

    Path(ROOT / cfg.model_dir).mkdir(parents=True, exist_ok=True)

    train(cfg, run_cv=not args.no_cv, verbose=not args.quiet)


if __name__ == "__main__":
    main()
