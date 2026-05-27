"""Build pymatgen/ASE structures for ABX3 halide perovskites.

Priority order per material:
  1. Load from existing GPW file (full geometry, including organic cation atoms)
  2. Inorganic A-site: construct cubic Pm-3m ABX3 (5-atom cell) from empirical lattice param
  3. Organic A-site with no GPW: pseudo-atom substitution (MA→Rb, FA→Cs, same +1 charge)

Pseudo-atom rationale: MA (r=2.17Å) and FA (r=2.53Å) are polyatomic cations that
GNNs trained on single-element site occupancies cannot represent directly. Replacing
with the closest monovalent cation by Shannon radius (MA→Rb 1.72Å, FA→Cs 1.88Å)
preserves the crystal connectivity and charge balance at the cost of a ~20% error
in A-site radius. GNNResult.structure_source = "pseudoatom" flags these cases.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)

# Shannon 1976 ionic radii (Å) + Kieslich 2014 for MA/FA pseudo-radii
_R_A: dict[str, float] = {"Cs": 1.88, "Rb": 1.72, "K": 1.38, "MA": 2.17, "FA": 2.53}
_R_B: dict[str, float] = {"Pb": 1.19, "Sn": 1.18, "Ge": 0.73, "Bi": 1.03, "In": 0.80}
_R_X: dict[str, float] = {"I": 2.20, "Br": 1.96, "Cl": 1.81}

# Organic A-site → closest inorganic proxy (monovalent, by Shannon radius)
_ORGANIC_PROXY: dict[str, str] = {"MA": "Rb", "FA": "Cs"}

_DFT_ROOT = Path(__file__).resolve().parents[2] / "calculations" / "top8_r2scan"

_TOP8_GPW_CANDIDATES = [
    "01_relax_sym/relax_sym.gpw",
    "01_relax/relax.gpw",
    "06_r2scan/r2scan.gpw",
    "06_r2scan/u_scan/u_scan_U2p50.gpw",
]


class PerovskiteStructureBuilder:
    """Build pymatgen Structure objects from ABX3 composition or existing DFT files.

    Parameters
    ----------
    dft_root : Path | None
        Root with per-material subdirectories (default: calculations/top8_r2scan/).
    """

    def __init__(self, dft_root: Optional[Path] = None) -> None:
        self._root = Path(dft_root) if dft_root else _DFT_ROOT

    def build(
        self, A: str, B: str, X: str, mat: Optional[str] = None
    ) -> tuple[object, str]:
        """Return (pymatgen.core.Structure, source_label).

        source_label: "gpw" | "cubic" | "pseudoatom"
        """
        mat_name = mat or f"{A}{B}{X}3"

        struct, source = self._from_gpw(mat_name)
        if struct is not None:
            return struct, source

        if A not in _ORGANIC_PROXY:
            return self._cubic_inorganic(A, B, X), "cubic"

        proxy = _ORGANIC_PROXY[A]
        log.warning(
            "%s: organic A-site %s → pseudo-atom %s (r %.2f→%.2f Å). "
            "GNN predictions are ranking signals only.",
            mat_name, A, proxy, _R_A[A], _R_A[proxy],
        )
        return self._cubic_inorganic(proxy, B, X), "pseudoatom"

    def build_from_name(self, mat: str) -> tuple[object, str]:
        """Convenience wrapper: resolve (A,B,X) from standard material name."""
        from ml_surrogate.inference import TOP8_MATS
        cfg = TOP8_MATS.get(mat)
        if cfg is None:
            raise ValueError(f"Unknown material '{mat}'.")
        return self.build(cfg["A"], cfg["B"], cfg["X"], mat=mat)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _from_gpw(self, mat_name: str) -> tuple[object | None, str]:
        try:
            from ase.io import read
            from pymatgen.io.ase import AseAtomsAdaptor
        except ImportError:
            return None, ""

        mat_dir = self._root / mat_name
        for rel in _TOP8_GPW_CANDIDATES:
            gpw = mat_dir / rel
            if gpw.exists():
                try:
                    atoms = read(str(gpw))
                    struct = AseAtomsAdaptor.get_structure(atoms)
                    log.debug("Loaded %s from %s (%d sites)", mat_name, gpw.name, struct.num_sites)
                    return struct, "gpw"
                except Exception as exc:
                    log.debug("Could not read %s: %s", gpw, exc)
        return None, ""

    def _cubic_inorganic(self, A: str, B: str, X: str) -> object:
        """Construct cubic Pm-3m ABX3 (5-atom) unit cell."""
        from pymatgen.core import Structure, Lattice

        r_A = _R_A.get(A, 1.6)
        r_B = _R_B.get(B, 1.2)
        r_X = _R_X.get(X, 2.0)
        a0 = float(2.0 * np.sqrt(2.0) * (r_B + r_X) * 0.97)

        return Structure(
            Lattice.cubic(a0),
            [A, B, X, X, X],
            [
                [0.5, 0.5, 0.5],  # A (body center)
                [0.0, 0.0, 0.0],  # B (corner)
                [0.5, 0.0, 0.0],  # X face centers
                [0.0, 0.5, 0.0],
                [0.0, 0.0, 0.5],
            ],
        )
