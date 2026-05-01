"""Scissor operator and HSE06+SOC corrections for CsPbI3 band gaps.

Two correction strategies:

  A (fallback — scissor):
      Eg_corrected = E_PBE + χSOC + χHSE
      χSOC = Eg(PBE+SOC) − Eg(PBE)   — negative for Pb 6p
      χHSE = Eg(HSE06)   − Eg(PBE)   — positive
      Assumes χSOC and χHSE are additive (error 0.05–0.15 eV, systematic).

  B (recommended — HSE06+SOC):
      Eg_primary = Eg computed from HSE06 .gpw via soc_eigenstates()
      Eliminates additivity assumption; δ_add = Eg(B) − Eg(A) quantifies error.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from .postprocessing import get_bandgap, get_soc_bandgap

logger = logging.getLogger(__name__)


@dataclass
class ScissorResult:
    """Holds all intermediate and final band gap values."""

    phase: str
    e_pbe_d3: float
    chi_soc: float
    chi_hse: float
    e_corrected: float                          # Strategy A: PBE + χSOC + χHSE
    e_experimental: Optional[float] = None
    mae_vs_experiment: Optional[float] = None
    # Strategy B — HSE06+SOC direct
    e_hse_soc: Optional[float] = None          # Eg from HSE06 .gpw + perturbative SOC
    delta_additivity: Optional[float] = None   # e_hse_soc − e_corrected (Strategy B − A)
    mae_vs_hse_soc: Optional[float] = None     # |e_hse_soc − e_experimental|
    chi_soc_source: str = "computed"           # "computed" | "literature"
    chi_hse_source: str = "literature"         # "computed" | "literature"
    k_mesh_hse: Optional[list] = None          # k-mesh used for HSE06 calculation


class ScissorCorrection:
    """Compute and apply the scissor operator correction for CsPbI3.

    The correction decomposes as:
        Eg_corr = E_PBE+D3 + χSOC + χHSE

    where χSOC and χHSE are evaluated on lower-cost calculations and
    then transferred to the dispersion-corrected PBE baseline.
    """

    # Per-phase reference values. "this work" fields updated after each run.
    REFERENCE: dict = {
        "alpha": {
            "experimental": 1.73,
            "exp_reference": "Sutton et al. ACS Energy Lett. 2018",
            "pbe_no_soc": 1.089,        # this work
            "pbe_soc": 0.300,           # this work
            "chi_soc_this_work": -0.789,
            "hse06_no_soc": None,       # pending HSE06 run
            "hse06_soc": None,          # pending HSE06+SOC run
        },
        "gamma": {
            "experimental": 1.68,
            "exp_reference": "Steele et al. JACS 2019",
            "pbe_no_soc": None,
            "pbe_soc": None,
            "hse06_no_soc": None,
            "hse06_soc": None,
        },
        "delta": {
            "experimental": 2.82,
            "exp_reference": "Sutton et al. ACS Energy Lett. 2018",
            "pbe_no_soc": None,
            "pbe_soc": None,
            "hse06_no_soc": None,
            "hse06_soc": None,
        },
    }

    def __init__(self, reference: dict | None = None, phase: str = "alpha") -> None:
        if reference:
            self.REFERENCE = reference
        self._phase = phase

    # ------------------------------------------------------------------
    # Core correction calculations
    # ------------------------------------------------------------------

    def compute_chi_soc(
        self,
        gpw_pbe: str | Path,
        gpw_pbe_soc: str | Path | None = None,
    ) -> float:
        """Compute χSOC = Eg(PBE+SOC) − Eg(PBE).

        If gpw_pbe_soc is None, uses stored REFERENCE values.
        """
        if gpw_pbe_soc is not None:
            e_pbe = get_bandgap(gpw_pbe, soc=False)
            e_pbe_soc = get_soc_bandgap(gpw_pbe_soc)
        else:
            e_pbe = get_bandgap(gpw_pbe, soc=False)
            phase_ref = self.REFERENCE.get(self._phase, {})
            e_pbe_soc = phase_ref.get("pbe_soc") or self.REFERENCE.get("alpha", {}).get("pbe_soc", 0.60)

        chi_soc = e_pbe_soc - e_pbe
        logger.info("χSOC = %.4f eV (Eg_PBE=%.4f, Eg_PBE+SOC=%.4f)", chi_soc, e_pbe, e_pbe_soc)
        return chi_soc

    def compute_chi_hse(
        self,
        gpw_pbe: str | Path,
        gpw_hse: str | Path | None = None,
    ) -> float:
        """Compute χHSE = Eg(HSE06) − Eg(PBE).

        If gpw_hse is None, uses stored REFERENCE values.
        """
        if gpw_hse is not None:
            e_pbe = get_bandgap(gpw_pbe, soc=False)
            e_hse = get_bandgap(gpw_hse, soc=False)
        else:
            e_pbe = get_bandgap(gpw_pbe, soc=False)
            phase_ref = self.REFERENCE.get(self._phase, {})
            e_hse = phase_ref.get("hse06_no_soc") or 1.76  # literature fallback

        chi_hse = e_hse - e_pbe
        logger.info("χHSE = %.4f eV (Eg_PBE=%.4f, Eg_HSE=%.4f)", chi_hse, e_pbe, e_hse)
        return chi_hse

    def corrected_gap(
        self,
        e_pbe_d3: float,
        chi_soc: float,
        chi_hse: float,
    ) -> float:
        """Compute the scissor-corrected band gap.

        Args:
            e_pbe_d3: PBE+D3 band gap (eV).
            chi_soc: SOC correction (eV), typically negative for Pb.
            chi_hse: HSE06 correction (eV), typically positive.

        Returns:
            Corrected band gap in eV.
        """
        result = e_pbe_d3 + chi_soc + chi_hse
        logger.info(
            "Corrected gap: %.4f = %.4f (PBE+D3) + %.4f (χSOC) + %.4f (χHSE)",
            result, e_pbe_d3, chi_soc, chi_hse,
        )
        return result

    def apply_scissor_to_bands(
        self,
        band_structure,
        vbm_shift: float = 0.0,
        cbm_shift: float = 0.0,
    ):
        """Apply rigid scissor shifts to valence and conduction bands.

        Modifies the BandStructure object in-place by shifting eigenvalues:
          - Bands below EF shifted by vbm_shift
          - Bands above EF shifted by cbm_shift

        Args:
            band_structure: ASE BandStructure object from calc.band_structure().
            vbm_shift: Energy shift applied to valence bands (eV).
            cbm_shift: Energy shift applied to conduction bands (eV).

        Returns:
            Modified BandStructure (same object, modified in place).
        """
        energies = band_structure.energies.copy()
        ef = band_structure.reference

        vb_mask = energies <= ef
        cb_mask = energies > ef

        energies[vb_mask] += vbm_shift
        energies[cb_mask] += cbm_shift
        band_structure.energies = energies
        return band_structure

    def run_full_correction(
        self,
        gpw_pbe: str | Path,
        gpw_pbe_soc: str | Path | None = None,
        gpw_hse: str | Path | None = None,
        phase: str = "alpha",
    ) -> ScissorResult:
        """Run the complete scissor correction pipeline.

        Returns a ScissorResult with all intermediate values.
        """
        e_pbe = get_bandgap(gpw_pbe, soc=False)
        chi_soc = self.compute_chi_soc(gpw_pbe, gpw_pbe_soc)
        chi_hse = self.compute_chi_hse(gpw_pbe, gpw_hse)
        # Treat the PBE gap as the PBE+D3 baseline (D3 has minimal effect on gap)
        e_corr = self.corrected_gap(e_pbe, chi_soc, chi_hse)

        phase_ref = self.REFERENCE.get(phase, {})
        exp = phase_ref.get("experimental")
        mae = abs(e_corr - exp) if exp is not None else None
        chi_soc_src = "computed" if gpw_pbe_soc is not None else "literature"
        chi_hse_src = "computed" if gpw_hse is not None else "literature"

        return ScissorResult(
            phase=phase,
            e_pbe_d3=e_pbe,
            chi_soc=chi_soc,
            chi_hse=chi_hse,
            e_corrected=e_corr,
            e_experimental=exp,
            mae_vs_experiment=mae,
            chi_soc_source=chi_soc_src,
            chi_hse_source=chi_hse_src,
        )

    def compute_hse_soc_gap(
        self,
        hse_gpw: str | Path,
        result: ScissorResult | None = None,
    ) -> float:
        """Compute Eg(HSE06+SOC) via perturbative SOC on an HSE06 .gpw.

        If a ScissorResult is provided, populates e_hse_soc and delta_additivity
        in-place and recomputes mae_vs_hse_soc against the experimental value.

        Returns Eg(HSE06+SOC) in eV.
        """
        e_hse_soc = get_soc_bandgap(hse_gpw)
        logger.info("Eg(HSE06+SOC) = %.4f eV", e_hse_soc)

        if result is not None:
            result.e_hse_soc = e_hse_soc
            result.delta_additivity = e_hse_soc - result.e_corrected
            if result.e_experimental is not None:
                result.mae_vs_hse_soc = abs(e_hse_soc - result.e_experimental)
            logger.info(
                "δ_add = %.4f eV (HSE06+SOC vs scissor; negative = scissor overestimates)",
                result.delta_additivity,
            )

        return e_hse_soc

    def report(self, phase: str = "alpha") -> None:
        """Print a comparison table vs. literature / experimental values."""
        ref = self.REFERENCE.get(phase, {})
        header = f"\n{'Method':<22} {'Eg (eV)':>10} {'vs. Exp (eV)':>14}"
        sep = "-" * 50

        rows = [
            ("PBE (no SOC)", ref.get("pbe_no_soc")),
            ("PBE + SOC", ref.get("pbe_soc")),
            ("HSE06 (no SOC)", ref.get("hse06_no_soc")),
            ("HSE06 + SOC", ref.get("hse06_soc")),
            ("Experimental", ref.get("experimental")),
        ]
        exp = ref.get("experimental", None)

        print(f"\nBand gap comparison — {phase}-CsPbI3")
        print(header)
        print(sep)
        for name, val in rows:
            if val is None:
                continue
            delta = f"{val - exp:+.2f}" if exp and name != "Experimental" else "  ref"
            print(f"{name:<22} {val:>10.3f} {delta:>14}")
        print(sep)
