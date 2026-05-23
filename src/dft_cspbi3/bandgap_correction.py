"""Scissor operator y correcciones HSE06+SOC para bandgaps CsPbI3."""

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
    """Guarda bandgaps intermedios y finales."""

    phase: str
    e_pbe_d3: float
    chi_soc: float
    chi_hse: float
    e_corrected: float                          # Strategy A
    e_experimental: Optional[float] = None
    mae_vs_experiment: Optional[float] = None
    # Strategy B - HSE06+SOC direct
    e_hse_soc: Optional[float] = None          # Eg desde HSE06.gpw + perturbative SOC
    delta_additivity: Optional[float] = None
    mae_vs_hse_soc: Optional[float] = None
    chi_soc_source: str = "computed"
    chi_hse_source: str = "literature"
    k_mesh_hse: Optional[list] = None          # k-mesh usado para HSE06 cálculo


class ScissorCorrection:
    """Calcula y aplica correccion scissor para CsPbI3."""

    # Referencias planas: compatibilidad tests/API antigua.
    # Referencias anidadas: uso por fase.
    REFERENCE: dict = {
        "experimental_alpha": 1.73,
        "pbe_no_soc": 1.44,
        "pbe_soc": 0.60,
        "hse06_no_soc": 1.76,
        "hse06_soc": 1.55,
        "alpha": {
            "experimental": 1.73,
            "exp_reference": "Sutton et al. ACS Energy Lett. 2018",
            "pbe_no_soc": 1.089,
            "pbe_soc": 0.300,
            "chi_soc_this_work": -0.789,
            "hse06_no_soc": 1.76,
            "hse06_soc": 1.55,
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

    def _ref(self, phase: str, key: str, default=None):
        """Lee referencia por fase; cae a clave plana."""
        phase_ref = self.REFERENCE.get(phase, {})
        if isinstance(phase_ref, dict) and key in phase_ref:
            return phase_ref[key]
        if key == "experimental":
            flat_key = f"experimental_{phase}"
            if flat_key in self.REFERENCE:
                return self.REFERENCE[flat_key]
        return self.REFERENCE.get(key, default)

    # Core correction cálculos

    def compute_chi_soc(
        self,
        gpw_pbe: str | Path,
        gpw_pbe_soc: str | Path | None = None,
    ) -> float:
        """Calcula χSOC = Eg(PBE+SOC) − Eg(PBE)."""
        if gpw_pbe_soc is not None:
            e_pbe = get_bandgap(gpw_pbe, soc=False)
            e_pbe_soc = get_soc_bandgap(gpw_pbe_soc)
        else:
            e_pbe = get_bandgap(gpw_pbe, soc=False)
            e_pbe_soc = self._ref(self._phase, "pbe_soc", 0.60)

        chi_soc = e_pbe_soc - e_pbe
        logger.info("χSOC = %.4f eV (Eg_PBE=%.4f, Eg_PBE+SOC=%.4f)", chi_soc, e_pbe, e_pbe_soc)
        return chi_soc

    def compute_chi_hse(
        self,
        gpw_pbe: str | Path,
        gpw_hse: str | Path | None = None,
    ) -> float:
        """Calcula χHSE = Eg(HSE06) − Eg(PBE)."""
        if gpw_hse is not None:
            e_pbe = get_bandgap(gpw_pbe, soc=False)
            e_hse = get_bandgap(gpw_hse, soc=False)
        else:
            e_pbe = get_bandgap(gpw_pbe, soc=False)
            e_hse = self._ref(self._phase, "hse06_no_soc", 1.76)

        chi_hse = e_hse - e_pbe
        logger.info("χHSE = %.4f eV (Eg_PBE=%.4f, Eg_HSE=%.4f)", chi_hse, e_pbe, e_hse)
        return chi_hse

    def corrected_gap(
        self,
        e_pbe_d3: float,
        chi_soc: float,
        chi_hse: float,
    ) -> float:
        """Calcula bandgap corregido scissor."""
        result = round(e_pbe_d3 + chi_soc + chi_hse, 12)
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
        """Aplica desplazamientos rigidos a bandas valencia/conduccion."""
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
        """Ejecuta flujo scissor completo."""
        e_pbe = get_bandgap(gpw_pbe, soc=False)
        chi_soc = self.compute_chi_soc(gpw_pbe, gpw_pbe_soc)
        chi_hse = self.compute_chi_hse(gpw_pbe, gpw_hse)
        # Treat PBE gap as PBE+D3 baseline (D3 has minimal effect en gap)
        e_corr = self.corrected_gap(e_pbe, chi_soc, chi_hse)

        exp = self._ref(phase, "experimental")
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
        """Calcula Eg(HSE06+SOC) via SOC perturbativo en HSE06.gpw."""
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
        """Imprime tabla comparativa."""
        ref = self.REFERENCE.get(phase, {})
        if not isinstance(ref, dict):
            ref = {}
        header = f"\n{'Metodo':<22} {'Eg (eV)':>10} {'vs. Exp (eV)':>14}"
        sep = "-" * 50

        rows = [
            ("PBE (sin SOC)", self._ref(phase, "pbe_no_soc")),
            ("PBE + SOC", self._ref(phase, "pbe_soc")),
            ("HSE06 (sin SOC)", self._ref(phase, "hse06_no_soc")),
            ("HSE06 + SOC", self._ref(phase, "hse06_soc")),
            ("Experimental", self._ref(phase, "experimental")),
        ]
        exp = self._ref(phase, "experimental")

        print(f"\nComparacion bandgap — {phase}-CsPbI3")
        print(header)
        print(sep)
        for name, val in rows:
            if val is None:
                continue
            delta = f"{val - exp:+.2f}" if exp and name != "Experimental" else "  ref"
            print(f"{name:<22} {val:>10.3f} {delta:>14}")
        print(sep)
