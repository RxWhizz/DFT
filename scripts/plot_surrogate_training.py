#!/usr/bin/env python3
"""Gráficas de entrenamiento del surrogate de energía (active learning).

Genera figuras reportables desde la curva de aprendizaje y el modelo actual:

  learning_curve.png  — MAE train vs test por batch (sobreajuste/convergencia)
  loss_rmse.png       — RMSE train vs test por batch (loss)
  overfit_ratio.png   — test_mae/train_mae por batch (1.0 = sin sobreajuste)
  data_growth.png     — n_train, n_test acumulados por batch
  parity_test.png     — predicho vs real (held-out) del modelo actual + MAE/RMSE/R²
  residuals_test.png  — histograma de residuos (held-out)

Lee: models/surrogate_energy_learning_curve.csv, data/processed/dft_accumulated.csv,
     models/surrogate_energy.pkl
Salida: reports/surrogate_training/*.png+pdf

Uso: python scripts/plot_surrogate_training.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

CURVE = ROOT / "models" / "surrogate_energy_learning_curve.csv"
ACC = ROOT / "data" / "processed" / "dft_accumulated.csv"
MODEL = ROOT / "models" / "surrogate_energy.pkl"
OUT = ROOT / "reports" / "surrogate_training"

_TRAIN_C = "#2a6f97"   # azul
_TEST_C = "#c1440e"    # naranja perovskita
DPI = 150


def _save(fig, stem):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / f"{stem}.png", dpi=DPI, bbox_inches="tight")
    fig.savefig(OUT / f"{stem}.pdf", bbox_inches="tight")
    plt.close(fig)


def _xlabels(curve):
    """Etiquetas de batch (-1 = bootstrap)."""
    return ["boot" if b == -1 else f"b{int(b)}" for b in curve["batch"]]


def plot_learning_curve(curve):
    fig, ax = plt.subplots(figsize=(7, 4.5))
    x = range(len(curve))
    ax.plot(x, curve["train_mae"], "o-", color=_TRAIN_C, label="MAE train", lw=2)
    ax.plot(x, curve["test_mae"], "s-", color=_TEST_C, label="MAE test (held-out)", lw=2)
    ax.fill_between(x, curve["train_mae"], curve["test_mae"], color="gray", alpha=0.12)
    ax.set_xticks(list(x)); ax.set_xticklabels(_xlabels(curve))
    ax.set_xlabel("batch de active learning")
    ax.set_ylabel("MAE (eV/átomo)")
    ax.set_title("Curva de aprendizaje — surrogate de energía DFT")
    ax.legend(); ax.grid(alpha=0.3)
    # eje secundario: datos totales
    ax2 = ax.twinx()
    ax2.plot(x, curve["n_total"], ":", color="green", alpha=0.6)
    ax2.set_ylabel("datos acumulados", color="green")
    ax2.tick_params(axis="y", labelcolor="green")
    _save(fig, "learning_curve")


def plot_loss(curve):
    fig, ax = plt.subplots(figsize=(7, 4.5))
    x = range(len(curve))
    ax.plot(x, curve["train_rmse"], "o-", color=_TRAIN_C, label="RMSE train", lw=2)
    ax.plot(x, curve["test_rmse"], "s-", color=_TEST_C, label="RMSE test", lw=2)
    ax.set_xticks(list(x)); ax.set_xticklabels(_xlabels(curve))
    ax.set_xlabel("batch"); ax.set_ylabel("RMSE / loss (eV/átomo)")
    ax.set_title("Loss (RMSE) por batch")
    ax.legend(); ax.grid(alpha=0.3)
    _save(fig, "loss_rmse")


def plot_overfit(curve):
    fig, ax = plt.subplots(figsize=(7, 4.5))
    x = range(len(curve))
    ax.plot(x, curve["overfit_ratio"], "D-", color="#6a0572", lw=2)
    ax.axhline(1.0, color="k", ls="--", alpha=0.5, label="sin sobreajuste (1.0)")
    ax.axhline(1.5, color="red", ls=":", alpha=0.5, label="alerta (1.5)")
    ax.set_xticks(list(x)); ax.set_xticklabels(_xlabels(curve))
    ax.set_xlabel("batch"); ax.set_ylabel("test_MAE / train_MAE")
    ax.set_title("Ratio de sobreajuste")
    ax.legend(); ax.grid(alpha=0.3)
    _save(fig, "overfit_ratio")


def plot_data_growth(curve):
    fig, ax = plt.subplots(figsize=(7, 4.5))
    x = range(len(curve))
    ax.bar([i - 0.2 for i in x], curve["n_train"], width=0.4, color=_TRAIN_C, label="train")
    ax.bar([i + 0.2 for i in x], curve["n_test"], width=0.4, color=_TEST_C, label="test")
    ax.set_xticks(list(x)); ax.set_xticklabels(_xlabels(curve))
    ax.set_xlabel("batch"); ax.set_ylabel("nº de muestras")
    ax.set_title("Crecimiento del dataset DFT")
    ax.legend(); ax.grid(alpha=0.3, axis="y")
    _save(fig, "data_growth")


_HELDOUT = ROOT / "models" / "surrogate_energy_heldout.csv"


def plot_parity_and_residuals():
    """Parity + residuos del held-out HONESTO (modelo train-split sobre test no visto)."""
    if not _HELDOUT.exists():
        return None
    ho = pd.read_csv(_HELDOUT)
    if len(ho) < 5:
        return None
    y = ho["y_true"].values.astype(float)
    pred = ho["y_pred"].values.astype(float)
    res = pred - y
    mae = float(np.mean(np.abs(res)))
    rmse = float(np.sqrt(np.mean(res ** 2)))
    ss_res = np.sum(res ** 2); ss_tot = np.sum((y - y.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")

    # parity
    fig, ax = plt.subplots(figsize=(5.5, 5.5))
    lim = [min(y.min(), pred.min()) - 0.05, max(y.max(), pred.max()) + 0.05]
    ax.plot(lim, lim, "k--", alpha=0.6)
    ax.scatter(y, pred, c=_TEST_C, alpha=0.6, edgecolors="none", s=28)
    ax.set_xlim(lim); ax.set_ylim(lim)
    ax.set_xlabel("E/átomo DFT real (eV)"); ax.set_ylabel("E/átomo predicho (eV)")
    ax.set_title("Parity — held-out test")
    ax.text(0.05, 0.95, f"MAE = {mae:.4f} eV/át\nRMSE = {rmse:.4f}\n$R^2$ = {r2:.4f}\nn = {len(y)}",
            transform=ax.transAxes, va="top", fontsize=10,
            bbox=dict(boxstyle="round", fc="white", alpha=0.8))
    ax.grid(alpha=0.3)
    _save(fig, "parity_test")

    # residuos
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.hist(res, bins=30, color=_TEST_C, alpha=0.7, edgecolor="k", lw=0.5)
    ax.axvline(0, color="k", ls="--")
    ax.set_xlabel("residuo: predicho − real (eV/átomo)"); ax.set_ylabel("frecuencia")
    ax.set_title(f"Residuos held-out (μ={res.mean():+.4f}, σ={res.std():.4f})")
    ax.grid(alpha=0.3, axis="y")
    _save(fig, "residuals_test")
    return {"mae": mae, "rmse": rmse, "r2": float(r2), "n_test": len(y)}


def make_plots(verbose: bool = True) -> dict:
    if not CURVE.exists():
        if verbose:
            print("(sin curva de aprendizaje todavía)")
        return {}
    curve = pd.read_csv(CURVE)
    plot_learning_curve(curve)
    plot_loss(curve)
    plot_overfit(curve)
    plot_data_growth(curve)
    parity = plot_parity_and_residuals()
    if verbose:
        print(f"Figuras en {OUT}/ ({len(list(OUT.glob('*.png')))} PNG)")
        if parity:
            print(f"Held-out: MAE={parity['mae']:.4f}  RMSE={parity['rmse']:.4f}  "
                  f"R²={parity['r2']:.4f}  (n={parity['n_test']})")
    return parity or {}


if __name__ == "__main__":
    make_plots()
