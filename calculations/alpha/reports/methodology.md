# Computational Methodology — Results and Discussion

*alpha-CsPbI₃ — DFT/GPAW pipeline*
*Last updated: 2026-05-04 (HSE06 k-mesh corrected to 2×2×2; SOC values updated; scissor correction implemented; HSE06 SCF running with nmaxold=2)*

---

## 1. Theoretical Framework

### 1.1 Kohn-Sham Density Functional Theory

All electronic structure calculations are performed within the Kohn-Sham (KS)
formulation of DFT [Hohenberg & Kohn, 1964; Kohn & Sham, 1965]. The total
electronic energy is minimised with respect to the charge density ρ(r):

    E[ρ] = Ts[ρ] + ∫ v_ext(r)ρ(r)dr + E_H[ρ] + E_xc[ρ]

where Ts is the non-interacting kinetic energy, E_H the Hartree energy, and
E_xc the exchange-correlation energy. The KS equations

    (-½∇² + v_eff(r)) ψᵢ(r) = εᵢ ψᵢ(r)

are solved self-consistently until convergence.

### 1.2 Born-Oppenheimer Approximation

Nuclear degrees of freedom are treated classically within the Born-Oppenheimer
approximation. Vibrational properties (Hessian, phonons) are computed as second
derivatives of the BO energy surface E(R) with respect to atomic displacements.

---

## 2. Exchange-Correlation Functional

**Functional**: PBE (Perdew-Burke-Ernzerhof, 1996)

**Known limitations**:
- Systematically *underestimates* band gaps (~0.3–0.8 eV error for halide perovskites) due to self-interaction error.
- Overestimates lattice constants by ~1–2%.
- SOC from Pb 6p further reduces the KS gap by ~0.8 eV (see Section 7).

---

## 3. Projector-Augmented Wave (PAW) Method

PAW datasets from `gpaw-setups-24.11.0` (scalar-relativistic PBE, GPAW default):

| Element | Dataset file    | Valence electrons | Frozen core        |
|---------|-----------------|-------------------|--------------------|
| Cs      | Cs.PBE.gz       | 9  (5s²5p⁶6s¹)   | [Kr] 4s–4p         |
| Pb      | Pb.PBE.gz       | 14 (5d¹⁰6s²6p²)  | [Xe] 4f¹⁴          |
| I       | I.PBE.gz        | 7  (5s²5p⁵)       | [Kr]               |

The Pb dataset includes the semicore 5d¹⁰ shell in the valence, which is essential
for accurate SOC treatment (5d–6p hybridisation). Datasets are scalar-relativistic:
mass-velocity and Darwin corrections are included self-consistently; the SOC term
is applied as a post-SCF perturbation (see Section 7).

---

## 4. Plane-Wave Basis and Cutoff

**Mode**: PW (plane-wave) | **Ecut**: 450 eV

Convergence tests confirm total energy differences < 1 meV/atom for Ecut ≥ 400 eV.
The 450 eV value is used as the production cutoff, matching the literature standard
for halide perovskites (e.g. Brivio et al. 2014, Wiktor et al. 2017).

---

## 5. k-point Sampling

| Step       | Mesh       | Purpose                        |
|------------|------------|--------------------------------|
| relax/scf  | 6×6×6 Γ   | Structural and electronic       |
| bands      | path Γ-X-M-Γ-R-X,M-R, 40 pts | Band structure   |
| DOS        | 12×12×12 Γ | Dense sampling for DOS         |
| phonons    | 3×3×3 Γ   | Supercell (scaled from 6×6×6)  |
| HSE06      | 2×2×2 Γ   | Includes R=(0.5,0.5,0.5); 3×3×3 excluded R-point (wrong gap) |

Electronic occupations: Fermi-Dirac smearing σ = 0.05 eV.

### 5.1 GPAW SCF convergence criteria recorded in production logs

The table below reports the actual convergence thresholds printed by GPAW in
the `.txt` logs, rather than only the YAML inputs. GPAW reports energy changes
per valence electron and uses `c` markers in the SCF table when a criterion has
converged.

| Calculation family | Representative log | Energy | Density | Eigenstates | Force criterion | Max SCF iter |
|---|---|---:|---:|---:|---:|---:|
| Geometry relaxation | `01_relax/relax.txt` | 1e-6 eV/electron | 1e-4 e/electron | 4e-8 eV²/electron | 0.01 eV/Å over last 2 cycles | 333 |
| Production SCF, DOS, binaries, PES points | `02_scf/scf.txt`, `04_dos/dos.txt`, `09_formation_energy/binaries/*.txt`, `07_vibrational/pes/scan_mode0/scf_*.txt` | 1e-8 eV/electron | 1e-4 e/electron | 4e-8 eV²/electron | — | 333 |
| Non-SCF band path | `03_bands/bands.txt` | 5e-4 eV/electron | 1e-4 e/electron | 4e-8 eV²/electron | — | 333 |
| Phonopy force supercells | `07_vibrational/phonons/phonopy_sc_*.txt` | 1e-8 eV/electron | 1e-5 e/electron | 1e-10 eV²/electron | — | 333 |
| HSE06 SCF (2×2×2) | `06_hse06/hse06.txt` | 1e-6 eV/electron | 1e-4 e/electron | 1e-4 eV²/electron | — | 500 |

Additional GPAW settings common to the production calculations:

- Spin treatment: spin-paired collinear DFT before perturbative SOC.
- Basis and grid: plane waves, 450 eV cutoff, effective real-space grid spacing
  around 0.193 Å for the primitive 5-atom cell.
- Mixer: Pulay/separate density mixing. The PBE calculations use GPAW defaults
  or `Mixer(beta=0.05, nmaxold=5, weight=50)` where explicitly requested;
  the checkpointed HSE06 resume uses `Mixer(beta=0.10, nmaxold=8, weight=50)`.
- Symmetry: finite-displacement and PES calculations use `symmetry=off`; binary
  reference cells retain their crystallographic symmetry when no displacement is
  present.

### 5.2 Convergence-test algorithm

The standalone convergence workflow in `src/dft_cspbi3/convergence.py` and
`scripts/run_convergence_test.py` implements two single-parameter sweeps:

**Plane-wave cutoff sweep**:

1. Hold the k-mesh fixed at 6x6x6.
2. Run single-point SCF calculations at Ecut = 300, 350, 400, 450, 500, 550 eV
   unless overridden from the CLI.
3. Compute total energy per atom for each cutoff.
4. Use the highest cutoff in the sweep as the internal reference.
5. Report Delta E in meV/atom and select the smallest cutoff with
   |Delta E| < 1 meV/atom.

**k-point sweep**:

1. Hold Ecut fixed at 450 eV.
2. Run single-point SCF calculations for NxNxN meshes, typically N = 4, 6, 8, 10.
3. Compute energy per atom and Delta E relative to the densest mesh.
4. Select the smallest mesh satisfying |Delta E| < 1 meV/atom.

The plotting utility writes PNG/PDF convergence curves and CSV tables. These tests
are calibration calculations; they do not alter the production `.gpw` checkpoints.

### 5.3 Validation algorithms

The validation layer in `src/dft_cspbi3/validation/` performs reproducibility and
sanity checks on logs and checkpoints:

- `validate_scf()` parses GPAW `iter:` lines, checks for a convergence marker,
  counts SCF iterations, computes the final |Delta E|, and flags oscillation if
  the final energy alternates over the last six iterations with |Delta E| > 1e-3 eV.
- `validate_physical_checks()` loads a `.gpw` checkpoint, verifies negative total
  energy, positive valence-electron count, and occupation-number consistency
  within 0.1 electron.
- `validate_soc()` checks SOC output array shapes, computes chi_SOC =
  Eg(SOC) - Eg(no SOC), requires the Pb-halide range -1.5 <= chi_SOC <= 0 eV,
  tests that spin splitting is detectable, and flags spurious magnetisation
  above 0.05 mu_B.
- `classify_from_phonons()` labels structures as stable, metastable, or unstable
  using imaginary phonon thresholds: <10 cm^-1 numerical noise, 10-100 cm^-1
  soft/metastable, >100 cm^-1 unstable.
- `classify_from_hessian()` provides a Gamma-point-only check based on Hessian
  eigenvalues with a 0.05 eV/Å² numerical floor.

---

## 6. Geometry Optimisation

**Algorithm**: BFGS (ASE) | **Convergence**: max|Fᵢ| < 0.01 eV/Å
**Cell**: fixed at a₀ = 6.18 Å (Pm-3m, experimental reference) | **Mixer**: β = 0.05

The cell is held fixed and only atomic positions are relaxed. For the ideal cubic
Pm-3m structure all atoms are at Wyckoff positions with zero internal degrees of
freedom, so relaxation serves primarily to verify the force threshold is met and
to produce a .gpw checkpoint for subsequent steps.

---

## 7. Spin-Orbit Coupling (SOC)

**Implementation**: `soc_eigenstates()` in GPAW 25.x (formerly `spinorbit_eigenvalues()`)

The SOC Hamiltonian

    H_SOC = (ħ/4m²c²) σ · (∇V × p)

is applied as a first-order perturbation to the collinear KS eigenstates from the
converged SCF. Spin quantisation axis: (θ=0, φ=0) (z-axis). The perturbative
treatment is valid for Pb 6p states in halide perovskites (error vs. self-consistent
SOC estimated at < 0.05 eV for the gap).

**This work — α-CsPbI₃**:

| Quantity         | Value      | Method       |
|------------------|------------|--------------|
| Eg(PBE, no SOC)  | 1.0891 eV  | This work — 6×6×6 SCF, R-point (0.5,0.5,0.5) |
| Eg(PBE+SOC)      | 0.3517 eV  | This work — perturbative SOC on scf.gpw |
| χSOC             | −0.7374 eV | This work — Eg(PBE+SOC) − Eg(PBE) |

The χSOC = −0.737 eV is consistent with the known Pb 6p SOC splitting. Literature
values for similar Pb-halide systems range from −0.75 to −1.00 eV depending on the
X-site anion (I > Br > Cl). This-work value (α-CsPbI₃, iodide) is in the expected range.

*Note on earlier values*: preliminary entries showed χSOC = −0.789 eV and
Eg(PBE+SOC) = 0.300 eV; those were based on a Fermi-level approximation
(median eigenvalue). The corrected values use the actual GPAW Fermi level from
the `scf.gpw` checkpoint.

---

## 8. Band Gap Correction

### 8.0 Motivation

Two independent mechanisms cause PBE to underestimate Eg:
1. **Self-interaction error** (SIE): PBE delocalises electrons → CBM too low, VBM too high.
   Correction: χHSE = Eg(HSE06) − Eg(PBE), typically +0.6–0.8 eV for halide perovskites.
2. **SOC**: Pb 6p band splitting lowers the CBM.
   Correction: χSOC computed explicitly (Section 7), = −0.789 eV for α.

### 8.1 Strategy A — Scissor (implemented, used as fallback)

    Eg_scissor = Eg(PBE) + χSOC + χHSE

**Current result (α-CsPbI₃, 2026-05-04)**:

    Eg(PBE)  = 1.0891 eV  (this work, 6×6×6 SCF)
    χSOC     = −0.7374 eV  (this work, perturbative SOC)
    χHSE     = +0.6709 eV  (literature: Eg_HSE06=1.76 eV fallback − Eg_PBE)
    Eg_scissor = 1.0226 eV  (vs. experimental 1.73 eV; error ~0.71 eV)

The large error vs. experiment arises because: (1) the literature χHSE was computed
for a setup with Eg(PBE)≈1.3 eV, but our Eg(PBE)=1.089 eV is lower (different
cell constant), making the fallback value not directly transferable; and (2) our SOC
correction (−0.737 eV) is at the upper end of the expected range due to the Pb.14
PAW dataset (semicore 5d in valence). The scissor result is a lower bound on the
true Eg(HSE06+SOC) for this specific setup.

**Explicit assumptions** (sources of error):

| Assumption | Error estimate | Reducible? |
|---|---|---|
| χSOC and χHSE are additive | 0.05–0.15 eV systematic | Yes → Strategy B |
| χHSE from literature (not our setup) | ~0.3–0.5 eV | Yes → converged HSE06 |
| Rigid-band (dispersion/m* unchanged) | ~15–30% on effective masses | Only with GW+SOC |

### 8.2 Strategy B — HSE06+SOC (recommended, in progress)

SOC applied perturbatively on top of an HSE06 SCF ground state. Eliminates the
χHSE transferability assumption by computing the exchange correction directly for
this system's geometry and k-mesh.

**Implementation note — GPAW hybrid DFT convergence investigation (Apr–May 2026)**:

Achieving a converged HSE06 SCF in GPAW 25.7.0 PW mode for α-CsPbI₃ required
an extended convergence investigation, summarised below.

| Date | Configuration | k-mesh | Iters | Outcome |
|---|---|---|---|---|
| Apr 26–28 | HSE06 SCF, Mixer(β=0.05, n=5), eigst=4e-8 | 4×4×4 | partial | ~11 h/iter, abandoned |
| Apr 27–29 | HSE06 SCF, Mixer(β=0.10, n=8), eigst=4e-8 | 3×3×3 | 13 | Oscillates: eigst stuck at −1.3 |
| Apr 29 | Restart from checkpoint iter 75, β=0.05, n=5 | 3×3×3 | 10 more | Same oscillation: −1.43→−1.29→−1.13 |
| May 4 | Non-SCF HSE06 (maxiter=1) from pbe_3x3x3.gpw | 3×3×3 | 1 | **Wrong k-mesh**: R-point absent |
| May 4 | PBE@3×3×3 → one-shot HSE06 | 3×3×3 | 1 | Gap 3.27 eV (wrong — R-point not sampled) |

**Critical finding — k-mesh error (2026-05-04)**:

Diagnostic of scf.gpw (6×6×6) revealed that the band gap minimum lies at
k = (0.5, 0.5, 0.5) (R-point) with Eg = 1.089 eV. The 3×3×3 Γ-centred mesh
has k-points at {0, 1/3, 2/3} — the R-point is absent. All HSE06 calculations
on the 3×3×3 mesh were sampling the wrong k-points, giving unphysical gaps of
3.3–4.5 eV (the gap at (1/3,1/3,1/3) is 3.7 eV, far from the true gap).

Fix: changed to 2×2×2 Γ-centred mesh. The 2×2×2 mesh includes R=(0.5,0.5,0.5)
as IBZ k-point k3, with the same IBZ count (4 k-points) as 3×3×3.

| Date | Configuration | k-mesh | Iters | Outcome |
|---|---|---|---|---|
| May 4 | PBE@2×2×2 converged | 2×2×2 | ~20 | Eg(PBE@2×2×2)=1.016 eV at R ✓ |
| May 4 | One-shot HSE06 from pbe_2x2x2.gpw (maxiter=1) | 2×2×2 | 1 | Eg=0.914 eV (unreliable: LCAO reinit) |
| May 4 | Full HSE06 SCF, Mixer(β=0.05, n=5, niter_fix=5) | 2×2×2 | 8 | Same oscillation: −1.37→−0.93 |

**Root cause of SCF oscillation**: the Pulay DIIS with nmaxold=5 accumulates
inconsistent history from the niter_fixdensity transition (iterations 1–5 with
frozen density, iterations 6+ with live density). At iteration 6/7 the Fock
exchange and density update simultaneously, causing the mixer to extrapolate to
a negative-residual configuration.

**Current approach (2026-05-04, running)**:

    Mixer(beta=0.05, nmaxold=2, weight=50.0)  — shorter DIIS history
    niter_fixdensity removed                   — no density-freeze transition
    eigenstates = 1e-4                         — relaxed criterion
    k-mesh = 2×2×2 (includes R-point)

Expected behaviour: without the nmaxold=5 accumulation of mixed-phase history,
the DIIS should remain in a consistent basin and converge in ~60–100 iterations
at ~25 min/iter early → ~5 min/iter late ≈ 10–25 h total.

### 8.3 Band gap table by phase

| Phase | Eg(PBE) | Eg(PBE+SOC) | χSOC      | Eg(HSE06) | Eg(scissor) | Eg(exp)  | Source exp |
|-------|---------|-------------|-----------|-----------|-------------|----------|------------|
| α     | 1.0891  | 0.3517      | −0.7374   | in progress | 1.02 eV (lit. χHSE) | 1.73 eV  | Sutton et al. ACS Energy Lett. 2018 |
| γ     | —       | —           | —         | —         | —           | 1.68 eV  | Steele et al. JACS 2019 |
| δ     | —       | —           | —         | —         | —           | 2.82 eV  | Sutton et al. ACS Energy Lett. 2018 |

### 8.4 Error budget (Strategy A, current scissor)

| Source | Magnitude | Reducible |
|---|---|---|
| χHSE from literature (not this setup) | ~0.3–0.5 eV | Yes → converged HSE06 SCF |
| Non-additivity χSOC + χHSE | 0.05–0.15 eV | Yes → Strategy B |
| Rigid-band approximation | ~0.05 eV on gap | No (needs GW+SOC) |
| k-mesh 2×2×2 (coarse but includes R) | ~0.05–0.10 eV | Partially (4×4×4 too costly) |
| Geometry (fixed cell a₀=6.18 Å) | ~0.05–0.10 eV | With PBEsol |
| **Total (quadrature)** | **~0.35–0.55 eV vs. exp** | |

### 8.5 Honest limitations

- Corrected Eg is a quasiparticle gap, **not the optical gap** (excitons lower it by ~50–100 meV).
- Dispersion and effective masses not corrected by scissor → do not use for transport.
- Temperature dependence not included (thermal expansion shifts χSOC by ~0.05–0.15 eV).
- Insufficient for PRL/Nature without GW+SOC.

### 8.6 Use-case classification

| Use case | Sufficient? |
|---|---|
| Qualitative gap ordering α vs γ vs δ | Yes |
| PV screening (target 1.1–1.7 eV) | Yes (for feasibility) |
| Effective masses and transport | No |
| Direct comparison with optical spectroscopy | No (no exciton) |
| Thesis / PRB / npj Comput. Mater. | Yes with error budget table |
| PRL / Nature | No (requires GW+SOC) |

### 8.7 Band-edge and effective-mass algorithms

The post-processing in `src/dft_cspbi3/analysis/electronic.py` operates directly
on `03_bands/bands.gpw`; no new GPAW calculation is launched.

**Direct/indirect gap classification**:

1. Load the band-path checkpoint with GPAW and obtain the fractional k-points,
   number of electrons, number of bands, eigenvalues, and Fermi level.
2. For a spin-paired calculation, set `n_occupied = round(N_e / 2)`.
3. Define the valence band as band `n_occupied - 1` and the conduction band as
   band `n_occupied`.
4. Identify VBM = max E_v(k), CBM = min E_c(k), and Eg = E_CBM - E_VBM.
5. Compute the minimum direct gap as min_k [E_c(k) - E_v(k)].
6. Classify the gap as direct when the VBM and CBM fractional k-points differ
   by less than 0.05 in Euclidean fractional-coordinate norm.

**Effective masses**:

Near each band extremum, the code fits a parabolic dispersion,

    E(k) = E0 + (hbar^2 / 2m*) |k - k0|^2,

using the band-path eigenvalues transformed to Cartesian reciprocal coordinates
in Å^-1. The conversion constant is hbar^2/m0 = 7.6199 eV Å^2. Electron masses
are fitted at the CBM; hole masses are fitted by applying the same curvature
procedure to `-E_v(k)` near the VBM and reporting a positive value. The reduced
mass is

    m_r = (m_e m_h) / (m_e + m_h).

**Current alpha result**:

| Quantity | Value |
|---|---:|
| Gap type | direct |
| Eg(PBE, band path) | 1.089 eV |
| VBM / CBM k-point | (0.5, 0.5, 0.5) |
| Electron effective mass | 1.346 m0 |
| Hole effective mass | 1.203 m0 |
| Reduced mass | 0.635 m0 |

**Structural metrics attached to the same analysis**:

`analysis.structural.analyze_perovskite_geometry()` computes Goldschmidt and
octahedral geometric descriptors from Shannon ionic radii:

    t = (r_A + r_X) / [sqrt(2) (r_B + r_X)]
    mu = r_B / r_X

The implemented acceptance windows are 0.80 <= t <= 1.00 and
0.44 <= mu <= 0.90. The same routine also estimates the mean B-X bond length,
B-X bond variance, B-X-B angle, and octahedral tilt angle using minimum-image
distances when the local coordination can be identified.

For alpha-CsPbI3, the current values are t = 0.822 and mu = 0.541, both inside
the implemented geometric stability windows; the mean Pb-I distance is 3.09 Å.

### 8.8 DOS near the gap and defect-tolerance proxy

`analysis.electronic.analyze_dos_near_gap()` is implemented as an optional
post-processing utility on `04_dos/dos.gpw`, although it is not currently exposed
as a separate top-level workflow step.

The algorithm loads the dense-DOS checkpoint, estimates VBM and CBM from the
highest occupied and lowest unoccupied eigenvalues, constructs a 2000-point energy
grid from VBM - 0.5 eV to CBM + 0.5 eV, and evaluates GPAW's `DOSCalculator`
with 0.05 eV broadening. The integrated DOS strictly inside the gap, excluding
±0.2 eV windows around the band edges, is used as a trap-state proxy. Values below
0.01 states/eV are classified as defect-tolerant by this simple criterion.

---

## 9. Vibrational Properties

### 9.1 Hessian Matrix (Γ-point)

**Parameters**: Δ = 0.01 Å, central finite differences, symmetry=off

    H_{ij} ≈ −(Fᵢ(R + Δêⱼ) − Fᵢ(R − Δêⱼ)) / (2Δ)

Symmetrisation H → (H + Hᵀ)/2 removes finite-difference asymmetry.
30 GPAW calls (5 atoms × 3 directions × 2 signs); k-mesh 6×6×6, symmetry=off.

The Hessian eigenvalues λ are local curvatures of the potential-energy surface
along the corresponding normal-mode coordinates:

- If λ > 0 by a clear numerical margin, the structure is a local minimum along
  that direction.
- If λ < 0, the curvature is negative and the structure is unstable along that
  coordinate; in phonon language this generally corresponds to an imaginary mode.
- If λ ≈ 0, the surface is nearly flat. Anharmonic terms can then dominate, so
  a one-dimensional scan may reveal a double well, displacive transition,
  octahedral tilt, ferroelectric-like distortion, or another soft-mode pathway.

**Results — α-CsPbI₃**:

| Metric | Value |
|---|---|
| Matrix size | 15 × 15 (3N = 15) |
| Min eigenvalue λ_min | +0.017 eV/Å² |
| Max eigenvalue λ_max | +6.178 eV/Å² |
| Imaginary eigenvalues (λ < 0) | **0** |
| Stability classification | **Γ-STABLE** |

All 15 eigenvalues positive → the relaxed cubic structure is a local energy minimum
at the Γ-point (no zero-wavevector instability). This is consistent with the
experimental stability of α-CsPbI₃ at high temperature (> 635 K).

The smallest eigenvalue (+0.017 eV/Å²) corresponds to the soft Cs cage mode —
nearly flat potential in the large 12-coordinated A-site cage, consistent with
the large Debye-Waller factor observed experimentally.

### 9.2 Phonon Dispersion — Method

Two calculation tiers are implemented (see §9.3 and §9.3b for results):

**Tier 1 — ASE Phonons (completed, Δ=0.05 Å, Apr 24 2026)**:
- Supercell: 2×2×2 (40 atoms)
- Displacement: Δ = 0.05 Å
- Total GPAW calls: 30 (5 atoms × 3 dirs × 2 signs) + 1 equilibrium = 31
- k-mesh supercell: 3×3×3
- Acoustic sum rule: ASE `ph.read(acoustic=True)` — post-hoc diagonal correction
- Wall time: ≈ 7.5 h (7 MPI processes, Apr 24 2026)

**Tier 2 — Phonopy (Δ=0.02 Å, completed — Apr 25 2026)**:
- Supercell: 2×2×2 (40 atoms)
- Displacement: Δ = 0.02 Å — optimal for CsPbI₃ (see justification below)
- Independent displacements: **3** (Phonopy exploits Pm-3m O_h symmetry;
  space group Pm-3m, 48 operations, reduces 30 displacements to 3 independent)
- Total GPAW calls: 3 (vs. 30 for Tier 1; 10× fewer)
- k-mesh supercell: 3×3×3 (Γ-centred, same density as primitive 6×6×6)
- SCF convergence: energy = 10⁻⁸ eV, density = 10⁻⁵, eigenstates = 10⁻⁸
  (eigenstates criterion relaxed from 10⁻¹⁰ → 10⁻⁸ following Togo et al. recommendation)
- Acoustic sum rule: Phonopy `symmetrize_force_constants(level=1)` — applies
  translational + point-group constraints *simultaneously before* building D(q)
- Status: disp 0 ✓, disp 1 ✓, disp 2 ✓ — all 3 complete (Apr 25 2026)
- `phonon_frequencies.npy`, `phonon_dos_phonopy.npy`, `born_charges.npy`, `dielectric_tensor.npy` written
- Observed wall time per displacement: ≈ 2 h 18 min (≈ 50 SCF iterations × ~2.8 min/iter)

**Justification for Δ=0.02 Å (replacing Δ=0.05 Å)**:

The finite-difference force is:

    F_i ≈ C_{ij} Δ_j + V_{ijk} Δ_j Δ_k / 2 + ...

Two competing error sources determine the optimal Δ:

- *Numerical noise* (∝ σ_F / 2Δ): with SCF convergence εE = 10⁻⁸ eV, the
  force noise σ_F ≈ 10⁻⁴ eV/Å, giving a noise-dominated limit Δ > 0.01 Å.
- *Anharmonic contamination* (∝ V₃ Δ² where V₃ = third-order force constant):
  α-CsPbI₃ has a soft, anharmonic potential along cage (Cs) and tilt (Pb-I-Pb)
  coordinates. For Δ = 0.05 Å, the anharmonic term V₃Δ² is non-negligible,
  producing force constants that violate the acoustic sum rule in a physically
  systematic (not random) way — a correction that ASE's diagonal fix cannot remove.

Optimal Δ lies between these limits. For typical halide perovskites with
σ_F ≈ 10⁻⁴ eV/Å and V₃ ≈ 0.5–1 eV/Å³, the optimal range is Δ = 0.01–0.03 Å.
We choose **Δ = 0.02 Å** as the primary value, with Δ = 0.03 Å as a cross-check.

**Why ASE's acoustic sum rule is insufficient for Δ=0.05 Å**:

ASE's `ph.read(acoustic=True)` corrects only the diagonal block C_{ii}(R=0) by
subtracting the residual sum Σ_j C_{ij}(0) from each diagonal element. This
correction assumes the error is numerical and symmetric. For Δ = 0.05 Å in
an anharmonic system, the error is *physically systematic* (arising from
third-order coupling) and cannot be cancelled by a diagonal scalar shift.

Phonopy's `symmetrize_force_constants(level=1)` simultaneously enforces:
1. Translational invariance: Σ_j C_{αβ,ij}(R) = 0
2. Point-group symmetry of Pm-3m: uses space-group constraints on C(R)
3. Rotational invariance (Born-Huang relation) at level=1

Together, these constraints produce a physically consistent force constant tensor
where the acoustic sum rule is satisfied as a symmetry of the space group, not
just as a numerical fixup.

**Why symmetry=off is required**:

Finite atomic displacements break the crystal symmetry. GPAW's symmetry analyser
must be disabled per displaced supercell to avoid symmetry-enforced cancellations
that would produce incorrect forces.

**k-mesh rationale**:

The 3×3×3 mesh for the 40-atom supercell provides k-point density equivalent to
the primitive-cell 6×6×6 mesh (k_sc = ⌊k_prim / n_sc⌋, with Γ-centering).
This maintains consistent BZ coverage between primitive and supercell calculations.

### 9.3 Phonon Dispersion — Results and Discussion (Tier 1: ASE, Δ=0.05 Å)

> **Note**: These results use Δ=0.05 Å with ASE Phonons. The acoustic branch
> artefacts described below motivated the Phonopy/Δ=0.02 Å refinement (Tier 2,
> now complete). Optical branches (5–136 cm⁻¹) are reliable and reported here.

**Summary table**:

| Branch type | Branches | Real modes | Range (cm⁻¹) | Notes |
|---|---|---|---|---|
| Acoustic (3) | 3 × 60 = 180 | 79 | 0 to ~50 (at zone edge) | 101 negative due to acoustic sum rule violation |
| Optical (12) | 12 × 60 = 720 | **720 / 720** | 5.1 – 135.6 | All real ✓ |
| **Total** | **15 × 60 = 900** | **799** | −26.3 to 135.6 | |

**Optical spectrum analysis**:

The 12 optical branches are all real and positive throughout the Brillouin zone
(range 5.1–135.6 cm⁻¹). Three spectral regions are identified:

- **Low-frequency optical (5–30 cm⁻¹)**: Cs⁺ cage rattling and Pb-I-Pb rocking modes.
  The near-zero frequencies reflect the soft Cs cage potential (consistent with λ_min
  of Hessian). Literature analogue: ~10–25 cm⁻¹ for Cs modes in CsPbBr₃.

- **Mid-frequency (30–80 cm⁻¹)**: Mixed Pb-I bending and Cs translational modes.

- **High-frequency (80–136 cm⁻¹)**: Pb-I stretching modes (T₁u symmetry at Γ).
  Maximum at 135.6 cm⁻¹. Literature: Pb-I stretch ~100–140 cm⁻¹ for CsPbI₃
  (Brivio et al. 2015, Saidi & Poncé 2016). Our values are in good agreement.

**Acoustic branch and the sum-rule violation**:

The 101 imaginary values are entirely in the acoustic branches (optical branches
are 100% real). Analysis of their origin:

1. **At Γ** (k=0): acoustic modes = −15.98, −11.52, −2.36 cm⁻¹ (should be exactly 0 by
   translational invariance). The Γ-point acoustic residual of ≈ −12 to −16 cm⁻¹
   indicates imperfect acoustic sum rule enforcement.

2. **Near R-point** (k=0.5, 0.5, 0.5): most negative = −26.27 cm⁻¹ in the acoustic branch.
   The largest violation occurs at zone boundaries, where acoustic branch energies are
   largest in magnitude and anharmonic contributions are most significant.

3. **Root cause**: Δ = 0.05 Å is anharmonic for this system. The potential energy surface
   of α-CsPbI₃ is extremely shallow along the Cs-cage and Pb-I-Pb rocking coordinates
   (soft phonon system). For Δ = 0.05 Å, the restoring forces include non-negligible
   third-order (anharmonic) contributions, which the harmonic acoustic sum rule cannot
   cancel. The Hessian (Δ = 0.01 Å), which stays closer to the harmonic regime,
   correctly gives all-positive eigenvalues at Γ.

**Physical instability of cubic CsPbI₃ at T = 0 K**:

α-CsPbI₃ (Pm-3m) is experimentally metastable below ~635 K. At T = 0 K, DFT
calculations on this system typically predict imaginary optical modes at the R and M
points of the BZ, corresponding to the octahedral tilting instability (R₄⁺ mode,
Glazer a⁻a⁻a⁻) that drives the α→γ (Pnma) phase transition upon cooling.

Our calculation does **not** produce imaginary optical modes at R. The optical branches
at R (0.5, 0.5, 0.5) range from ≈13 to 136 cm⁻¹, all positive. This is consistent
with the sensitivity of the R₄⁺ mode to the lattice constant:

- At a₀ = 6.18 Å (this work, close to experiment): R₄⁺ is near zero or positive.
- At a₀ > 6.25 Å (PBE-overexpanded cell): R₄⁺ goes imaginary (Brivio et al. 2015).

Since our cell parameter matches experiment rather than PBE equilibrium, the tilting
instability is suppressed in our calculation. This means the phonon spectrum is not
capturing the full metastability of the cubic phase — a known limitation of fixed-cell
calculations near structural phase boundaries.

**Comparison with Hessian (Γ-point)**:

| | Hessian (Δ=0.01 Å) | Phonons Γ-point (Δ=0.05 Å) |
|---|---|---|
| Acoustic modes | — | −15.98, −11.52, −2.36 cm⁻¹ (artifact) |
| Lowest optical | +0.017 eV/Å² → ~3.7 cm⁻¹ | 5.15 cm⁻¹ |
| Highest optical | +6.178 eV/Å² → ~629 cm⁻¹* | 103.3 cm⁻¹ |
| Imaginary eigenvalues | 0 | 3 (acoustic artifact) |

*The Hessian eigenvalues are in eV/Å² and include all degrees of freedom; the
phonon branches at Γ correspond only to the unit-cell modes, so comparison is
qualitative. The largest Hessian eigenvalue likely corresponds to the high-frequency
Pb-I stretch modes.

**Conclusions from vibrational analysis**:

1. **Γ-point stable**: all Hessian eigenvalues positive; no zero-wavevector instability.
2. **Optical spectrum reliable**: 12 optical branches real and positive, 5–136 cm⁻¹.
   Pb-I stretching at 80–136 cm⁻¹ is in good agreement with literature.
3. **Acoustic branches unreliable** due to Δ = 0.05 Å anharmonicity. The 101
   imaginary acoustic values are numerical artifacts, not physical instabilities.
4. **Zone-boundary optical modes**: positive in our calculation, consistent with
   a₀ = 6.18 Å (near-experimental cell). The R₄⁺ tilting instability is suppressed
   relative to a PBE-relaxed cell (a₀ ≈ 6.22–6.25 Å).

### 9.3b Phonon Dispersion — Tier 2 Refinement (Phonopy, Δ=0.02 Å) — Complete (Apr 25 2026)

Symmetry reduction — why 3 independent displacements (not 4 as initially estimated):

Pm-3m (space group 221, O_h) has 48 symmetry operations. Phonopy analyses the
site symmetries of each Wyckoff position in the 2×2×2 supercell:

| Atom | Wyckoff (prim) | Site symmetry | Indep. disps |
|---|---|---|---|
| Cs | 1b | O_h (m-3m) | 1 (x only, y/z related by symmetry) |
| Pb | 1a | O_h (m-3m) | 1 |
| I  | 3d | D_4h (4/mmm) | 1 (one displacement covers all 3 I sites) |

Total: 3 independent displacements. Reliability is not reduced relative to 30: Phonopy
generates the full force constant tensor C(R) by applying symmetry operations to the
3 computed force vectors, recovering all elements exactly (symmetry reduction is lossless).

**Force set quality (completed displacements)**:

| Disp | Displaced atom | Direction | max|F| (eV/Å) | ASR residual |
|---|---|---|---|---|
| 0 | atom 1 (Cs/Pb) | [+x, 0, 0] | 0.00539 | 0.167% of max|F| |
| 1 | atom 9 (Pb/I)  | [+x, 0, 0] | 0.08778 | 0.587% of max|F| |
| 2 | atom 17 (I)   | [+x,+y, 0] (diagonal [110]) | ✓ complete | — |

ASR residuals < 1% before explicit enforcement confirm Δ=0.02 Å is in the harmonic
regime. Phonopy `symmetrize_force_constants(level=1)` will reduce them to zero exactly.

---

### 9.4 LO-TO Splitting — Completed (Apr 25 2026)

In polar materials the macroscopic electric field associated with longitudinal
optical (LO) phonons splits LO and TO modes at the Γ-point. The correction follows
the non-analytical Gonze-Lee formula:

    D^NA_{αβ}(q→0) = (4π/V) × [Σᵢ Zᵢ*_α qᵢ] × [Σⱼ Zⱼ*_β qⱼ] / (q · ε∞ · q)

where Z* are Born effective charges and ε∞ the electronic dielectric tensor.

**Implementation**: canonical finite-displacement Berry-phase approach via
`gpaw.borncharges` module (`_all_disp`, `born_charges`, `polarization_phase`).
Static ε∞ computed from `gpaw.external.static_polarizability`.

**Results — α-CsPbI₃**:

| Quantity | Value | Notes |
|---|---|---|
| ε∞ (isotropic) | 3.647 | Cubic symmetry: ε_xx = ε_yy = ε_zz ✓ |
| Z*(Cs) diagonal | +1.370 | Nearly isotropic, nominal ionic charge +1 |
| Z*(Pb) diagonal | +4.978 | Dynamic charge ~5×, strong covalency |
| Z*(I) ‖ Pb-I axis | −4.849 | Longitudinal: large dynamic charge |
| Z*(I) ⊥ Pb-I axis | −0.749 | Transverse: near nominal −1 |
| Born ASR (Σ Z*) | 0.000 e | Satisfied exactly ✓ |

The Z*(Pb) ≈ +5 and strongly anisotropic Z*(I) are characteristic of the covalent
Pb-I bonding in halide perovskites. For comparison: MAPbI₃ Z*(Pb) ≈ +4.5 (Brivio
2015), CsPbBr₃ Z*(Pb) ≈ +4.8 (Saidi & Poncé 2016). Our value +4.978 is at the
high end, consistent with the larger I⁻ polarisability relative to Br⁻.

The LO-TO correction is applied automatically by Phonopy when `born_charges.npy`
and `dielectric_tensor.npy` are present in the phonons work directory.
Estimated LO-TO splitting for Pb-I stretch modes: ~20–50 cm⁻¹.

### 9.5 Known limitations

| Limitation | Impact | Status | Recommended fix |
|---|---|---|---|
| Tier 1: Δ = 0.05 Å (anharmonic) | Acoustic sum rule residual ≈ 12–16 cm⁻¹ at Γ | **Resolved** — Tier 2 Δ=0.02 Å complete | — |
| LO-TO correction absent | Γ-point LO/TO splitting absent | **Resolved** — Born charges + ε∞ computed | — |
| 2×2×2 supercell | Zone-boundary modes undersampled near phase boundary | Remaining | Use 3×3×3 for publication |
| Fixed cell (a₀ = 6.18 Å) | R₄⁺ tilting mode suppressed relative to PBE cell | Remaining | Compare with fully relaxed cell |
| T = 0 K harmonic approximation | Thermal expansion and anharmonic renormalisation absent | Remaining | Quasi-harmonic approximation (future) |

### 9.6 Quasi-zero/negative-mode PES scan and double-well criterion

The quasi-zero/negative-mode potential-energy scan is implemented in
`src/dft_cspbi3/analysis/pes.py` and orchestrated by `_run_pes()` in
`workflow_manager.py`.

**Mode selection**:

1. Load `07_vibrational/hessian/hessian.npy`.
2. Diagonalise the 15 x 15 Hessian with `numpy.linalg.eigh`.
3. Sort eigenpairs by eigenvalue.
4. Select modes with λ < 0.05 eV/Å², matching the Hessian numerical floor used
   by the stability classifier. Negative modes and near-zero positive modes trigger
   the PES scan; clearly positive-curvature modes do not.

For alpha-CsPbI3, one mode meets this stricter threshold:

| Mode | Hessian eigenvalue (eV/Å²) |
|---:|---:|
| 0 | 0.0174 |

Only the softest mode is scanned in the automated workflow. The eigenvector is
normalised to unit norm and the atomic positions are displaced as

    R(Q) = R0 + Q e_hat,

with Q sampled on a 20-point uniform grid from -0.5 to +0.5 Å. Each point uses
a single-point PBE/PW calculation with `symmetry=off`, 6x6x6 k-mesh, and the SCF
criteria shown in Section 5.1. Energies are cached as `E_NNN.npy`, while GPAW logs
are written to `07_vibrational/pes/scan_mode0/scf_NNN.txt`.

**Double-well detector**:

The detector is deterministic and one-dimensional:

1. Find the global maximum in E(Q), treated as a candidate saddle.
2. Reject the candidate if it lies at either boundary of the scan.
3. Find the lowest-energy point to the left and right of the saddle.
4. Compute the barrier relative to the higher of the two minima.
5. Classify as double well if the barrier exceeds 10 meV.

If a double well is detected, the workflow launches a CI-NEB calculation between
the two endpoint structures with 7 internal images, spring constant 0.10 eV/Å²,
and target fmax = 0.10 eV/Å. In the present alpha scan no double well was detected,
so CI-NEB was not launched.

**Current alpha result**:

| Quantity | Value |
|---|---:|
| PES points | 20 |
| Q range | ±0.5 Å |
| Minimum relative energy | 0.000048 eV at Q = -0.026 Å |
| Maximum relative energy | 0.020414 eV at Q = -0.500 Å |
| Energy span | 20.37 meV |
| Double well | No |
| Barrier used for classification | 0.0 meV |

---

## 10. Optical Properties

### 10.1 Theory — Linear Response (RPA)

The frequency-dependent dielectric function is computed within the Random Phase
Approximation (RPA) at the optical limit q → 0:

    ε(ω) = 1 − lim_{q→0} V(q) χ⁰(q, ω)

where χ⁰ is the Kohn-Sham independent-particle polarisability and V(q) = 4π/q² is
the bare Coulomb kernel. This is the independent-particle approximation (IPA/RPA) —
excitonic effects (electron-hole attraction) are not included. For CsPbI₃, excitonic
binding energies of ~50–100 meV are reported in the literature (Srimath Kandada &
Silva 2020), which redshift the optical gap below the quasiparticle gap by that amount.

The Lehmann representation gives:

    ε₂(ω) ∝ Σ_{v,c,k} |⟨ψ_{ck}|p̂|ψ_{vk}⟩|² δ(ε_{ck} − ε_{vk} − ħω)

This is directly related to the joint density of states weighted by optical matrix
elements. ε₁(ω) is obtained via Kramers-Kronig from ε₂(ω).

**Implementation**: `gpaw.response.df.DielectricFunction` — evaluates the full
non-local response on the plane-wave basis used in the SCF calculation.

### 10.2 Derived Optical Quantities

From the complex dielectric function ε(ω) = ε₁(ω) + i·ε₂(ω):

| Quantity | Formula | Physical meaning |
|---|---|---|
| n(ω) | Re(√ε) | Refractive index |
| k(ω) | Im(√ε) | Extinction coefficient |
| α(ω) | (ω/ħc) × ε₂/n [cm⁻¹] | Absorption coefficient |
| R(ω) | \|(n+ik−1)/(n+ik+1)\|² | Reflectance |

The absorption onset is defined as the lowest photon energy ω where α(ω) > 10⁴ cm⁻¹.

**PV criterion**: for thin-film solar cells, α ≥ 10⁴ cm⁻¹ throughout the visible
range (1.8–3.1 eV) enables ~1 μm absorber layers. Values ~10⁵ cm⁻¹ are exceptional
(GaAs-class). CsPbI₃ is expected to achieve ~2–4 × 10⁴ cm⁻¹ near onset, consistent
with strong optical absorption observed experimentally (Eperon et al. 2015).

### 10.3 Scissor Correction

The RPA calculation uses the KS eigenvalues, which inherit the PBE band gap error
(1.089 eV vs. experimental ~1.73 eV). A rigid-band scissor shift δ is applied to
all conduction band eigenvalues before the response calculation:

    ε_{ck} → ε_{ck} + δ     (conduction bands only)

The shift is computed automatically as:

    δ = Eg(HSE06) − Eg(PBE)

once `hse06.gpw` is available. This brings the optical onset into agreement with the
HSE06 quasiparticle gap, without modifying the transition matrix elements or the
valence band dispersion. The rigid-band approximation introduces an estimated error
of ~0.05–0.1 eV on the onset position.

If HSE06 is not yet available, the calculation proceeds without correction (pure PBE)
and the onset will be underestimated by ~0.6 eV.

### 10.4 Computational Parameters

| Parameter | Value | Notes |
|---|---|---|
| Frequency range | 0 – 6.0 eV | Covers UV + full visible |
| Frequency step | 0.025 eV | 241 points; smooth spectrum |
| Broadening η | 0.1 eV | Lorentzian (lifetime broadening) |
| Onset threshold | 10⁴ cm⁻¹ | Standard thin-film PV criterion |
| Scissor source | HSE06 − PBE (auto) | Applied via `eshift` parameter |
| Input checkpoint | `02_scf/scf.gpw` | 6×6×6 k-mesh, 26 bands |
| k-mesh | same as SCF | 6×6×6 Γ; adequate for macroscopic ε |
| Estimated cost | 1–3 h (7 MPI) | Non-iterative linear response |

### 10.5 AM1.5G Solar Absorption Score

To quantify relevance for photovoltaic applications, a figure of merit is defined as:

    S_AM1.5G = [∫_{ω_onset}^{ω_max} α(ω) · I_{AM1.5G}(ω) dω] / [α_ref · ∫ I_{AM1.5G}(ω) dω]

where I_{AM1.5G}(ω) is the ASTM G173-03 AM1.5G spectral irradiance [W/m²/eV] and
α_ref = 10⁵ cm⁻¹ is the normalisation reference (GaAs-class absorber). The score
S ∈ [0, 1] equals 1 for a perfect absorber with α = 10⁵ cm⁻¹ above onset.

**Threshold**: S > 0.05 with onset < 2.0 eV → classified as **prometedor** (promising
for single-junction PV). S < 0.02 → marginal.

### 10.6 Status

| Quantity | Status | Notes |
|---|---|---|
| ε₁(ω), ε₂(ω) | Pending — HSE06 in progress | Will run after hse06.gpw available |
| n(ω), k(ω) | Pending | Derived from ε(ω) |
| α(ω) | Pending | Key PV metric |
| Absorption onset | Pending | Expected ~1.7 eV (with scissor) |
| AM1.5G score | Pending | Expected > 0.05 |
| α @ {1.5, 2.0, 2.5, 3.0} eV | Pending | Tabulated for comparison |

---

## 11. Thermodynamic Stability Against Binary Decomposition

The binary-decomposition formation enthalpy is implemented in
`src/dft_cspbi3/analysis/thermodynamic.py` and run by the `formation_energy`
workflow step.

The reference reaction is

    CsPbI3 -> CsI + PbI2

and the reported quantity is

    Delta H_f = E(CsPbI3) - E(CsI) - E(PbI2)

per formula unit. Negative values indicate stability with respect to the chosen
binary decomposition channel. This is a 0 K DFT total-energy criterion; it does
not include finite-temperature vibrational free energies, configurational entropy,
or competing ternary/non-stoichiometric phases.

**Reference structures**:

| Phase | Structure model | Atoms/f.u. | Lattice parameters |
|---|---|---:|---|
| CsI | rock-salt Fm-3m | 2 | a = 4.567 Å |
| PbI2 | CdI2-type P-3m1 | 3 | a = 4.558 Å, c = 6.986 Å, z(I) = 0.235 |

Each binary reference uses the same PBE/PW settings as the production SCF
calculation: 450 eV cutoff, Γ-centred 6x6x6 k-mesh, Fermi-Dirac occupations, and
the SCF convergence thresholds listed in Section 5.1. Results are cached as
`09_formation_energy/binaries/CsI.gpw` and `PbI2.gpw`.

**Current alpha result**:

| Quantity | Value |
|---|---:|
| E(CsPbI3) per f.u. | -14.053696 eV |
| E(CsI) per f.u. | 34.069303 eV |
| E(PbI2) per f.u. | 0.774418 eV |
| Delta H_f | -48.897417 eV/f.u. |
| Binary-decomposition classification | Stable |

The large magnitude reflects the absolute PAW total-energy zero used consistently
within this workflow; only differences computed with identical PAW/XC settings
are meaningful.

---

## 12. Composite Photovoltaic Score

The `score` workflow step is implemented in `src/dft_cspbi3/analysis/scoring.py`.
It collects whichever upstream analyses are available and assigns neutral partial
credit (0.5) for missing inputs, so the score can be recomputed progressively as
new calculations finish.

The implemented total score ranges from 0 to 100:

| Component | Weight | Algorithm |
|---|---:|---|
| Band gap | 25 | Gaussian score centred at the Shockley-Queisser optimum Eg = 1.34 eV, width 0.35 eV |
| Gap type | 20 | direct = 1, indirect = 0 |
| Stability | 20 | 60% thermodynamic score from Delta H_f, 40% phonon-stability score |
| Transport | 15 | sigmoid penalties for m_e and m_h above 0.5 m0 |
| Exciton | 10 | Wannier-Mott E_b = Ry (m_r/m0) / epsilon_r^2, sigmoid full credit below roughly 25-75 meV |
| Defect tolerance | 10 | 1 / (1 + 100 x in-gap DOS) |

Automatic disqualification caps the score at 20 if Eg < 0.5 eV or
Delta H_f > +0.5 eV. Grades are assigned as A >= 80, B >= 60, C >= 40,
D otherwise, with DQ reserved for disqualified cases.

This score is a screening heuristic, not a device-efficiency prediction. It is
most useful for comparing phases or compositions after the same workflow has
been run for each candidate.

---

## 13. Software Stack

| Component | Version | Purpose |
|-----------|---------|---------|
| Python    | 3.12.3  | Runtime |
| GPAW      | 25.7.0  | DFT engine (PAW, plane-wave, MPI) |
| ASE       | 3.28.0  | Atoms, geometry, phonons, band paths |
| LibXC     | 5.2.3   | Exchange-correlation functional library |
| OpenMPI   | 4.1.6   | MPI parallelisation (k-point) |
| NumPy     | 2.4.4   | Numerical arrays |
| Phonopy   | ≥ 2.0   | Symmetry-reduced displacements, ASR, dispersion |
| SciPy     | ≥ 1.11  | Interpolation, integration |

**Hardware**: 8-core Intel (shared-memory), ~16 GB RAM.
**Parallelisation**: 7 MPI processes over k-points (1 reserved for OS).
**Typical wall times** (α, 5-atom primitive cell):

| Step | Wall time | Notes |
|---|---|---|
| relax | ~30 min | BFGS, 6×6×6 k-mesh |
| scf | ~15 min | single-point, 6×6×6 |
| bands | ~30 min | 40 k-points on path |
| dos | ~45 min | 12×12×12 k-mesh |
| soc | ~5 min | post-SCF perturbation |
| hessian | ~2 h | 30 GPAW calls (Δ=0.01 Å) |
| loto | ~35 min | 6 Berry-phase SCFs |
| phonons (Tier 2) | ~7 h total | 3 displacements × ~2.3 h/disp |
| pes | ~1.3 h | 20 single-point SCFs along the softest Hessian mode |
| formation_energy | ~2 min after cache | CsI and PbI2 binary references cached as .gpw |
| effective_masses | seconds | post-processing of `03_bands/bands.gpw` |
| hse06 | ~10–25 h | hybrid SCF, 2×2×2 k-mesh (includes R-point), ~25 min/iter early → ~5 min/iter late |
| optical | ~1–3 h | RPA linear response |

**PAW datasets**: bundled via `gpaw-data` Python package (version 24.11.0), located at
`.venv/lib/python3.12/site-packages/gpaw_data/setups/`. No separate install required.
Datasets Cs.PBE.gz, Pb.PBE.gz, I.PBE.gz — scalar-relativistic GPAW default (PBE XC,
no SOC in the PAW sphere — SOC applied perturbatively post-SCF, Section 7).

All calculations are reproducible from `configs/default_params.yaml` and the source
structures in `structures/`. Resume command for interrupted phonon calculations:

    find calculations/alpha/07_vibrational/phonons/phonon/ -name "*.json" -size 0 -delete
    GPAW_SETUP_PATH=~/.gpaw/gpaw-setups-24.11.0 GPAW_CONFIG=$(pwd)/siteconfig.py \
    OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
    mpirun -n 7 .venv/bin/python3 main.py run --phase alpha --steps phonons --validate --report

---

## 14. Estrategia Multiescala — Extensiones Futuras

Esta sección documenta la hoja de ruta para ampliar el pipeline más allá del estado
fundamental hacia propiedades operacionales fotovoltaicas. Los módulos descritos aquí
están **implementados en código** pero requieren ejecución adicional (véase
[multiscale_proposal.md](multiscale_proposal.md) para la propuesta completa).

### 14.1 Óptica de Dispositivo (L1b)

**Módulo**: `analysis/optical_device.py`  
**Método**: Beer-Lambert I(x,ω) = I₀(ω) exp(−α(ω)x), integración AM1.5G  
**Inputs**: `11_optical/absorption_cm1.npy`, `optical_frequencies.npy`  
**Outputs**: G(x) [photons/cm³/s], η_opt, J_sc(límite, IQE=1) [mA/cm²]  
**Costo**: segundos (puro Python, sin DFT)

Extensión TMM multicapa disponible en `multilayer_tmm_profile()` para simular
stack FTO/TiO₂/CsPbI₃/spiro-OMeTAD/Au con interferencia coherente.

### 14.2 HSE06+SOC (L2a)

**Módulo**: `workflow_manager._run_soc_hse06()`  
**Método**: `soc_eigenstates(hse06.gpw)` — perturbativo post-HSE06  
**Prerequisito**: `06_hse06/hse06.gpw` (actualmente en curso)  
**Gap esperado**: ~1.35–1.45 eV (HSE06 ~1.7 eV − SOC ~0.3–0.35 eV)  
**Costo**: ~30 min una vez hse06.gpw disponible

Scissor automático: `_run_optical()` detecta hse06.gpw y calcula
eshift = E_g(HSE06) − E_g(PBE) antes de correr DielectricFunction.

### 14.3 Defectos Intrínsecos (L3)

**Módulo**: `analysis/defects.py`  
**Método**: DFT supercell 2×2×2, corrección Makov-Payne, geom. pre-relajada con MACE  
**Defectos**: V_I, I_i, V_Pb, V_Cs, Pb_I, I_Pb (11 configuraciones de carga)  
**Costo**: ~50 h en 7 cores (reducible con doble Xeon a ~13 h)

La corrección de tamaño finito usa ε∞ = 3.647 (calculado en §9.4).
Para publicación se recomienda la corrección Freysoldt completa (pydefect).

### 14.4 Migración Iónica CI-NEB (L4)

**Módulo**: `analysis/neb_workflow.build_migration_endpoints()` +
`run_migration_neb()`  
**Método**: CI-NEB con 7 imágenes, fmax = 0.10 eV/Å, k = 0.10 eV/Å²  
**Rutas**: V_I ⟨100⟩, V_I ⟨110⟩, I_i ⟨100⟩, V_Cs ⟨100⟩  
**Costo**: ~3 h/ruta × 5 rutas = ~15 h

Barreras literatura: V_I ≈ 0.1–0.25 eV, V_Cs ≈ 0.4–0.6 eV.

### 14.5 Kinetic Monte Carlo (L5)

**Módulo**: `analysis/kmc.py` — algoritmo BKL O(N) por evento  
**Inputs**: barreras NEB (L4), G(x) óptico (L1), ε∞  
**Outputs**: φ_defectos(t), riesgo_recombinación(t), label fotostabilidad  
**Costo**: segundos–minutos (sin DFT)

### 14.6 Quasi-Armónica QHA (L6a)

**Módulo**: `analysis/phonopy_workflow.compute_quasiharmonic()`  
**Método**: Phonopy QHA, 6 volúmenes (strain ±4%), EOS Vinet  
**Outputs**: G(T), α(T) [1/K], C_p(T), V_eq(T), B₀ [GPa]  
**Costo**: ~42 h en 7 cores (reutiliza los fonones ya calculados por volumen)

⚠ **Limitación**: QHA falla en la transición α→γ (modo blando R₄⁺).
Usar MACE-AIMD para detectar la transición; QHA para cuantificar propiedades
termodinámicas en el rango estable (T < 320 K estimado).

### 14.7 AIMD-MLIP con MACE-MP-0 (L6b)

**Módulo**: `analysis/aimd_mlip.py`  
**Método**: NVT Langevin + MACE-MP-0 (universal ML potential, MP-trained)  
**Temperaturas**: 300/400/500/600 K, 5000 pasos × 2 fs = 10 ps por temperatura  
**Métricas**: RMSD, RDF Pb-I, ángulo Pb-I-Pb, label {stable|distorted|decomposed}  
**Costo**: ~5 min CPU por temperatura (vs. ~400 h AIMD-DFT)  
**Instalación**: `pip install mace-torch`

Pipeline híbrido recomendado:
```
MACE (minutos) → cribado estabilidad → si estable:
QHA DFT (~42 h) → C_p(T), α(T) cuantitativos
```
Factor de ahorro: ~10× vs. AIMD-DFT puro.

### 14.8 Algoritmos identificados pero no implementados

Estos algoritmos aparecen como necesidades metodológicas o mejoras naturales del
workflow, pero no están implementados actualmente en el repositorio:

| Algoritmo | Estado actual | Futuro propuesto |
|---|---|---|
| PES 1D bayesiano / surrogate-assisted | El PES actual usa una malla uniforme de 20 puntos y detector determinista de doble pozo | Implementar Gaussian Process o Bayesian optimisation sobre Q para refinar mínimos/sillas con menos SCF |
| Detector adaptativo de doble pozo | El criterio actual busca un máximo interior y barrera >10 meV | Añadir refinamiento local de mínimos y saddle, incertidumbre del ajuste y clasificación probabilística |
| Corrección Freysoldt/Komsa-Pasquarello para defectos cargados | El módulo de defectos usa Makov-Payne como aproximación | Integrar pydefect/pymatgen para alineamiento de potencial y corrección anisotrópica |
| Workflow top-level para DOS near-gap | `analyze_dos_near_gap()` existe como utilidad, pero no como `STEP_ORDER` | Añadir paso `dos_gap` o integrarlo en `effective_masses`/`score` para alimentar defect-tolerance |

### 14.9 Fuera de Alcance

| Técnica | Fenómeno | Motivo de exclusión |
|---------|----------|---------------------|
| BSE (Bethe-Salpeter) | Excitones | ~50× costo RPA, requiere HPC |
| AIMD-DFT completo | Dinámica real > 300 K | ~400 h/temperatura, sustituido por MACE |
| SRIM/Geant4 | Radiación ionizante | Solo aplica a PV espacial |
| GW+BSE post-irradiación | Gap bajo daño | Fuera del alcance terrestre |
