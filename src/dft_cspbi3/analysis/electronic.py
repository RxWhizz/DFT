"""Electronic estructura analysis."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ħ²/m₀ en eV·Å² - usado convert banda curvature effective mass
_HBAR2_OVER_M0_EV_ANG2 = 7.6199   # eV·Å²


@dataclass
class GapTypeResult:
    """Direct vs indirect banda gap classification."""

    gap_type: str
    gap_eV: float
    vbm_kpt_frac: Optional[np.ndarray]
    cbm_kpt_frac: Optional[np.ndarray]
    vbm_kpt_label: str = ""
    cbm_kpt_label: str = ""
    direct_gap_eV: Optional[float] = None
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
    """Parabolic effective masses en CBM y VBM."""

    m_e: Optional[float]    # electron effective mass en CBM en units m₀
    m_h: Optional[float]    # hole effective mass en VBM en units m₀ (positive)
    m_reduced: Optional[float]  # reduced mass 1/m_r = 1/m_e + 1/m_h
    n_kpts_fit: int = 5
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
    """DOS cerca EF = proxy defectos."""
    dos_in_gap_states_per_eV: float    # states/eV integrated ±window cerca EF
    window_eV: float
    vbm_eV: float
    cbm_eV: float
    gap_eV: float
    defect_tolerant: bool              # True si en-gap DOS bajo umbral
    flags: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        status = "DEFECT-TOLERANT" if self.defect_tolerant else "IN-GAP STATES"
        return f"{status}: {self.dos_in_gap_states_per_eV:.4f} states/eV in ±{self.window_eV} eV window"


# Gap type classification


def classify_gap_type(bands_gpw: str | Path) -> GapTypeResult:
    """Determina gap directo/indirecto."""
    from gpaw import GPAW

    flags: list[str] = []
    calc = GPAW(str(bands_gpw))

    try:
        n_electrons = calc.get_number_of_electrons()
        n_bands = calc.get_number_of_bands()
        n_occupied = int(round(n_electrons / 2))

        kpts = calc.get_bz_k_points()              # (nk, 3) fractional
        nk = len(kpts)

        # Eigenvalues
        eigs = np.array([
            [calc.get_eigenvalues(kpt=ik, spin=0) for ik in range(nk)]
        ])  # shape (1, nk, nbands)

        ef = calc.get_fermi_level()

        # VBM
        vb_energies = eigs[0, :, n_occupied - 1]
        cb_energies = eigs[0, :, n_occupied]

        vbm_k = int(np.argmax(vb_energies))
        cbm_k = int(np.argmin(cb_energies))

        vbm_e = float(vb_energies[vbm_k])
        cbm_e = float(cb_energies[cbm_k])
        gap = cbm_e - vbm_e

        # Minimum direct gap
        direct_gaps = cb_energies - vb_energies
        min_direct_gap = float(np.min(direct_gaps))
        min_direct_k = int(np.argmin(direct_gaps))

        # Clasifica
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


# Effective masses


def compute_effective_masses(
    bands_gpw: str | Path,
    n_fit: int = 2,
) -> EffectiveMassResult:
    """Calcula electron y hole effective masses via parabolic fit."""
    from gpaw import GPAW

    flags: list[str] = []
    calc = GPAW(str(bands_gpw))

    try:
        n_electrons = calc.get_number_of_electrons()
        n_occupied = int(round(n_electrons / 2))

        kpts = calc.get_bz_k_points()           # (nk, 3) fractional
        cell = calc.atoms.cell
        rec = np.linalg.inv(cell.T) * 2 * np.pi  # reciprocal lattice (filas = b vectors) en Å⁻¹
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
            m_h = abs(m_h)

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
    """Fit parabola energies cerca extremum_k along each direction y devuelve harmonic mean m*."""
    nk = len(energies)
    # Take n_fit points en each lado
    i_start = max(0, extremum_k - n_fit)
    i_end = min(nk, extremum_k + n_fit + 1)
    if i_end - i_start < 3:
        flags.append(f"TOO_FEW_KPTS_{label}:{i_end - i_start}")
        return None

    k_slice = kpts_frac[i_start:i_end]            # (m, 3) fractional
    e_slice = energies[i_start:i_end]

    # Convert Cartesian en Å⁻¹
    k_cart = k_slice @ rec                         # (m, 3) en Å⁻¹
    k0 = k_cart[extremum_k - i_start]
    dk = k_cart - k0

    # Scalar k-distance along ruta
    k_dist = np.linalg.norm(dk, axis=1)

    # Exclude exact extremum (k_dist = 0) para numerical fit
    mask = k_dist > 1e-6
    if mask.sum() < 3:
        flags.append(f"DEGENERATE_KPATH_{label}")
        return None

    k_fit = k_dist[mask]
    e_fit = e_slice[mask] - e_slice[extremum_k - i_start]

    # Fit E = *k² through origin (intercept forced zero - valid en extremum)
    # Weighted least squares
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


# Fine k-ruta effective masses (non-SCF)


def compute_effective_masses_nscf(
    scf_gpw: str | Path,
    cbm_kpt_frac: np.ndarray,
    vbm_kpt_frac: np.ndarray,
    step_dir: Path,
    n_fit: int = 5,
    dk_AA: float = 0.005,
) -> EffectiveMassResult:
    """Masas efectivas desde ruta k fina."""
    from gpaw import GPAW

    step_dir = Path(step_dir)
    fine_gpw = step_dir / "effmass_fine.gpw"
    flags: list[str] = []

    # get lattice parámetro convert dk_AA → fractional
    calc_gs = GPAW(str(scf_gpw), txt=None)
    cell = calc_gs.atoms.cell
    rec = np.linalg.inv(cell.T) * 2 * np.pi   # filas reciprocal lattice vectors (Å⁻¹)
    # For cubic celda, |b| = 2π/ along each direction
    b_norms = np.linalg.norm(rec, axis=1)
    dk_frac_per_dir = dk_AA / b_norms
    calc_gs.__del__()

    # construye fine k-point list cerca CBM
    if not fine_gpw.exists():
        k0 = np.asarray(cbm_kpt_frac, dtype=float)
        kpts: list[list[float]] = [k0.tolist()]
        for d in range(3):
            step = np.zeros(3)
            step[d] = dk_frac_per_dir[d]
            for n in range(1, n_fit + 2):           # n_fit+1 por lado
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

    # fit effective masses desde fine k-ruta
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


# SOC-corrected effective masses desde fine k-ruta


def compute_effective_masses_soc(
    fine_gpw: str | Path,
    n_fit: int = 5,
    theta: float = 0.0,
    phi: float = 0.0,
) -> EffectiveMassResult:
    """Effective masses desde perturbative SOC applied fine k-ruta.gpw."""
    from gpaw import GPAW
    from gpaw.spinorbit import soc_eigenstates

    flags: list[str] = []
    try:
        calc = GPAW(str(fine_gpw), txt=None)
        nb = calc.get_number_of_bands()
        ne = int(calc.get_number_of_electrons())  # 44 para CsPbI₃ - NOT ne//2
        kpts_frac = calc.get_bz_k_points()
        cell = calc.atoms.cell
        rec = np.linalg.inv(cell.T) * 2 * np.pi

        soc_result = soc_eigenstates(calc, n2=nb, theta=theta, phi=phi)
        eigs = soc_result.eigenvalues()   # shape (nk, 2*nb)
        calc.__del__()

        # After SOC doubling
        cb = eigs[:, ne]
        vb = eigs[:, ne - 1]

        cbm_k = int(np.argmin(cb))
        vbm_k = int(np.argmax(vb))

        m_e = _fit_mass(cb, kpts_frac, rec, cbm_k, n_fit, flags, "CBM_SOC")
        m_h_raw = _fit_mass(-vb, kpts_frac, rec, vbm_k, n_fit, flags, "VBM_SOC")
        m_h = abs(m_h_raw) if m_h_raw is not None else None

        m_reduced = None
        if m_e is not None and m_h is not None and (m_e + m_h) > 0:
            m_reduced = (m_e * m_h) / (m_e + m_h)

        result = EffectiveMassResult(m_e=m_e, m_h=m_h, m_reduced=m_reduced,
                                     n_kpts_fit=n_fit, flags=flags)
        logger.info("SOC effective masses: %s", result.summary)
        return result

    except Exception as exc:
        flags.append(f"SOC_MASS_FAILED:{exc}")
        logger.warning("SOC effective mass calculation failed: %s", exc)
        return EffectiveMassResult(m_e=None, m_h=None, m_reduced=None, flags=flags)


# DOS cerca gap


def analyze_dos_near_gap(
    dos_gpw: str | Path,
    window_eV: float = 0.2,
    threshold_states_per_eV: float = 0.01,
) -> DosNearGapResult:
    """Integra DOS cerca bordes de banda."""
    from gpaw import GPAW
    from gpaw.dos import DOSCalculator

    flags: list[str] = []

    try:
        calc = GPAW(str(dos_gpw))
        ef = calc.get_fermi_level()
        n_electrons = calc.get_number_of_electrons()
        n_occupied = int(round(n_electrons / 2))

        # Estimate VBM y CBM desde eigenvalues
        nk = len(calc.get_bz_k_points())
        all_vb = [calc.get_eigenvalues(kpt=ik, spin=0)[n_occupied - 1] for ik in range(nk)]
        all_cb = [calc.get_eigenvalues(kpt=ik, spin=0)[n_occupied] for ik in range(nk)]
        vbm = float(np.max(all_vb))
        cbm = float(np.min(all_cb))
        gap = cbm - vbm

        # Calcula DOS usa GPAW's DOSCalculator
        dos_calc = DOSCalculator.from_calculator(str(dos_gpw), soc=False)
        energies_eV = np.linspace(vbm - 0.5, cbm + 0.5, 2000)
        dos_values = dos_calc.raw_dos(energies_eV, spin=0, width=0.05)

        # Integrate en-gap states
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
