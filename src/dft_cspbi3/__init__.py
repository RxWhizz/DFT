"""
dft-cspbi3-gpaw: Automated DFT simulations of CsPbI3 halide perovskite using GPAW.

Methodology:
  - PAW datasets: Cs.9.PBE, Pb.14.PBE (semicore 5d), I.7.PBE
  - Relaxation: PBEsol + DFT-D3, PW(450 eV), k=[6,6,6]
  - Band gap: scissor correction Eg = E_PBE+D3 + χSOC + χHSE
  - SOC: perturbative via spinorbit_eigenvalues() or non-collinear
  - Vibrational: Hessian (finite differences) + phonon dispersion (supercell)

Pipeline:
  structure → relax → scf → bands/dos → soc → hessian → phonons → validation → reports
"""

__version__ = "0.2.0"
__author__ = "DFT-CsPbI3 Contributors"

from .structure_builder import StructureBuilder
from .calculator_factory import GPAWCalculatorFactory
from .workflow_manager import DFTWorkflow
from .bandgap_correction import ScissorCorrection
from . import validation
from . import reporting

__all__ = [
    "StructureBuilder",
    "GPAWCalculatorFactory",
    "DFTWorkflow",
    "ScissorCorrection",
    "validation",
    "reporting",
]
