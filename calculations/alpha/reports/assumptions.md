# Scientific Assumptions and Validity Range

*alpha-CsPbI₃ — DFT pipeline*
*Generated: 2026-04-29 17:16:08*

---

## 1. Structural Assumptions

| Assumption | Justification | Limitation |
|------------|---------------|------------|
| Perfect periodicity | Enables Bloch's theorem and plane-wave basis | Ignores defects, vacancies, grain boundaries |
| Fixed composition | Integer stoichiometry CsPbI₃ | No off-stoichiometry, no doping |
| Static lattice (0 K) | BO approximation; nuclei at potential minimum | No thermal expansion; compare with low-T experiments |
| A-site treated as point charge (for inorganic Cs) | Cs is monatomic; no orientational DOF | FA⁺ or MA⁺ requires rotational disorder treatment |
| Constant cell parameters during relaxation | Separates cell optimisation from atomic relaxation | May miss volume changes under pressure or phase transitions |

---

## 2. Electronic Structure Approximations

| Approximation | Effect | Known Error |
|---------------|--------|-------------|
| DFT (KS formalism) | Maps interacting electrons → non-interacting | Exact in principle; XC approximation is the source of errors |
| GGA (PBEsol) | Local + semi-local XC energy density | Underestimates band gap ~0.3–1.0 eV (self-interaction error) |
| Pseudopotential/PAW | Replaces core electrons with effective potential | Accurate for valence electrons if correct dataset used |
| Non-relativistic core | Core relativistic effects absorbed into PAW datasets | Scalar-relativistic corrections included; SO from valence only |
| Perturbative SOC | First-order correction to collinear KS states | Accurate when Δ_SO ≪ crystal-field splitting (valid for CsPbI₃) |
| Scissor correction | Linear shift of conduction bands | Neglects k-dependent band renormalisation; ±0.1 eV accuracy |
| Collinear spin | No non-collinear magnetism | Valid for non-magnetic halide perovskites |

---

## 3. Numerical Approximations

| Parameter | Value Used | Convergence Criterion | Residual Error |
|-----------|------------|----------------------|----------------|
| Plane-wave cutoff | 450 eV | < 1 meV/atom vs. Ecut convergence | < 1 meV/atom |
| k-point mesh | [6, 6, 6] | < 1 meV/atom vs. k-mesh convergence | < 1 meV/atom |
| SCF energy threshold | 10⁻⁸ eV | Self-consistent convergence | < 10⁻⁸ eV/cycle |
| Force threshold | 0.01 eV/Å | Geometry optimisation | < 0.01 eV/Å |
| Fermi-Dirac smearing | 0.05 eV | Smooth BZ sampling | < 0.01 eV on gap |
| Hessian step Δ | 0.01 Å | Finite-difference Hessian | ~0.1% error on force constants |
| Phonon supercell | 2×2×2 | Force constant range | Neglects interactions beyond 2× cell |

---

## 4. Range of Validity

### 4.1 What this calculation CAN address

- **Relative stability** of α, γ, δ phases (energy differences, Gibbs hierarchy)
- **Electronic structure** at T = 0 K in the absence of defects
- **Qualitative band gap** (order of magnitude, direct/indirect character)
- **Corrected band gap** via scissor operator (±0.1–0.2 eV from experiment)
- **Dynamical stability** of the structure (phonon analysis)
- **Zone-centre vibrational modes** (Raman/IR active modes at Γ)

### 4.2 What this calculation CANNOT reliably address

- **Finite-temperature stability** — thermal expansion, entropy, free energy, phase
  transitions require phonon free energy or MD
- **Defect properties** — point defects, vacancies, interstitials require supercell
  defect calculations with charge corrections
- **Carrier mobility** — requires electron-phonon coupling (not implemented here)
- **Optical spectra** — BSE or TDDFT needed; KS gaps ≠ optical gaps
- **Absolute accuracy of band gaps** — even corrected PBE+SOC+HSE scissor has
  ±0.1–0.2 eV systematic error; experimental comparison is required
- **Long-range structural disorder** — FA⁺ rotation, halide segregation, phase
  coexistence require statistical mechanics beyond single-unit-cell DFT

---

## 5. Comparison to Literature

For α-CsPbI₃ (cubic, Pm-3m):

| Method | Band gap (eV) | Source |
|--------|--------------|--------|
| PBE (this work) | ~1.44 | Computed |
| PBE + SOC (this work) | ~0.60 | Computed |
| HSE06 + SOC (literature) | ~1.55 | Brivio et al. (2014) |
| Experiment | 1.73 | Sutton et al. (2018) |
| This work (corrected) | ~1.52 | Scissor: PBE + χSOC + χHSE |

Error vs. experiment: ~0.2 eV — acceptable for comparative phase studies.

---

## 6. Reproducibility Statement

All calculations in this pipeline are fully reproducible from:
- `configs/default_params.yaml` — all numerical parameters
- `structures/` — initial crystal structures (JSON format, ASE compatible)
- `src/dft_cspbi3/` — Python source code (version-controlled)

The only external dependency is a licensed installation of GPAW (≥ 24.1.0)
with the corresponding PAW datasets.
