"""GNN property predictors via MATGL pretrained models.

Replaces all semi-empirical/heuristic estimators in the pipeline:
  step_semiempirical()  (B_BASE + X_SHIFT)   →  predict_bandgap()  [MEGNet-BandGap]
  step_ainagent_score() (band+gold heuristic) →  GNNAcquisition     [GNN UCB]
  _estimate_bandgap()   (candidate_space.py)  →  predict_bandgap()  [MEGNet-BandGap]

Properties NOT predicted (no pretrained MATGL model exists for halide perovskites):
  DOS, effective mass, dielectric constant, optical spectra.
  These are left as None in GNNResult; ai_spectra_top8.py heuristics are removed.

Models used (all offline-accessible via ~/.cache/matgl):
  MEGNet-BandGap-mfi-MP-2019.4.1  — bandgap (cached, already used in AI-04)
  MEGNet-Eform-MP-2018.6.1        — formation energy/atom
  M3GNet-Eform-MP-2018.6.1        — second Eform estimator (ensemble uncertainty)

Uncertainty: MEGNet and M3GNet are deterministic point estimators. Eform uncertainty
is approximated as |Ef_MEGNet - Ef_M3GNet| / 2 (model disagreement). For bandgap,
no second model is available; uncertainty is reported as None.
"""
from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from typing import Optional

import torch

log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Result dataclass
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class GNNResult:
    """Properties predicted by GNN for one ABX3 structure.

    None values indicate the model was unavailable or failed.
    Eg in eV; Eform in eV/atom (negative = stable).
    """
    Eg_eV: float                          # MEGNet-BandGap-mfi
    Eform_megnet_eV_atom: Optional[float] # MEGNet-Eform
    Eform_m3gnet_eV_atom: Optional[float] # M3GNet-Eform
    Eform_eV_atom: Optional[float]        # ensemble mean
    Eform_std_eV_atom: Optional[float]    # |MEGNet - M3GNet| / 2
    structure_source: str                 # "gpw" | "cubic" | "pseudoatom"
    model_warnings: list[str] = field(default_factory=list)

    @property
    def in_pv_window(self) -> bool:
        return 1.1 <= self.Eg_eV <= 1.8

    @property
    def is_stable(self) -> bool:
        """Heuristic: Eform < −0.1 eV/atom → stable (hull distance proxy)."""
        return self.Eform_eV_atom is not None and self.Eform_eV_atom < -0.1


# ──────────────────────────────────────────────────────────────────────────────
# matgl 3.0.1 patch — broadcast bug with old MEGNet checkpoints
# ──────────────────────────────────────────────────────────────────────────────

def _patch_megnet() -> None:
    try:
        import matgl.layers._graph_convolution_pyg as gcm
        _orig = gcm._broadcast_to_nodes

        def _fixed(sf, nb, nn):
            while sf.dim() > 2:
                sf = sf.squeeze(0)
            return _orig(sf, nb, nn)

        gcm._broadcast_to_nodes = _fixed
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────────────────────
# GNNPredictor
# ──────────────────────────────────────────────────────────────────────────────

class GNNPredictor:
    """MATGL GNN property predictor — no heuristic fallbacks.

    Models are lazy-loaded on first use. Call predict_batch() to preload all
    models once and amortize the load cost over a batch.

    Parameters
    ----------
    device : str
        "cpu" or "cuda". MEGNet/M3GNet are small enough to run on CPU
        for the 8-material top-list (~0.5 s each on single core).
    """

    def __init__(self, device: str = "cpu") -> None:
        self._device = device
        self._megnet_bg: object | None = None
        self._megnet_ef: object | None = None
        self._m3gnet_ef: object | None = None
        _patch_megnet()

    # ── Lazy loaders ────────────────────────────────────────────────────────

    def _load_megnet_bg(self) -> None:
        if self._megnet_bg is not None:
            return
        import matgl
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self._megnet_bg = matgl.load_model("MEGNet-BandGap-mfi-MP-2019.4.1")
        log.info("Loaded MEGNet-BandGap-mfi-MP-2019.4.1")

    def _load_megnet_ef(self) -> None:
        if self._megnet_ef is not None:
            return
        try:
            import matgl
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                self._megnet_ef = matgl.load_model("MEGNet-Eform-MP-2018.6.1")
            log.info("Loaded MEGNet-Eform-MP-2018.6.1")
        except Exception as exc:
            log.warning("MEGNet-Eform-MP-2018.6.1 unavailable: %s", exc)

    def _load_m3gnet_ef(self) -> None:
        if self._m3gnet_ef is not None:
            return
        try:
            import matgl
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                self._m3gnet_ef = matgl.load_model("M3GNet-Eform-MP-2018.6.1")
            log.info("Loaded M3GNet-Eform-MP-2018.6.1")
        except Exception as exc:
            log.warning("M3GNet-Eform-MP-2018.6.1 unavailable: %s", exc)

    def _preload_all(self) -> None:
        self._load_megnet_bg()
        self._load_megnet_ef()
        self._load_m3gnet_ef()

    # ── Predictions ─────────────────────────────────────────────────────────

    def predict_bandgap(self, structure) -> float:
        """GNN bandgap from MEGNet-BandGap (insulator state=2).

        Returns bandgap in eV, clamped to ≥ 0.
        Raises RuntimeError if model fails (no heuristic fallback).
        """
        self._load_megnet_bg()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            Eg = float(
                self._megnet_bg.predict_structure(
                    structure, state_attr=torch.tensor([[2]])
                )
            )
        return max(Eg, 0.0)

    def predict_eform_megnet(self, structure) -> Optional[float]:
        """Formation energy/atom from MEGNet-Eform. Returns None if unavailable."""
        self._load_megnet_ef()
        if self._megnet_ef is None:
            return None
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                return float(self._megnet_ef.predict_structure(structure))
        except Exception as exc:
            log.warning("MEGNet-Eform prediction failed: %s", exc)
            return None

    def predict_eform_m3gnet(self, structure) -> Optional[float]:
        """Formation energy/atom from M3GNet-Eform. Returns None if unavailable."""
        self._load_m3gnet_ef()
        if self._m3gnet_ef is None:
            return None
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                return float(self._m3gnet_ef.predict_structure(structure))
        except Exception as exc:
            log.warning("M3GNet-Eform prediction failed: %s", exc)
            return None

    def predict(self, structure, structure_source: str = "unknown") -> GNNResult:
        """Run all models on one structure. Raises on bandgap failure."""
        model_warnings: list[str] = []

        Eg = self.predict_bandgap(structure)  # hard failure → propagate

        Ef_meg = self.predict_eform_megnet(structure)
        Ef_m3g = self.predict_eform_m3gnet(structure)

        if Ef_meg is not None and Ef_m3g is not None:
            Ef_mean = (Ef_meg + Ef_m3g) / 2.0
            Ef_std = abs(Ef_meg - Ef_m3g) / 2.0
        elif Ef_meg is not None:
            Ef_mean, Ef_std = Ef_meg, None
        elif Ef_m3g is not None:
            Ef_mean, Ef_std = Ef_m3g, None
        else:
            Ef_mean, Ef_std = None, None

        if structure_source == "pseudoatom":
            model_warnings.append(
                "Pseudo-atom substitution used for organic A-site. "
                "Treat as ranking signal, not absolute value."
            )

        return GNNResult(
            Eg_eV=Eg,
            Eform_megnet_eV_atom=Ef_meg,
            Eform_m3gnet_eV_atom=Ef_m3g,
            Eform_eV_atom=Ef_mean,
            Eform_std_eV_atom=Ef_std,
            structure_source=structure_source,
            model_warnings=model_warnings,
        )

    def predict_batch(
        self,
        structures_with_sources: list[tuple[object, str]],
    ) -> list[GNNResult]:
        """Predict over a list of (structure, source) pairs.

        Preloads all models once, then runs sequentially.
        """
        self._preload_all()
        return [self.predict(s, src) for s, src in structures_with_sources]
