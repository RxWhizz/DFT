"""Cascada de cribado barato para batches de candidatos ABX3.

Cada candidato pasa tiers de costo creciente ANTES del DFT caro:

  Tier 0 — descriptores físicos (instantáneo): PhysicalFilter
           (especies, neutralidad, Goldschmidt t, octaédrico μ, volumen).
  Tier 1 — surrogate (ms): SurrogateEnsemble de bandgap → Eg_pred ± σ,
           band_score (proximidad a la ventana PV), incertidumbre para UCB.
  Tier 2 — MLFF (seg): construir estructura → MEGNet/M3GNet energía de
           formación (Eform) → estabilidad. Indicador de "físicamente
           correcto" sin DFT. Descarta Eform > umbral.

Score de adquisición (active learning):
  total = band_score(PV) + stab_score(Eform) + β·σ(UCB exploración)

Reusa: filters/physical_filters.PhysicalFilter, structure/build_abx3,
ml_surrogate.model.SurrogateEnsemble, ml_surrogate.gnn_predictor.GNNPredictor.
NO requiere DFT — todo corre en el venv (.venv) con matgl/mace/torch.
"""
from __future__ import annotations

import math
import warnings
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from buho.filters.physical_filters import PhysicalFilter
from buho.generator.heuristic_generator import GeneratedCandidate
from buho.structure.build_abx3 import ABX3StructureBuilder
from ml_surrogate.features import (
    CHARGES,
    ELECTRONEG,
    IONIC_RADII,
    ORGANIC_A,
    build_X,
    goldschmidt,
    lattice_est,
    octahedral_factor,
)

_PV_CENTER = 1.45
_PV_SIGMA = 0.35
_STAB_SCALE = 0.5


def _band_score(eg: float) -> float:
    """Gaussiana centrada en el óptimo fotovoltaico (1.45 eV)."""
    if eg is None or math.isnan(eg):
        return 0.0
    return float(np.exp(-0.5 * ((eg - _PV_CENTER) / _PV_SIGMA) ** 2))


def _stab_score(eform: Optional[float]) -> float:
    """sigmoid(−Eform/escala): Eform negativo (estable) → score alto."""
    if eform is None or (isinstance(eform, float) and math.isnan(eform)):
        return 0.5
    return float(1.0 / (1.0 + math.exp(eform / _STAB_SCALE)))


class ScreeningCascade:
    """Orquesta Tier 0-2 sobre un batch de GeneratedCandidate.

    Parámetros
    ----------
    config       : dict completo de generator.yaml
    project_root : raíz del proyecto (para resolver model_path)
    """

    def __init__(self, config: dict, project_root: Optional[Path] = None):
        self._cfg = config
        self._root = Path(project_root) if project_root else Path.cwd()
        self._scr = config.get("screening", {})
        self._acq = config.get("acquisition", {})
        self._filter = PhysicalFilter(config)
        self._builder = ABX3StructureBuilder(config, random_seed=config.get("random_seed", 42))

        self._beta = float(self._acq.get("beta", 1.0))
        self._eform_max = float(self._scr.get("eform_max_eV_atom", 0.20))
        self._use_surrogate = bool(self._scr.get("tier1_surrogate", True))
        self._use_mlff = bool(self._scr.get("tier2_mlff", True))

        self._surrogate = None  # lazy
        self._gnn = None        # lazy

    # ── Carga perezosa de modelos ─────────────────────────────────────────────
    def _load_surrogate(self):
        if self._surrogate is not None or not self._use_surrogate:
            return self._surrogate
        from ml_surrogate.model import SurrogateEnsemble
        mp = self._root / "models" / "surrogate_bandgap.pkl"
        if mp.exists():
            try:
                self._surrogate = SurrogateEnsemble.load(mp)
            except Exception as e:
                warnings.warn(f"Cascade: surrogate no cargó ({e}); Tier 1 omitido.")
        else:
            warnings.warn(f"Cascade: surrogate no encontrado en {mp}; Tier 1 omitido.")
        return self._surrogate

    def _load_gnn(self):
        if self._gnn is not None or not self._use_mlff:
            return self._gnn
        from ml_surrogate.gnn_predictor import GNNPredictor
        self._gnn = GNNPredictor(device="cpu")
        return self._gnn

    # ── Features desde un candidato mixto (radios efectivos) ──────────────────
    @staticmethod
    def _features(c: GeneratedCandidate,
                  eform: Optional[float] = None,
                  eg_gga: Optional[float] = None) -> dict:
        def eff(fr: dict, table: dict) -> float:
            return sum(f * table[s] for s, f in fr.items())
        A, B, X = c.fractions["A"], c.fractions["B"], c.fractions["X"]
        r_A, r_B, r_X = eff(A, IONIC_RADII), eff(B, IONIC_RADII), eff(X, IONIC_RADII)
        chi_A, chi_B, chi_X = eff(A, ELECTRONEG), eff(B, ELECTRONEG), eff(X, ELECTRONEG)
        q_A, q_B, q_X = eff(A, CHARGES), eff(B, CHARGES), eff(X, CHARGES)
        t = goldschmidt(r_A, r_B, r_X)
        mu = octahedral_factor(r_B, r_X)
        a = lattice_est(r_B, r_X)
        nan = float("nan")
        return {
            "r_A": r_A, "r_B": r_B, "r_X": r_X,
            "chi_A": chi_A, "chi_B": chi_B, "chi_X": chi_X,
            "q_A": q_A, "q_B": q_B, "q_X": q_X,
            "tolerance_t": t, "oct_factor": mu,
            "a_lat_est_A": a, "vol_est_A3": a ** 3,
            "delta_chi_BX": chi_X - chi_B, "mu_BX": r_B + r_X,
            "is_organic_A": float(c.is_organic_A),
            "a_lat_mp_A": nan,
            "band_gap_gga_eV": eg_gga if eg_gga is not None else nan,
            "Eform_eV_atom": eform if eform is not None else nan,
        }

    # ── Pipeline ──────────────────────────────────────────────────────────────
    def screen(self, candidates: list[GeneratedCandidate],
               run_mlff: Optional[bool] = None) -> pd.DataFrame:
        """Corre la cascada y devuelve un DataFrame rankeado con indicadores.

        Columnas: candidate_id, formula, generation_mode, is_organic_A,
        tolerance_t, oct_factor, vol_est_A3, Eg_surrogate_eV, Eg_sigma_eV,
        band_score, in_pv_window, Eg_gnn_eV, Eform_eV_atom, Eform_std_eV_atom,
        is_stable, stab_score, ucb_bonus, total_score, passed_eform, tier_reached.
        """
        use_mlff = self._use_mlff if run_mlff is None else run_mlff

        # ── Tier 0: descriptores físicos ─────────────────────────────────────
        fr = self._filter.apply(candidates)
        passed = fr.passed
        rows: list[dict] = []
        for c in passed:
            rows.append({
                "candidate_id": c.candidate_id,
                "formula": c.formula,
                "generation_mode": c.generation_mode,
                "is_organic_A": c.is_organic_A,
                "tolerance_t": c.tolerance_t,
                "oct_factor": c.oct_factor,
                "vol_est_A3": c.vol_est_A3,
                "Eg_surrogate_eV": None, "Eg_sigma_eV": None,
                "band_score": 0.0, "in_pv_window": None,
                "Eg_gnn_eV": None, "Eform_eV_atom": None,
                "Eform_std_eV_atom": None, "is_stable": None,
                "stab_score": 0.5, "ucb_bonus": 0.0, "total_score": 0.0,
                "passed_eform": True, "tier_reached": 0,
            })

        if not passed:
            return pd.DataFrame(rows)

        feats = [self._features(c) for c in passed]

        # ── Tier 1: surrogate bandgap (composición) ──────────────────────────
        sur = self._load_surrogate()
        if sur is not None:
            try:
                Xm = build_X(pd.DataFrame(feats), sur.feature_cols)
                means, stds = sur.predict_batch(Xm)
            except Exception as e:
                warnings.warn(f"Cascade Tier1 falló: {e}")
                means = [float("nan")] * len(passed)
                stds = [float("nan")] * len(passed)
            for row, mu, sd in zip(rows, means, stds):
                eg = float(mu)
                row["Eg_surrogate_eV"] = round(eg, 4)
                row["Eg_sigma_eV"] = round(float(sd), 4)
                row["band_score"] = round(_band_score(eg), 4)
                row["in_pv_window"] = bool(1.1 <= eg <= 1.8)
                row["ucb_bonus"] = round(self._beta * float(sd), 4)
                row["tier_reached"] = 1

        # ── Tier 2: MLFF energía de formación / estabilidad ──────────────────
        if use_mlff:
            gnn = self._load_gnn()
            if gnn is not None:
                from pymatgen.io.ase import AseAtomsAdaptor
                structs = []
                for c in passed:
                    try:
                        atoms, meta = self._builder.build(c, out_dir=None, export=False)
                        src = "pseudoatom" if meta.get("molecular_A_placeholder") else "cubic"
                        structs.append((AseAtomsAdaptor.get_structure(atoms), src))
                    except Exception:
                        structs.append((None, "failed"))
                for row, (st, src) in zip(rows, structs):
                    if st is None:
                        continue
                    try:
                        res = gnn.predict(st, structure_source=src)
                        row["Eg_gnn_eV"] = round(res.Eg_eV, 4)
                        # Combinar Eform robustamente: MEGNet-Eform a veces da NaN
                        # (el ensemble de GNNResult lo propaga). Promediar solo
                        # valores finitos de MEGNet/M3GNet.
                        vals = [v for v in (res.Eform_megnet_eV_atom,
                                            res.Eform_m3gnet_eV_atom)
                                if v is not None and not math.isnan(v)]
                        if vals:
                            eform = sum(vals) / len(vals)
                            row["Eform_eV_atom"] = round(eform, 4)
                            row["Eform_std_eV_atom"] = (round(abs(vals[0] - vals[1]) / 2, 4)
                                                        if len(vals) == 2 else None)
                            row["is_stable"] = bool(eform < -0.1)
                            row["stab_score"] = round(_stab_score(eform), 4)
                            row["passed_eform"] = bool(eform <= self._eform_max)
                        row["tier_reached"] = 2
                    except Exception:
                        pass

        # ── Score de adquisición ─────────────────────────────────────────────
        for row in rows:
            row["total_score"] = round(
                row["band_score"] + row["stab_score"] + row["ucb_bonus"], 4)

        df = pd.DataFrame(rows).sort_values("total_score", ascending=False).reset_index(drop=True)
        return df

    def select_for_dft(self, df: pd.DataFrame, n: Optional[int] = None) -> pd.DataFrame:
        """Selecciona candidatos para DFT.

        Filtra por estabilidad (passed_eform). Si `n` (o config
        `screening.n_dft_per_batch`) es <= 0 o None → devuelve TODOS los que pasen
        estabilidad (rankeados por score). Si n > 0 → solo el top-N.
        """
        if n is None:
            n = int(self._scr.get("n_dft_per_batch", 0))
        keep = df[df["passed_eform"]].copy().reset_index(drop=True)
        if n and n > 0:
            keep = keep.head(n)
        return keep.reset_index(drop=True)
