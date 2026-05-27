#!/usr/bin/env python3
"""Entrena surrogates para m*_e, m*_h y ε_∞ de perovskitas ABX3.

Datos: data/meff_lit.csv + data/dielectric_lit.csv (literatura GW/HSE + DFT publicada)
       Puede complementarse con resultados DFT propios cuando estén disponibles.

Modelos guardados:
  models/surrogate_meff_e.pkl   — m*_e/m₀ (RF+GBR, bootstrap=100)
  models/surrogate_meff_h.pkl   — m*_h/m₀ (RF+GBR, bootstrap=100)
  models/surrogate_eps_inf.pkl  — ε_∞      (RF+GBR, bootstrap=100)

Uso:
    .venv/bin/python3 scripts/train_meff_dielectric.py
    .venv/bin/python3 scripts/train_meff_dielectric.py --verbose
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ml_surrogate.features import extract, build_X, BASE_FEATURES
from ml_surrogate.model import SurrogateEnsemble


def _load_dataset(csv_path: Path, target_col: str) -> tuple[np.ndarray, np.ndarray, list[str]]:
    df = pd.read_csv(csv_path)
    rows = []
    targets = []
    for _, row in df.iterrows():
        try:
            feats = extract(row["A"], row["B"], row["X"])
            rows.append(feats)
            targets.append(float(row[target_col]))
        except (ValueError, KeyError) as e:
            print(f"  skip {row.get('material','?')}: {e}")
    feat_df = pd.DataFrame(rows)
    X_mat = build_X(feat_df, BASE_FEATURES)
    y = np.array(targets)
    return X_mat, y, BASE_FEATURES


def _train_and_save(
    X: np.ndarray,
    y: np.ndarray,
    feature_cols: list[str],
    out_path: Path,
    label: str,
    verbose: bool,
) -> None:
    n = len(y)
    model = SurrogateEnsemble(
        n_estimators=200,
        max_depth=4,
        min_samples_leaf=2,
        n_bootstrap=100,
        random_state=42,
    ).fit(X, y, feature_cols)

    # LOO CV for n ≤ 20, else 5-fold
    from sklearn.model_selection import LeaveOneOut, KFold, cross_val_predict
    from sklearn.pipeline import Pipeline
    from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.preprocessing import StandardScaler

    def _pipe(est):
        return Pipeline([
            ("imp", SimpleImputer(strategy="median")),
            ("sc",  StandardScaler()),
            ("m",   est),
        ])

    cv = LeaveOneOut() if n <= 20 else KFold(n_splits=5, shuffle=True, random_state=42)
    rf_cv = cross_val_predict(
        _pipe(RandomForestRegressor(200, max_depth=4, min_samples_leaf=2, random_state=42, n_jobs=-1)),
        X, y, cv=cv,
    )
    mae = float(np.mean(np.abs(rf_cv - y)))
    r2  = float(1 - np.sum((rf_cv - y)**2) / np.sum((y - y.mean())**2))

    model.save(out_path)

    metrics = {"n": n, "cv": "LOO" if n <= 20 else "5-fold",
               "mae": round(mae, 4), "r2": round(r2, 4)}
    out_path.with_suffix(".metrics.json").write_text(json.dumps(metrics, indent=2))

    if verbose:
        imp = model.feature_importances()
        top3 = sorted(imp.items(), key=lambda x: -x[1])[:3]
        print(f"  {label}  n={n}  MAE={mae:.4f}  R²={r2:.3f}")
        print(f"  top features: {top3}")
    else:
        print(f"  {label}: n={n}  MAE={mae:.4f}  R²={r2:.3f}  → {out_path.name}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Train m* and ε_∞ surrogates")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    models_dir = ROOT / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    meff_csv  = ROOT / "data" / "meff_lit.csv"
    diel_csv  = ROOT / "data" / "dielectric_lit.csv"

    print("── Surrogate m*_e ──────────────────────────────────")
    X, y, cols = _load_dataset(meff_csv, "m_e_m0")
    _train_and_save(X, y, cols, models_dir / "surrogate_meff_e.pkl", "m*_e", args.verbose)

    print("── Surrogate m*_h ──────────────────────────────────")
    X, y, cols = _load_dataset(meff_csv, "m_h_m0")
    _train_and_save(X, y, cols, models_dir / "surrogate_meff_h.pkl", "m*_h", args.verbose)

    print("── Surrogate ε_∞  ──────────────────────────────────")
    X, y, cols = _load_dataset(diel_csv, "eps_inf")
    _train_and_save(X, y, cols, models_dir / "surrogate_eps_inf.pkl", "ε_∞", args.verbose)

    print("Listo. Modelos en models/")


if __name__ == "__main__":
    main()
