"""
Regression analysis metrics for comparing ML predictions vs DFT references.
"""

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

logger = logging.getLogger(__name__)


def safe_divide(a: float, b: float, default: float = 0.0) -> float:
    """Safely divide a by b, returning default if b is zero."""
    return a / b if b != 0 else default


def compute_regression_metrics(
    y_true: np.ndarray, y_pred: np.ndarray, property_name: str
) -> Dict[str, float]:
    """
    Compute regression metrics for a single property.

    Args:
        y_true: True values (DFT)
        y_pred: Predicted values (ML)
        property_name: Name of the property for logging

    Returns:
        Dictionary of metrics
    """
    if len(y_true) == 0 or len(y_pred) == 0:
        logger.warning(f"No data for {property_name}")
        return {}

    # Absolute Error
    ae = np.abs(y_true - y_pred)

    # Relative Error (%)
    rel_error = 100 * np.abs(y_true - y_pred) / np.abs(y_true)
    rel_error = np.where(np.isfinite(rel_error), rel_error, 0.0)  # Handle inf

    # Mean Absolute Error
    mae = mean_absolute_error(y_true, y_pred)

    # Root Mean Square Error
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))

    # R² score
    r2 = r2_score(y_true, y_pred)

    # Mean Bias Error
    bias = np.mean(y_pred - y_true)

    # Pearson correlation
    try:
        pearson_corr, _ = pearsonr(y_true, y_pred)
    except Exception as e:
        logger.warning(f"Pearson correlation failed for {property_name}: {e}")
        pearson_corr = np.nan

    # Spearman correlation
    try:
        spearman_corr, _ = spearmanr(y_true, y_pred)
    except Exception as e:
        logger.warning(f"Spearman correlation failed for {property_name}: {e}")
        spearman_corr = np.nan

    return {
        "mae": mae,
        "rmse": rmse,
        "r2": r2,
        "bias": bias,
        "pearson_corr": pearson_corr,
        "spearman_corr": spearman_corr,
        "mean_ae": np.mean(ae),
        "mean_rel_error": np.mean(rel_error),
        "max_ae": np.max(ae),
        "max_rel_error": np.max(rel_error),
    }


def analyze_all_properties(df: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    """
    Analyze regression metrics for all comparable properties.

    Args:
        df: DataFrame with DFT and ML columns

    Returns:
        Dictionary of property metrics
    """
    properties = [
        "bandgap",
        "lattice_parameter",
        "volume",
        "formation_energy",
        "energy_hull",
        "absorption_score",
        "stability_score",
    ]

    results = {}
    for prop in properties:
        dft_col = f"dft_{prop}"
        ml_col = f"ml_{prop}"

        if dft_col in df.columns and ml_col in df.columns:
            # Drop NaN values
            valid_data = df[[dft_col, ml_col]].dropna()
            if len(valid_data) > 0:
                y_true = valid_data[dft_col].values
                y_pred = valid_data[ml_col].values
                results[prop] = compute_regression_metrics(y_true, y_pred, prop)
            else:
                logger.warning(f"No valid data for {prop}")
        else:
            logger.warning(f"Missing columns for {prop}: {dft_col}, {ml_col}")

    return results


def create_metrics_summary_table(metrics: Dict[str, Dict[str, float]]) -> pd.DataFrame:
    """
    Create a summary table of regression metrics.

    Args:
        metrics: Dictionary from analyze_all_properties

    Returns:
        DataFrame with metrics summary
    """
    rows = []
    for prop, mets in metrics.items():
        row = {"property": prop}
        row.update(mets)
        rows.append(row)

    return pd.DataFrame(rows)