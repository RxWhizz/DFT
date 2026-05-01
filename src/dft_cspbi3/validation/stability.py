"""Structural stability classification from phonon/Hessian results.

Classification criteria (per user specification):

  STABLE      — no imaginary phonon frequencies above numerical noise (< 10 cm⁻¹)
  METASTABLE  — small imaginary frequencies (10–100 cm⁻¹); possibly numerical noise,
                local minimum in a flat landscape, or soft mode near phase transition
  UNSTABLE    — clear imaginary modes (> 100 cm⁻¹); structure is a saddle point
                and will distort spontaneously

Hessian-only classification (single unit cell, Γ-point only):
  STABLE      — all eigenvalues ≥ -_ZERO_THRESH  (only translational modes ~0)
  UNSTABLE    — one or more clearly negative eigenvalues
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


# ---------------------------------------------------------------------------
# Enum
# ---------------------------------------------------------------------------


class StabilityClass(enum.Enum):
    STABLE = "stable"
    METASTABLE = "metastable"
    UNSTABLE = "unstable"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

_NOISE_CM1 = 10.0       # Below this: treated as numerical zero
_SOFT_CM1 = 100.0       # Below this (absolute): metastable
_HESS_NOISE = 0.05      # eV/Å²  — Hessian eigenvalue noise floor


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------


@dataclass
class StabilityReport:
    """Combined stability assessment from phonons and/or Hessian."""

    classification: StabilityClass
    source: str                           # "phonons", "hessian", or "both"
    n_imaginary_phonons: int
    max_imaginary_cm1: float              # 0.0 if stable
    n_negative_hessian: int
    min_hessian_eigval: float             # eV/Å²
    diagnosis: str
    recommendations: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)

    @property
    def is_valid_structure(self) -> bool:
        return self.classification in (StabilityClass.STABLE, StabilityClass.METASTABLE)


# ---------------------------------------------------------------------------
# Classification functions
# ---------------------------------------------------------------------------


def classify_from_phonons(phonon_result) -> StabilityReport:
    """Classify stability based on a PhononResult object.

    Args:
        phonon_result: PhononResult from validation.phonons.compute_phonons().

    Returns:
        StabilityReport.
    """
    n_imag = phonon_result.n_imaginary
    max_imag = phonon_result.max_imaginary_cm1  # most negative, 0 if none

    if n_imag == 0:
        cls = StabilityClass.STABLE
        diagnosis = (
            f"All phonon frequencies are real and positive "
            f"(min = {phonon_result.frequencies_cm1.min():.1f} cm⁻¹). "
            "Structure is at a stable energy minimum."
        )
        recs: list[str] = []
    elif abs(max_imag) < _SOFT_CM1:
        cls = StabilityClass.METASTABLE
        diagnosis = (
            f"{n_imag} imaginary mode(s) with |ω| < {_SOFT_CM1} cm⁻¹ "
            f"(worst: {max_imag:.1f} cm⁻¹). "
            "Could be numerical noise, a flat potential landscape, or a soft mode "
            "near a structural phase transition."
        )
        recs = [
            "Increase supercell size to check if modes are artefacts.",
            "Re-relax with tighter force criterion (fmax < 0.01 eV/Å).",
            "Check for nearby phase transitions (e.g. octahedral tilting).",
        ]
    else:
        cls = StabilityClass.UNSTABLE
        diagnosis = (
            f"{n_imag} imaginary mode(s) with |ω| up to {abs(max_imag):.1f} cm⁻¹. "
            "Structure is a saddle point and will relax to a lower-energy configuration."
        )
        recs = [
            "Follow the imaginary eigenvector to reach a true minimum.",
            "Consider a larger supercell or different initial geometry.",
            "Check if octahedral tilting or A-site ordering is suppressed.",
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
    """Classify stability based on a HessianResult object (Γ-point only).

    Args:
        hessian_result: HessianResult from validation.hessian.compute_hessian().

    Returns:
        StabilityReport. Less reliable than full phonon calculation.
    """
    n_neg = hessian_result.n_negative
    min_eigval = hessian_result.min_eigenvalue

    if n_neg == 0:
        cls = StabilityClass.STABLE
        diagnosis = (
            f"All Hessian eigenvalues ≥ −{_HESS_NOISE} eV/Å² "
            f"(min = {min_eigval:.4f} eV/Å²). "
            "Γ-point Hessian is positive semi-definite."
        )
        recs: list[str] = []
    else:
        cls = StabilityClass.UNSTABLE
        diagnosis = (
            f"{n_neg} negative Hessian eigenvalue(s) "
            f"(min = {min_eigval:.4f} eV/Å²). "
            "Structure is not at a local energy minimum."
        )
        recs = [
            "Re-relax the structure with tighter convergence.",
            "Follow the negative eigenvector to escape the saddle point.",
            "Run a full phonon calculation with supercells to confirm instability.",
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
    """Merge Hessian and phonon stability assessments into a single verdict.

    Phonon result takes precedence when both are available since it accounts
    for the full Brillouin zone (not only Γ).
    """
    ph_report = classify_from_phonons(phonon_result)
    h_report = classify_from_hessian(hessian_result)

    # Phonon result dominates; Hessian provides corroborating evidence
    combined_flags = list(dict.fromkeys(ph_report.flags + h_report.flags))

    if ph_report.classification == StabilityClass.STABLE and h_report.classification == StabilityClass.STABLE:
        cls = StabilityClass.STABLE
    elif ph_report.classification == StabilityClass.UNSTABLE or h_report.classification == StabilityClass.UNSTABLE:
        cls = StabilityClass.UNSTABLE
    else:
        cls = StabilityClass.METASTABLE

    diagnosis = (
        f"Phonon analysis: {ph_report.diagnosis}\n"
        f"Hessian analysis (Γ-point): {h_report.diagnosis}"
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
