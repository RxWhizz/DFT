"""Scientific validation package for the DFT-CsPbI3 pipeline.

Modules
-------
scf         — Parse GPAW text output; check SCF convergence and physical consistency.
soc         — Validate perturbative SOC application via spinorbit_eigenvalues().
hessian     — Compute 3N×3N Hessian via central finite differences; classify stability.
phonons     — Supercell phonon calculation with ASE+GPAW; detect imaginary modes.
stability   — Classify structures as STABLE / METASTABLE / UNSTABLE.

All validation functions return typed dataclasses so results can be inspected
programmatically and serialised to the reporting package.
"""

from .scf import (
    SCFReport,
    PhysicalChecks,
    validate_scf,
    validate_physical_checks,
    classify_electronic_structure,
)
from .soc import (
    SOCReport,
    validate_soc,
    soc_was_applied,
)
from .hessian import (
    HessianResult,
    compute_hessian,
    check_forces,
    load_hessian_from_cache,
)
from .phonons import (
    PhononResult,
    compute_phonons,
    frequencies_at_gamma,
)
from .stability import (
    StabilityClass,
    StabilityReport,
    classify_from_phonons,
    classify_from_hessian,
    classify_combined,
)

__all__ = [
    # scf
    "SCFReport",
    "PhysicalChecks",
    "validate_scf",
    "validate_physical_checks",
    "classify_electronic_structure",
    # soc
    "SOCReport",
    "validate_soc",
    "soc_was_applied",
    # hessian
    "HessianResult",
    "compute_hessian",
    "check_forces",
    "load_hessian_from_cache",
    # phonons
    "PhononResult",
    "compute_phonons",
    "frequencies_at_gamma",
    # stability
    "StabilityClass",
    "StabilityReport",
    "classify_from_phonons",
    "classify_from_hessian",
    "classify_combined",
]
