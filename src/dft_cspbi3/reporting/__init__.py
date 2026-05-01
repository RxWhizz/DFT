"""Automated report generation for the DFT-CsPbI3 pipeline.

Modules
-------
validation_report    — validation_report.md: parameters, convergence, SCF, physical checks.
vibrational_analysis — vibrational_analysis.md: Hessian eigenvalues, phonon frequencies.
methodology          — methodology.md: theoretical framework (Kohn-Sham, BO, PAW, SOC).
assumptions          — assumptions.md: hypotheses, approximations, validity range.
"""

from .validation_report import ValidationData, generate_validation_report
from .vibrational_analysis import generate_vibrational_report
from .methodology import generate_methodology
from .assumptions import generate_assumptions

__all__ = [
    "ValidationData",
    "generate_validation_report",
    "generate_vibrational_report",
    "generate_methodology",
    "generate_assumptions",
]
