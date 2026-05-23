"""Clasifica estabilidad por fonones/Hessiano."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


# Enum.


class StabilityClass(enum.Enum):
    STABLE = "stable"
    METASTABLE = "metastable"
    UNSTABLE = "unstable"
    UNKNOWN = "unknown"


# Umbrales.

_NOISE_CM1 = 10.0
_SOFT_CM1 = 100.0
_HESS_NOISE = 0.05      # eV/Å²; piso ruido autovalor Hessian


# Datos.


@dataclass
class StabilityReport:
    """Estabilidad combinada fonones/Hessiano."""

    classification: StabilityClass
    source: str
    n_imaginary_phonons: int
    max_imaginary_cm1: float              # 0.0 si estable
    n_negative_hessian: int
    min_hessian_eigval: float             # eV/Å²
    diagnosis: str
    recommendations: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)

    @property
    def is_valid_structure(self) -> bool:
        return self.classification in (StabilityClass.STABLE, StabilityClass.METASTABLE)


# Clasificadores.


def classify_from_phonons(phonon_result) -> StabilityReport:
    """Clasifica estabilidad desde PhononResult."""
    n_imag = phonon_result.n_imaginary
    max_imag = phonon_result.max_imaginary_cm1  # most negative, 0 si none

    if n_imag == 0:
        cls = StabilityClass.STABLE
        diagnosis = (
            f"Frecuencias phonon reales y positivas "
            f"(min = {phonon_result.frequencies_cm1.min():.1f} cm⁻¹). "
            "Estructura en minimo energetico stable."
        )
        recs: list[str] = []
    elif abs(max_imag) < _SOFT_CM1:
        cls = StabilityClass.METASTABLE
        diagnosis = (
            f"{n_imag} modos imaginarios con |ω| < {_SOFT_CM1} cm⁻¹ "
            f"(peor: {max_imag:.1f} cm⁻¹). "
            "Puede ser ruido numerico, PES plana o modo blando cerca transicion."
        )
        recs = [
            "Aumentar supercelda; descartar artefactos.",
            "Relajar otra vez con fmax < 0.01 eV/Å.",
            "Revisar transiciones cercanas: tilt octaedrico.",
        ]
    else:
        cls = StabilityClass.UNSTABLE
        diagnosis = (
            f"{n_imag} modos imaginarios con |ω| hasta {abs(max_imag):.1f} cm⁻¹. "
            "Estructura = punto silla; relajara a configuracion mas baja."
        )
        recs = [
            "Seguir autovector imaginario hasta minimo real.",
            "Usar supercelda mayor o geometria inicial distinta.",
            "Revisar tilt octaedrico u orden sitio A suprimido.",
        ]

    return StabilityReport(
        classification=cls,
        source="phonons",
        n_imaginary_phonons=n_imag,
        max_imaginary_cm1=max_imag,
        n_negative_hessian=0,
        min_hessian_eigval=float("nan"),
        diagnosis=diagnosis,
        recommendations=recs,
        flags=phonon_result.flags,
    )


def classify_from_hessian(hessian_result) -> StabilityReport:
    """Clasifica estabilidad desde HessianResult."""
    n_neg = hessian_result.n_negative
    min_eigval = hessian_result.min_eigenvalue

    if n_neg == 0:
        cls = StabilityClass.STABLE
        diagnosis = (
            f"Autovalores Hessian ≥ −{_HESS_NOISE} eV/Å² "
            f"(min = {min_eigval:.4f} eV/Å²). "
            "Hessian Γ semidefinido positivo."
        )
        recs: list[str] = []
    else:
        cls = StabilityClass.UNSTABLE
        diagnosis = (
            f"{n_neg} autovalores Hessian negativos "
            f"(min = {min_eigval:.4f} eV/Å²). "
            "Estructura no esta en minimo local."
        )
        recs = [
            "Relajar con convergencia mas estricta.",
            "Seguir autovector negativo para salir de punto silla.",
            "Correr phonon completo con superceldas para confirmar instability.",
        ]

    return StabilityReport(
        classification=cls,
        source="hessian",
        n_imaginary_phonons=0,
        max_imaginary_cm1=0.0,
        n_negative_hessian=n_neg,
        min_hessian_eigval=min_eigval,
        diagnosis=diagnosis,
        recommendations=recs,
        flags=hessian_result.flags,
    )


def classify_combined(
    hessian_result,
    phonon_result,
) -> StabilityReport:
    """Une veredictos Hessiano + fonones."""
    ph_report = classify_from_phonons(phonon_result)
    h_report = classify_from_hessian(hessian_result)

    # Resultado phonon domina.
    combined_flags = list(dict.fromkeys(ph_report.flags + h_report.flags))

    if ph_report.classification == StabilityClass.STABLE and h_report.classification == StabilityClass.STABLE:
        cls = StabilityClass.STABLE
    elif ph_report.classification == StabilityClass.UNSTABLE or h_report.classification == StabilityClass.UNSTABLE:
        cls = StabilityClass.UNSTABLE
    else:
        cls = StabilityClass.METASTABLE

    diagnosis = (
        f"Analisis phonon: {ph_report.diagnosis}\n"
        f"Analisis Hessian (Γ): {h_report.diagnosis}"
    )
    recs = list(dict.fromkeys(ph_report.recommendations + h_report.recommendations))

    return StabilityReport(
        classification=cls,
        source="both",
        n_imaginary_phonons=ph_report.n_imaginary_phonons,
        max_imaginary_cm1=ph_report.max_imaginary_cm1,
        n_negative_hessian=h_report.n_negative_hessian,
        min_hessian_eigval=h_report.min_hessian_eigval,
        diagnosis=diagnosis,
        recommendations=recs,
        flags=combined_flags,
    )
