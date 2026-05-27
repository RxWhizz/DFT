"""Minimal tests for the surrogate ML module.

Run: .venv/bin/python3 -m pytest tests/test_surrogate.py -v
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


# ── features.py ───────────────────────────────────────────────────────────────

def test_extract_cspbi3():
    from ml_surrogate.features import extract, goldschmidt, octahedral_factor
    f = extract("Cs", "Pb", "I")
    # Goldschmidt should be ~0.807
    assert abs(f["tolerance_t"] - 0.807) < 0.01
    # Octahedral factor Pb/I = 1.19/2.20 ≈ 0.541
    assert abs(f["oct_factor"] - 0.541) < 0.01
    # Lattice constant estimate: 2√2*(1.19+2.20) ≈ 9.59 Å — Cs perovskite primitive is ~6.3
    # a_est is for cubic conventional cell = 2√2*(rB+rX)
    assert 9.0 < f["a_lat_est_A"] < 10.5
    assert f["is_organic_A"] == 0.0


def test_extract_organic():
    from ml_surrogate.features import extract
    f = extract("MA", "Pb", "I")
    assert f["is_organic_A"] == 1.0
    # MA radius larger than Cs
    assert f["r_A"] > 1.67


def test_extract_mixed_halide():
    from ml_surrogate.features import extract
    f = extract("Cs", "Pb", "I", x_I=0.5, x_Br=0.5)
    r_X_expected = 0.5 * 2.20 + 0.5 * 1.96
    assert abs(f["r_X"] - r_X_expected) < 1e-6


def test_build_X_shape():
    from ml_surrogate.features import extract, build_X, BASE_FEATURES
    import pandas as pd
    rows = [extract("Cs", "Pb", "I"), extract("MA", "Sn", "Br")]
    df = pd.DataFrame(rows)
    X = build_X(df, BASE_FEATURES)
    assert X.shape == (2, len(BASE_FEATURES))
    assert not np.isnan(X).any()


def test_build_X_imputation():
    from ml_surrogate.features import extract, build_X, BASE_FEATURES, OPTIONAL_FEATURES
    import pandas as pd
    f = extract("Cs", "Pb", "I")   # optional features are NaN
    df = pd.DataFrame([f])
    cols = BASE_FEATURES + OPTIONAL_FEATURES
    X = build_X(df, cols, impute_median=True)
    # After median imputation, no NaN should remain
    assert not np.isnan(X).any()


# ── model.py ──────────────────────────────────────────────────────────────────

def _make_tiny_dataset():
    from ml_surrogate.features import extract, build_X, BASE_FEATURES
    import pandas as pd
    compositions = [
        ("Cs", "Pb", "I", 1.73), ("Cs", "Pb", "Br", 2.36), ("Cs", "Sn", "I", 1.30),
        ("MA", "Pb", "I", 1.55), ("FA", "Pb", "I", 1.48), ("Cs", "Ge", "I", 1.63),
    ]
    rows = [extract(A, B, X) for A, B, X, _ in compositions]
    y = np.array([eg for *_, eg in compositions])
    df = pd.DataFrame(rows)
    X = build_X(df, BASE_FEATURES)
    return X, y, BASE_FEATURES


def test_ensemble_fit_predict():
    from ml_surrogate.model import SurrogateEnsemble
    X, y, cols = _make_tiny_dataset()
    model = SurrogateEnsemble(n_estimators=20, n_bootstrap=10, random_state=0)
    model.fit(X, y, cols)
    mean, std = model.predict_single(X[0])
    assert isinstance(mean, float)
    assert std >= 0.0


def test_ensemble_batch_predict():
    from ml_surrogate.model import SurrogateEnsemble
    X, y, cols = _make_tiny_dataset()
    model = SurrogateEnsemble(n_estimators=20, n_bootstrap=5, random_state=0).fit(X, y, cols)
    means, stds = model.predict_batch(X)
    assert means.shape == (len(y),)
    assert stds.shape == (len(y),)
    assert (stds >= 0).all()


def test_feature_importances():
    from ml_surrogate.model import SurrogateEnsemble
    X, y, cols = _make_tiny_dataset()
    model = SurrogateEnsemble(n_estimators=20, n_bootstrap=5, random_state=0).fit(X, y, cols)
    imp = model.feature_importances()
    assert set(imp.keys()) == set(cols)
    assert abs(sum(imp.values()) - 1.0) < 1e-6


def test_save_load(tmp_path):
    from ml_surrogate.model import SurrogateEnsemble
    X, y, cols = _make_tiny_dataset()
    model = SurrogateEnsemble(n_estimators=10, n_bootstrap=5, random_state=0).fit(X, y, cols)
    path = tmp_path / "model.pkl"
    model.save(path)
    loaded = SurrogateEnsemble.load(path)
    m1, _ = model.predict_single(X[0])
    m2, _ = loaded.predict_single(X[0])
    assert abs(m1 - m2) < 1e-10


# ── integration.py ───────────────────────────────────────────────────────────

def test_surrogate_acquisition_heuristic_fallback(tmp_path):
    """SurrogateAcquisition uses heuristic when model file is absent."""
    from ml_surrogate.integration import SurrogateAcquisition
    from ml_surrogate.config import SurrogateConfig
    cfg = SurrogateConfig()
    cfg.model_dir = str(tmp_path)
    cfg.model_name = "nonexistent_model"
    acq = SurrogateAcquisition(beta=1.0, cfg=cfg)
    score = acq.score_one("CsPbI3", "Cs", "Pb", "I")
    assert score.model_source == "heuristic_fallback"
    assert score.Eg_pred == pytest.approx(1.50, abs=0.1)


def test_surrogate_acquisition_with_model(tmp_path):
    from ml_surrogate.integration import SurrogateAcquisition
    from ml_surrogate.model import SurrogateEnsemble
    from ml_surrogate.config import SurrogateConfig
    X, y, cols = _make_tiny_dataset()
    model = SurrogateEnsemble(n_estimators=20, n_bootstrap=5, random_state=0).fit(X, y, cols)
    model_path = tmp_path / "surrogate_bandgap.pkl"
    model.save(model_path)
    cfg = SurrogateConfig()
    cfg.model_dir = str(tmp_path)
    cfg.model_name = "surrogate_bandgap"
    acq = SurrogateAcquisition(beta=1.0, cfg=cfg)
    score = acq.score_one("CsPbI3", "Cs", "Pb", "I")
    assert score.model_source == "surrogate"
    assert 0.5 < score.Eg_pred < 5.0
    assert score.Eg_uncertainty >= 0.0
    assert 0.0 <= score.total_score


# ── config.py ─────────────────────────────────────────────────────────────────

def test_config_defaults():
    from ml_surrogate.config import SurrogateConfig
    cfg = SurrogateConfig()
    assert cfg.model_type == "ensemble"
    assert cfg.n_estimators == 200
    assert cfg.target_col == "Eg_target_eV"


def test_config_from_yaml(tmp_path):
    from ml_surrogate.config import SurrogateConfig
    yaml_content = "n_estimators: 50\nmax_depth: 3\nmodel_name: test_model\n"
    p = tmp_path / "test.yaml"
    p.write_text(yaml_content)
    cfg = SurrogateConfig.from_yaml(p)
    assert cfg.n_estimators == 50
    assert cfg.max_depth == 3
    assert cfg.model_name == "test_model"
