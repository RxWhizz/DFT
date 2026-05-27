"""Feature engineering for ABX3 halide perovskite surrogate.

All features are derivable from composition alone (no DFT required).
Optional features use MACE relaxation geometry or MP/GGA data when available.

Feature vector (16D base):
  [0]  r_A          — Shannon ionic radius A-site (Å, 12-coord)
  [1]  r_B          — Shannon ionic radius B-site (Å, 6-coord)
  [2]  r_X          — Shannon ionic radius X-site (Å, 6-coord)
  [3]  chi_A        — Pauling electronegativity A-site
  [4]  chi_B        — Pauling electronegativity B-site
  [5]  chi_X        — Pauling electronegativity X-site
  [6]  q_A          — Formal charge A-site (+1)
  [7]  q_B          — Formal charge B-site (+2)
  [8]  q_X          — Formal charge X-site (-1)
  [9]  tolerance_t  — Goldschmidt tolerance factor
  [10] oct_factor   — Octahedral factor = r_B / r_X
  [11] a_lat_est_A  — Estimated lattice constant 2√2·(r_B+r_X) (Å)
  [12] vol_est_A3   — Estimated unit cell volume (Å³)
  [13] delta_chi_BX — Electronegativity difference chi_X - chi_B (ionicity proxy)
  [14] mu_BX        — Reduced radius r_B + r_X (bond length proxy)
  [15] is_organic_A — 1 if A ∈ {MA, FA}, else 0

Optional extensions (appended when data available):
  [16] a_lat_mp_A   — MP or MACE lattice constant (Å)
  [17] E_mace_eV_atom — MACE total energy per atom (eV)
  [18] band_gap_gga_eV — GGA bandgap from MP or DFT
  [19] Eform_eV_atom   — Formation energy per atom (eV)
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

# ── Physical constants ─────────────────────────────────────────────────────────

# Shannon 1976 (12-coord for A, 6-coord for B/X) + Kieslich 2014 for organics
IONIC_RADII: Dict[str, float] = {
    "Cs": 1.67, "Rb": 1.52, "K": 1.38, "MA": 2.17, "FA": 2.53,
    "Pb": 1.19, "Sn": 1.18, "Ge": 0.73, "Bi": 1.03, "In": 0.80,
    "I":  2.20, "Br": 1.96, "Cl": 1.81,
}

# Pauling electronegativities (organics: effective from N-C-H bonds)
ELECTRONEG: Dict[str, float] = {
    "Cs": 0.79, "Rb": 0.82, "K": 0.82, "MA": 2.30, "FA": 2.40,
    "Pb": 2.33, "Sn": 1.96, "Ge": 2.01, "Bi": 2.02, "In": 1.78,
    "I":  2.66, "Br": 2.96, "Cl": 3.16,
}

# Formal charges
CHARGES: Dict[str, int] = {
    "Cs": 1, "Rb": 1, "K": 1, "MA": 1, "FA": 1,
    "Pb": 2, "Sn": 2, "Ge": 2, "Bi": 3, "In": 3,
    "I": -1, "Br": -1, "Cl": -1,
}

ORGANIC_A = {"MA", "FA"}
_SQRT2 = math.sqrt(2.0)

# ── Core functions ─────────────────────────────────────────────────────────────


def goldschmidt(r_A: float, r_B: float, r_X: float) -> float:
    """Goldschmidt tolerance factor t = (r_A + r_X) / (√2 · (r_B + r_X))."""
    return (r_A + r_X) / (_SQRT2 * (r_B + r_X))


def octahedral_factor(r_B: float, r_X: float) -> float:
    """Octahedral factor μ = r_B / r_X. Stable when 0.41 ≤ μ ≤ 0.90."""
    return r_B / r_X


def lattice_est(r_B: float, r_X: float) -> float:
    """Empirical cubic lattice constant a₀ ≈ 2√2·(r_B + r_X) (Å)."""
    return 2.0 * _SQRT2 * (r_B + r_X)


def extract(
    A: str,
    B: str,
    X: str,
    x_I: Optional[float] = None,
    x_Br: Optional[float] = None,
    x_Cl: Optional[float] = None,
    a_lat: Optional[float] = None,
    E_mace_eV_atom: Optional[float] = None,
    band_gap_gga: Optional[float] = None,
    Eform_eV_atom: Optional[float] = None,
) -> Dict[str, float]:
    """Compute feature dict for one ABX3 composition.

    Parameters
    ----------
    A, B : site-labels (e.g. "Cs", "Pb")
    X    : halide label for pure compositions (e.g. "I"); ignored for mixed
    x_I, x_Br, x_Cl : halide fractions (must sum to 1)
    a_lat : measured or MACE lattice constant (optional)
    E_mace_eV_atom : MACE energy/atom (optional)
    band_gap_gga : GGA bandgap in eV (optional)
    Eform_eV_atom : formation energy/atom in eV (optional)
    """
    if A not in IONIC_RADII:
        raise ValueError(f"Unknown A-site element: {A!r}")
    if B not in IONIC_RADII:
        raise ValueError(f"Unknown B-site element: {B!r}")

    # Infer halide fractions from X label when not explicitly provided
    _PURE = {"I", "Br", "Cl"}
    if x_I is None and x_Br is None and x_Cl is None:
        if X in _PURE:
            x_I  = 1.0 if X == "I"  else 0.0
            x_Br = 1.0 if X == "Br" else 0.0
            x_Cl = 1.0 if X == "Cl" else 0.0
        else:
            x_I, x_Br, x_Cl = 1.0, 0.0, 0.0  # fallback
    else:
        x_I  = x_I  if x_I  is not None else 0.0
        x_Br = x_Br if x_Br is not None else 0.0
        x_Cl = x_Cl if x_Cl is not None else 0.0

    r_A = IONIC_RADII[A]
    r_B = IONIC_RADII[B]
    r_X = x_I * IONIC_RADII["I"] + x_Br * IONIC_RADII["Br"] + x_Cl * IONIC_RADII["Cl"]
    chi_A = ELECTRONEG[A]
    chi_B = ELECTRONEG[B]
    chi_X = x_I * ELECTRONEG["I"] + x_Br * ELECTRONEG["Br"] + x_Cl * ELECTRONEG["Cl"]
    q_A = float(CHARGES[A])
    q_B = float(CHARGES[B])
    q_X = x_I * CHARGES["I"] + x_Br * CHARGES["Br"] + x_Cl * CHARGES["Cl"]

    t = goldschmidt(r_A, r_B, r_X)
    f_oct = octahedral_factor(r_B, r_X)
    a_est = lattice_est(r_B, r_X)
    vol_est = a_est ** 3

    feats: Dict[str, float] = {
        "r_A": r_A, "r_B": r_B, "r_X": r_X,
        "chi_A": chi_A, "chi_B": chi_B, "chi_X": chi_X,
        "q_A": q_A, "q_B": q_B, "q_X": q_X,
        "tolerance_t": t,
        "oct_factor": f_oct,
        "a_lat_est_A": a_est,
        "vol_est_A3": vol_est,
        "delta_chi_BX": chi_X - chi_B,
        "mu_BX": r_B + r_X,
        "is_organic_A": float(A in ORGANIC_A),
    }

    # Optional features — NaN when unavailable (model handles imputation)
    feats["a_lat_mp_A"] = float(a_lat) if a_lat is not None else float("nan")
    feats["E_mace_eV_atom"] = float(E_mace_eV_atom) if E_mace_eV_atom is not None else float("nan")
    feats["band_gap_gga_eV"] = float(band_gap_gga) if band_gap_gga is not None else float("nan")
    feats["Eform_eV_atom"] = float(Eform_eV_atom) if Eform_eV_atom is not None else float("nan")

    return feats


def from_candidate(candidate) -> Dict[str, float]:
    """Extract features from an HTSCandidate object."""
    return extract(
        A=candidate.A,
        B=candidate.B,
        X=candidate.X if hasattr(candidate, "X") else "I",
        x_I=getattr(candidate, "x_I", 1.0),
        x_Br=getattr(candidate, "x_Br", 0.0),
        x_Cl=getattr(candidate, "x_Cl", 0.0),
    )


def from_dict(d: dict) -> Dict[str, float]:
    """Extract features from a flat dict (e.g. ai_predictions.json row)."""
    return extract(
        A=d["A"], B=d["B"], X=d.get("X", "I"),
        x_I=float(d.get("x_I", 1.0 if d.get("X") == "I" else 0.0)),
        x_Br=float(d.get("x_Br", 1.0 if d.get("X") == "Br" else 0.0)),
        x_Cl=float(d.get("x_Cl", 1.0 if d.get("X") == "Cl" else 0.0)),
        a_lat=d.get("a_mace_A") or d.get("a_lat_mp_A"),
        E_mace_eV_atom=(d["E_mace_eV"] / (5 if d.get("B") in ("Pb", "Sn", "Ge") else 12))
                        if d.get("E_mace_eV") else None,
        band_gap_gga=d.get("band_gap_gga_eV") or d.get("Eg_megnet_eV"),
        Eform_eV_atom=d.get("Eform_eV_atom"),
    )


def build_X(
    df: pd.DataFrame,
    feature_cols: List[str],
    impute_median: bool = True,
) -> np.ndarray:
    """Build feature matrix from DataFrame.

    Parameters
    ----------
    df : DataFrame with feature columns
    feature_cols : ordered list of column names to use
    impute_median : replace NaN with column median (for optional features)
    """
    X = df[feature_cols].values.astype(float)
    if impute_median and np.isnan(X).any():
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            col_medians = np.nanmedian(X, axis=0)
        for j in range(X.shape[1]):
            nan_rows = np.isnan(X[:, j])
            if not nan_rows.any():
                continue
            fill = col_medians[j] if not np.isnan(col_medians[j]) else 0.0
            X[nan_rows, j] = fill
    return X


BASE_FEATURES = [
    "r_A", "r_B", "r_X",
    "chi_A", "chi_B", "chi_X",
    "q_A", "q_B", "q_X",
    "tolerance_t", "oct_factor",
    "a_lat_est_A", "vol_est_A3",
    "delta_chi_BX", "mu_BX",
    "is_organic_A",
]

OPTIONAL_FEATURES = [
    "a_lat_mp_A",
    "E_mace_eV_atom",
    "band_gap_gga_eV",
    "Eform_eV_atom",
]
