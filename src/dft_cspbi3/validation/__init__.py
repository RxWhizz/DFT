"""Scientific validación package para DFT-CsPbI3 pipeline."""

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
    # fonones
    "PhononResult",
    "compute_phonons",
    "frequencies_at_gamma",
    # estabilidad
    "StabilityClass",
    "StabilityReport",
    "classify_from_phonons",
    "classify_from_hessian",
    "classify_combined",
]
