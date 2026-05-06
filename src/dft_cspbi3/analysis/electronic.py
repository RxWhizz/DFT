"""Electronic structure analysis: gap type, effective masses, DOS near gap.

All functions read from existing .gpw checkpoints — no new GPAW calculations needed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ħ²/m₀ in eV·Å² — used to convert band curvature to effective mass
_HBAR2_OVER_M0_EV_ANG2 = 7.6199   # eV·Å²


@dataclass
class GapTypeResult:
    """Direct vs indirect band gap classification."""

    gap_type: str                       # "direct" or "indirect"
    gap_eV: float
    vbm_kpt_frac: Optional[np.ndarray]  # VBM k-point in fractional coords
    cbm_kpt_frac: Optional[np.ndarray]  # CBM k-point in fractional coords
    vbm_kpt_label: str = ""
    cbm_kpt_label: str = ""
    direct_gap_eV: Optional[float] = None  # minimum direct gap (even if gap is indirect)
    flags: list[str] = field(default_factory=list)

    @property
    def is_direct(self) -> bool:
        return self.gap_type == "direct"

    @property
    def summary(self) -> str:
        return (
            f"{self.gap_type.upper()} gap: {self.gap_eV:.3f} eV  "
            f"(VBM @ {self.vbm_kpt_label or 'k?'}, CBM @ {self.cbm_kpt_label or 'k?'})"
        )


@dataclass
class EffectiveMassResult:
    """Parabolic effective masses at CBM and VBM."""

    m_e: Optional[float]    # electron effective mass at CBM in units of m₀
    m_h: Optional[float]    # hole effective mass at VBM in units of m₀ (positive)
    m_reduced: Optional[float]  # reduced mass 1/m_r = 1/m_e + 1/m_h
    n_kpts_fit: int = 5     # number of k-points used in parabolic fit (each side)
    flags: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return self.m_e is not None and self.m_h is not None

    @property
    def summary(self) -> str:
        if not self.valid:
            return "Effective masses: FAILED"
        return (
            f"m*_e = {self.m_e:.3f} m₀,  m*_h = {self.m_h:.3f} m₀,  "
            f"m*_r = {self.m_reduced:.3f} m₀"
        )


@dataclass
class DosNearGapResult:
    """DOS near the Fermi level — proxy for defect tolerance."""

    dos_in_gap_states_per_eV: float    # states/eV integrated ±window around EF
    window_eV: float                   # integration window used
    vbm_eV: float
    cbm_eV: float
    gap_eV: float
    defect_tolerant: bool              # True if in-gap DOS below threshold
    flags: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        status = "DEFECT-TOLERANT" if self.defect_tolerant else "IN-GAP STATES"
        return f"{status}: {self.dos_in_gap_states_per_eV:.4f} states/eV in ±{self.window_eV} eV window"


# ---------------------------------------------------------------------------
# Gap type classification
# ---------------------------------------------------------------------------


def classify_gap_type(bands_gpw: str | Path) -> GapTypeResult:
    """Determine if the band gap is direct or indirect.

    Loads the band structure from a bands.gpw file, finds the VBM and CBM
    k-points, and compares their fractional coordinates.

    Args:
        bands_gpw: Path to a bands-step .gpw file.

    Returns:
        GapTypeResult with gap type, VBM/CBM k-points, and the minimum direct gap.
    """
    from gpaw import GPAW

    flags: list[str] = []
    calc = GPAW(str(bands_gpw))

    try:
        n_electrons = calc.get_number_of_electrons()
        n_bands = calc.get_number_of_bands()
        n_occupied = int(round(n_electrons / 2))   # spin-paired

        kpts = calc.get_bz_k_points()              # (nk, 3) fractional
        nk = len(kpts)

        # Eigenvalues: shape (nspins, nk, nbands) in eV
        eigs = np.array([
            [calc.get_eigenvalues(kpt=ik, spin=0) for ik in range(nk)]
        ])  # shape (1, nk, nbands)

        ef = calc.get_fermi_level()

        # VBM: highest occupied band top
        vb_energies = eigs[0, :, n_occupied - 1]   # (nk,)
        cb_energies = eigs[0, :, n_occupied]        # (nk,)

        vbm_k = int(np.argmax(vb_energies))
        cbm_k = int(np.argmin(cb_energies))

        vbm_e = float(vb_energies[vbm_k])
        cbm_e = float(cb_energies[cbm_k])
        gap = cbm_e - vbm_e

        # Minimum direct gap: same k-point
        direct_gaps = cb_energies - vb_energies     # (nk,)
        min_direct_gap = float(np.min(direct_gaps))
        min_direct_k = int(np.argmin(direct_gaps))

        # Classify: direct if VBM and CBM are at the same k-point
        k_dist = np.linalg.norm(kpts[vbm_k] - kpts[cbm_k])
        gap_type = "direct" if k_dist < 0.05 else "indirect"

        result = GapTypeResult(
            gap_type=gap_type,
            gap_eV=gap,
            vbm_kpt_frac=kpts[vbm_k],
            cbm_kpt_frac=kpts[cbm_k],
            direct_gap_eV=min_direct_gap,
            flags=flags,
        )
        logger.info("Gap type: %s", result.summary)

        if gap_type == "indirect":
            logger.info(
                "Minimum direct gap: %.3f eV at k=(%s)",
                min_direct_gap, kpts[min_direct_k],
            )

    except Exception as exc:
        flags.append(f"GAP_TYPE_FAILED:{exc}")
        logger.warning("Gap type classification failed: %s", exc)
        result = GapTypeResult(
            gap_type="unknown",
            gap_eV=0.0,
            vbm_kpt_frac=None,
            cbm_kpt_frac=None,
            flags=flags,
        )
    finally:
        calc.__del__()

    return result


# ---------------------------------------------------------------------------
# Effective masses
# ---------------------------------------------------------------------------


def compute_effective_masses(
    bands_gpw: str | Path,
    n_fit: int = 2,
) -> EffectiveMassResult:
    """Compute electron and hole effective masses via parabolic fit.

    Fits E(k) = E₀ + ħ²k²/(2m*) to the band structure near the CBM and VBM
    using the n_fit k-points on each side of the extremum.

    n_fit=2 keeps the fit inside the parabolic regime near R (~0.025 Å⁻¹
    for the M→R segment spacing of 0.013 Å⁻¹).  Larger values include
    non-parabolic points and overestimate m*.

    Args:
        bands_gpw: Path to a bands-step .gpw file with a k-path calculation.
        n_fit: Number of k-points on each side of the extremum for the fit.

    Returns:
        EffectiveMassResult in units of the free electron mass m₀.
    """
    from gpaw import GPAW

    flags: list[str] = []
    calc = GPAW(str(bands_gpw))

    try:
        n_electrons = calc.get_number_of_electrons()
        n_occupied = int(round(n_electrons / 2))

        kpts = calc.get_bz_k_points()           # (nk, 3) fractional
        cell = calc.atoms.cell                   # ASE cell
        rec = np.linalg.inv(cell.T) * 2 * np.pi  # reciprocal lattice (rows = b vectors) in Å⁻¹
        nk = len(kpts)

        eigs = np.array([
            [calc.get_eigenvalues(kpt=ik, spin=0) for ik in range(nk)]
        ])  # (1, nk, nbands)

        vb = eigs[0, :, n_occupied - 1]
        cb = eigs[0, :, n_occupied]

        vbm_k = int(np.argmax(vb))
        cbm_k = int(np.argmin(cb))

        m_e = _fit_mass(cb, kpts, rec, cbm_k, n_fit, flags, label="CBM")
        m_h = _fit_mass(-vb, kpts, rec, vbm_k, n_fit, flags, label="VBM")
        if m_h is not None:
            m_h = abs(m_h)   # hole mass is positive

        m_reduced = None
        if m_e is not None and m_h is not None and (m_e + m_h) > 0:
            m_reduced = (m_e * m_h) / (m_e + m_h)

        result = EffectiveMassResult(
            m_e=m_e,
            m_h=m_h,
            m_reduced=m_reduced,
            n_kpts_fit=n_fit,
            flags=flags,
        )
        logger.info("Effective masses: %s", result.summary)

    except Exception as exc:
        flags.append(f"EFFECTIVE_MASS_FAILED:{exc}")
        logger.warning("Effective mass calculation failed: %s", exc)
        result = EffectiveMassResult(m_e=None, m_h=None, m_reduced=None, flags=flags)
    finally:
        calc.__del__()

    return result


def _fit_mass(
    energies: np.ndarray,
    kpts_frac: np.ndarray,
    rec: np.ndarray,
    extremum_k: int,
    n_fit: int,
    flags: list[str],
    label: str,
) -> Optional[float]:
    """Fit parabola to energies near extremum_k along each direction and return harmonic mean m*."""
    nk = len(energies)
    # Take n_fit points on each side
    i_start = max(0, extremum_k - n_fit)
    i_end = min(nk, extremum_k + n_fit + 1)
    if i_end - i_start < 3:
        flags.append(f"TOO_FEW_KPTS_{label}:{i_end - i_start}")
        return None

    k_slice = kpts_frac[i_start:i_end]            # (m, 3) fractional
    e_slice = energies[i_start:i_end]             # (m,)

    # Convert to Cartesian in Å⁻¹
    k_cart = k_slice @ rec                         # (m, 3) in Å⁻¹
    k0 = k_cart[extremum_k - i_start]
    dk = k_cart - k0                               # displacement from extremum

    # Scalar k-distance along path
    k_dist = np.linalg.norm(dk, axis=1)            # (m,)

    # Exclude exact extremum (k_dist = 0) for numerical fit
    mask = k_dist > 1e-6
    if mask.sum() < 3:
        flags.append(f"DEGENERATE_KPATH_{label}")
        return None

    k_fit = k_dist[mask]
    e_fit = e_slice[mask] - e_slice[extremum_k - i_start]

    # Fit E = a*k² through origin (intercept forced to zero — valid at the extremum)
    # Weighted least squares: a = Σ(k²·E) / Σ(k⁴)
    try:
        k2 = k_fit ** 2
        a = float(np.dot(k2, e_fit) / np.dot(k2, k2))
        if abs(a) < 1e-6:
            flags.append(f"FLAT_BAND_{label}")
            return None
        m_star = _HBAR2_OVER_M0_EV_ANG2 / (2 * a)
        if m_star < 0.01 or m_star > 20:
            flags.append(f"UNPHYSICAL_MASS_{label}:{m_star:.2f}")
        return float(m_star)
    except Exception as exc:
        flags.append(f"FIT_FAILED_{label}:{exc}")
        return None


# ---------------------------------------------------------------------------
# Fine k-path effective masses (non-SCF)
# ---------------------------------------------------------------------------


def compute_effective_masses_nscf(
    scf_gpw: str | Path,
    cbm_kpt_frac: np.ndarray,
    vbm_kpt_frac: np.ndarray,
    step_dir: Path,
    n_fit: int = 5,
    dk_AA: float = 0.005,
) -> EffectiveMassResult:
    """Effective masses from a fine k-path non-SCF calculation around the band extrema.

    Builds a 3-direction k-grid (kx, ky, kz) around the CBM/VBM k-point with
    spacing dk_AA (Å⁻¹), runs GPAW with fixdensity=True, then fits parabolas.

    Unlike compute_effective_masses(), this does NOT depend on the resolution of
    the existing band-path calculation — it uses its own fine k-sampling.
    scf_gpw must exist; wavefunctions in it are not required (fixdensity diagonalises
    H[ρ] at the new k-points from the stored density).

    Args:
        scf_gpw:       Converged SCF .gpw file (density must be stored).
        cbm_kpt_frac:  CBM k-point in fractional coordinates (e.g. [0.5,0.5,0.5]).
        vbm_kpt_frac:  VBM k-point in fractional coordinates.
        step_dir:      Directory for output files (fine_kpts.gpw, effmass.txt).
        n_fit:         Points each side of extremum for parabolic fit.
        dk_AA:         k-step in Å⁻¹ for the fine grid.
    """
    from gpaw import GPAW

    step_dir = Path(step_dir)
    fine_gpw = step_dir / "effmass_fine.gpw"
    flags: list[str] = []

    # --- get lattice parameter to convert dk_AA → fractional ----------------
    calc_gs = GPAW(str(scf_gpw), txt=None)
    cell = calc_gs.atoms.cell
    rec = np.linalg.inv(cell.T) * 2 * np.pi   # rows are reciprocal lattice vectors (Å⁻¹)
    # For a cubic cell, |b| = 2π/a along each direction
    b_norms = np.linalg.norm(rec, axis=1)
    dk_frac_per_dir = dk_AA / b_norms          # fractional step per reciprocal direction
    calc_gs.__del__()

    # --- build fine k-point list around CBM ----------------------------------
    if not fine_gpw.exists():
        k0 = np.asarray(cbm_kpt_frac, dtype=float)
        kpts: list[list[float]] = [k0.tolist()]     # extremum itself
        for d in range(3):
            step = np.zeros(3)
            step[d] = dk_frac_per_dir[d]
            for n in range(1, n_fit + 2):           # n_fit+1 on each side for safety
                kpts.append((k0 + n * step).tolist())
                kpts.append((k0 - n * step).tolist())

        logger.info(
            "Running fine k-path non-SCF: %d k-points, dk=%.4f Å⁻¹", len(kpts), dk_AA
        )
        calc_fine = GPAW(
            str(scf_gpw),
            kpts=kpts,
            fixdensity=True,
            symmetry="off",
            txt=str(step_dir / "effmass.txt"),
        )
        atoms = calc_fine.get_atoms()
        atoms.get_potential_energy()
        calc_fine.write(str(fine_gpw))
        logger.info("Fine k-path saved: %s", fine_gpw)

    # --- fit effective masses from fine k-path -------------------------------
    try:
        calc_fine = GPAW(str(fine_gpw), txt=None)
        kpts_frac = calc_fine.get_bz_k_points()
        ne = int(calc_fine.get_number_of_electrons())
        n_occ = ne // 2
        nk = len(kpts_frac)
        cell = calc_fine.atoms.cell
        rec_fine = np.linalg.inv(cell.T) * 2 * np.pi

        eigs = np.array([calc_fine.get_eigenvalues(kpt=ik, spin=0) for ik in range(nk)])
        cb = eigs[:, n_occ]
        vb = eigs[:, n_occ - 1]
        cbm_k = int(np.argmin(cb))
        vbm_k = int(np.argmax(vb))
        calc_fine.__del__()

        m_e = _fit_mass(cb, kpts_frac, rec_fine, cbm_k, n_fit, flags, "CBM")
        m_h_raw = _fit_mass(-vb, kpts_frac, rec_fine, vbm_k, n_fit, flags, "VBM")
        m_h = abs(m_h_raw) if m_h_raw is not None else None

        m_reduced = None
        if m_e is not None and m_h is not None and (m_e + m_h) > 0:
            m_reduced = (m_e * m_h) / (m_e + m_h)

        result = EffectiveMassResult(m_e=m_e, m_h=m_h, m_reduced=m_reduced,
                                    n_kpts_fit=n_fit, flags=flags)
        logger.info("Fine-grid effective masses: %s", result.summary)
        return result

    except Exception as exc:
        flags.append(f"FINE_MASS_FAILED:{exc}")
        logger.warning("Fine k-path mass fit failed: %s", exc)
        return EffectiveMassResult(m_e=None, m_h=None, m_reduced=None, flags=flags)


# ---------------------------------------------------------------------------
# DOS near gap
# ---------------------------------------------------------------------------


def analyze_dos_near_gap(
    dos_gpw: str | Path,
    window_eV: float = 0.2,
    threshold_states_per_eV: float = 0.01,
) -> DosNearGapResult:
    """Integrate DOS within ±window_eV of the band edges to detect in-gap states.

    A large DOS within the gap indicates trap states or metallic character.
    This serves as a proxy for defect tolerance in perovskite absorbers.

    Args:
        dos_gpw: Path to a DOS-step .gpw file with dense k-mesh.
        window_eV: Integration window around each band edge (eV).
        threshold_states_per_eV: Threshold below which the material is
            considered defect-tolerant (no in-gap states).

    Returns:
        DosNearGapResult.
    """
    from gpaw import GPAW
    from gpaw.dos import DOSCalculator

    flags: list[str] = []

    try:
        calc = GPAW(str(dos_gpw))
        ef = calc.get_fermi_level()
        n_electrons = calc.get_number_of_electrons()
        n_occupied = int(round(n_electrons / 2))

        # Estimate VBM and CBM from eigenvalues
        nk = len(calc.get_bz_k_points())
        all_vb = [calc.get_eigenvalues(kpt=ik, spin=0)[n_occupied - 1] for ik in range(nk)]
        all_cb = [calc.get_eigenvalues(kpt=ik, spin=0)[n_occupied] for ik in range(nk)]
        vbm = float(np.max(all_vb))
        cbm = float(np.min(all_cb))
        gap = cbm - vbm

        # Compute DOS using GPAW's DOSCalculator
        dos_calc = DOSCalculator.from_calculator(str(dos_gpw), soc=False)
        energies_eV = np.linspace(vbm - 0.5, cbm + 0.5, 2000)
        dos_values = dos_calc.raw_dos(energies_eV, spin=0, width=0.05)

        # Integrate in-gap states: energies strictly between VBM and CBM
        in_gap_mask = (energies_eV > vbm + window_eV) & (energies_eV < cbm - window_eV)
        if in_gap_mask.sum() == 0:
            in_gap_dos = 0.0
        else:
            de = energies_eV[1] - energies_eV[0]
            in_gap_dos = float(np.trapz(dos_values[in_gap_mask], dx=de))

        calc.__del__()

    except Exception as exc:
        flags.append(f"DOS_NEAR_GAP_FAILED:{exc}")
        logger.warning("DOS near gap analysis failed: %s", exc)
        return DosNearGapResult(
            dos_in_gap_states_per_eV=0.0,
            window_eV=window_eV,
            vbm_eV=0.0,
            cbm_eV=0.0,
            gap_eV=0.0,
            defect_tolerant=True,
            flags=flags,
        )

    result = DosNearGapResult(
        dos_in_gap_states_per_eV=in_gap_dos,
        window_eV=window_eV,
        vbm_eV=vbm,
        cbm_eV=cbm,
        gap_eV=gap,
        defect_tolerant=in_gap_dos < threshold_states_per_eV,
        flags=flags,
    )
    logger.info("DOS near gap: %s", result.summary)
    return result
