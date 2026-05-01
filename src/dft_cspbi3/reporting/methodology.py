"""Generate methodology.md — scientific methodology document.

Describes the theoretical framework and computational choices used in this
pipeline, translated from the thesis methodology. Serves as the reproducibility
record for a publication supplement.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional


def generate_methodology(
    params: Optional[dict] = None,
    output_dir: str | Path = "./reports",
    filename: str = "methodology.md",
) -> Path:
    """Write methodology.md and return its path.

    Args:
        params: Optional dict of calculation parameters to embed in the text.
                Keys used: xc, ecut_eV, kpts, soc_mode, phase.
        output_dir: Output directory.
        filename: Report filename.

    Returns:
        Path to the generated file.
    """
    params = params or {}
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / filename

    xc = params.get("xc", "PBEsol")
    ecut = params.get("ecut_eV", 450)
    kpts = params.get("kpts", [6, 6, 6])
    kstr = f"{kpts[0]}×{kpts[1]}×{kpts[2]}"
    soc_mode = params.get("soc_mode", "perturbative (spinorbit_eigenvalues)")
    phase = params.get("phase", "CsPbI₃")

    content = f"""\
# Computational Methodology

*{phase} — DFT pipeline based on GPAW/ASE*
*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*

---

## 1. Theoretical Framework

### 1.1 Kohn-Sham Density Functional Theory

All electronic structure calculations are performed within the Kohn-Sham (KS)
formulation of DFT [Hohenberg & Kohn, 1964; Kohn & Sham, 1965]. The total
electronic energy is minimised with respect to the charge density ρ(r):

    E[ρ] = Ts[ρ] + ∫ v_ext(r)ρ(r)dr + E_H[ρ] + E_xc[ρ]

where Ts is the non-interacting kinetic energy, E_H the Hartree energy, and
E_xc the exchange-correlation energy. The self-consistent KS equations

    (-½∇² + v_eff(r)) ψᵢ(r) = εᵢ ψᵢ(r)

are solved iteratively until the charge density and total energy converge
below the specified threshold.

### 1.2 Born-Oppenheimer Approximation

The nuclear degrees of freedom are treated classically within the
Born-Oppenheimer (BO) approximation. The electronic problem is solved for
each fixed nuclear configuration, yielding the BO energy surface E(R) on
which the nuclei move. Geometry optimisation minimises |∇_R E(R)|, and
vibrational properties (Hessian, phonons) are computed as second derivatives
of E(R).

---

## 2. Exchange-Correlation Functional

**Functional**: {xc}

The {xc} functional is used for all structural relaxation and self-consistent
field (SCF) calculations. {_xc_note(xc)}

**Known limitations**:
- PBE/PBEsol systematically *underestimates* the band gap (by ~0.3–0.8 eV for
  halide perovskites). This is a known self-interaction error.
- Spin-orbit coupling from Pb 6p states further reduces the KS gap by ~0.84 eV.
- A scissor correction (Eg_corr = E_PBE + χSOC + χHSE) is applied to recover
  a physically meaningful gap.

---

## 3. Projector-Augmented Wave (PAW) Method

All electron densities are represented using the PAW method [Blöchl, 1994]
as implemented in GPAW. The PAW datasets used are:

| Element | Dataset        | Valence electrons |
|---------|----------------|-------------------|
| Cs      | Cs.9.PBE       | 9 (5s²5p⁶6s¹)    |
| Pb      | Pb.14.PBE      | 14 (5d¹⁰6s²6p²)  |
| I       | I.7.PBE        | 7 (5s²5p⁵)        |

The Pb.14.PBE dataset includes the semicore 5d electrons, which is essential
for accurate SOC treatment (5d hybridisation with 6p states).

---

## 4. Plane-Wave Basis and Cutoff

**Mode**: PW (plane-wave expansion)
**Cutoff energy**: Ecut = {ecut} eV

The KS wavefunctions are expanded in plane waves:

    ψᵢₖ(r) = Σ_G cᵢₖ(G) exp(i(k+G)·r)

where G runs over reciprocal lattice vectors with |k+G|² < 2Ecut (in Hartree
units). The cutoff was determined from convergence tests (see validation_report.md),
ensuring total energy differences < 1 meV/atom across the tested range.

---

## 5. k-point Sampling

**Mesh**: {kstr} Monkhorst-Pack grid (Γ-centred)

The Brillouin zone is sampled using a uniform Monkhorst-Pack mesh. The Γ-centred
grid is required for systems with time-reversal symmetry. A denser mesh
({kstr} → 12×12×12) is used for DOS calculations to resolve fine features.

Electronic occupations use a Fermi-Dirac smearing of 0.05 eV (≈ 580 K),
which is small compared to the band gap and ensures smooth SCF convergence
without introducing finite-temperature errors in ground-state properties.

---

## 6. Geometry Optimisation

Atomic positions are relaxed using the BFGS algorithm (Broyden-Fletcher-
Goldfarb-Shanno) as implemented in ASE. The relaxation is terminated when:

    max |F_i| < {params.get('fmax', 0.01)} eV/Å

The cell parameters are held fixed at experimental/reference values during
the relaxation (constant-cell relaxation). A self-consistent Mixer with
β = 0.05 is used to stabilise convergence in systems with heavy atoms.

---

## 7. Spin-Orbit Coupling (SOC)

**Mode**: {soc_mode}

SOC is included perturbatively using the `spinorbit_eigenvalues()` function
in GPAW. This applies the relativistic correction:

    H_SOC = (ħ/4m²c²) σ · (∇V × p)

as a first-order perturbation to the collinear KS eigenstates. The approach
is accurate when SOC is not too strong relative to the crystal-field splitting
(valid for Pb 6p states in halide perovskites to within ~0.05 eV).

The perturbative SOC correction χSOC = Eg(SOC) − Eg(PBE) is evaluated and
stored separately so it can be combined with hybrid functional corrections.

---

## 8. Band Gap Correction (Scissor Operator)

Because PBE systematically underestimates the gap and SOC further reduces it,
a two-component scissor correction is applied:

    Eg_corrected = Eg(PBE+D3) + χSOC + χHSE

where:
- χSOC = Eg(PBE+SOC) − Eg(PBE)   [typically −0.84 eV for CsPbI₃]
- χHSE = Eg(HSE06) − Eg(PBE)      [typically +0.32 eV for CsPbI₃]

This avoids the O(N³) cost of a full HSE06+SOC self-consistent calculation
while recovering band gaps within ~0.1–0.2 eV of experiment.

---

## 9. Vibrational Properties

### 9.1 Hessian Matrix

The Hessian H is computed via central finite differences on the forces:

    H_{{ij}} ≈ -(F_i(R + Δê_j) - F_i(R - Δê_j)) / (2Δ)

with Δ = 0.01 Å. Symmetrisation (H → (H + Hᵀ)/2) removes finite-difference
asymmetry. Eigenvalues ≥ 0 indicate a stable energy minimum.

### 9.2 Phonon Dispersion

Phonon frequencies are computed via the finite-displacement supercell method.
Force constants C(R) are obtained from displaced supercell GPAW calculations,
Fourier-transformed to the dynamical matrix D(q), and diagonalised:

    ω²(q) = eigenvalues of D(q) = eigenvalues of [C(q) / √(MᵢMⱼ)]

The acoustic sum rule is enforced to remove translational drift. Imaginary
frequencies (ω² < 0) identify dynamic instabilities.

---

## 10. Software Stack

| Component | Version |
|-----------|---------|
| GPAW      | ≥ 24.1.0 |
| ASE       | ≥ 3.23.0 |
| NumPy     | ≥ 1.26   |
| Python    | ≥ 3.11   |

All calculations are reproducible from the provided `configs/default_params.yaml`
and the source structures in `structures/`.
"""

    # Do not overwrite if the file already has expanded results sections
    # (Section 9.3+ contain actual phonon data that the template cannot regenerate).
    if out_path.exists():
        existing = out_path.read_text(encoding="utf-8")
        if "### 9.3 Phonon Dispersion" in existing or "Results and Discussion" in existing:
            return out_path

    out_path.write_text(content, encoding="utf-8")
    return out_path


def _xc_note(xc: str) -> str:
    notes = {
        "PBEsol": (
            "PBEsol is a revised PBE functional optimised for crystalline solids "
            "(Perdew et al., 2008). It improves lattice constants and cohesive energies "
            "relative to PBE, at the cost of slightly reduced molecular atomisation energies."
        ),
        "PBE": (
            "PBE (Perdew-Burke-Ernzerhof, 1996) is the most widely used GGA functional. "
            "It is known to overestimate lattice constants by ~1–2% for solids."
        ),
        "HSE06": (
            "HSE06 is a range-separated hybrid functional that mixes 25% Hartree-Fock "
            "exact exchange at short range (ω = 0.11 Bohr⁻¹). It significantly improves "
            "band gap accuracy over GGA at ~10–50× higher computational cost."
        ),
    }
    return notes.get(xc, "")
