# α-CsPbI₃ DFT Results Report

_Generated: 2026-04-29 17:43_  
_Method: GPAW · PBE-PW · PAW · Phonopy_

## Calculation Status
| Step | Status |
|---|---|
| 01 Relax | ✓ |
| 02 SCF | ✓ |
| 03 Bands | ✓ |
| 04 DOS | ✓ |
| 05 SOC | ✓ |
| 05 HSE06+SOC | pending |
| 06 HSE06 | pending |
| 07 Hessian | ✓ |
| 07 Phonons (disp 0) | ✓ |
| 07 Phonons (disp 1) | ✓ |
| 07 Phonons (disp 2) | ✓ |
| 07 Phonons (dispersion) | ✓ |
| 07 PES | ✓ |
| 08 LOTO | ✓ |
| 09 Formation energy | ✓ |
| 10 Effective masses | ✓ |
| 11 Optical | pending |
| 11 Device optics | pending |
| 13 Defects | pending |
| 14 Migration NEB | pending |
| 15 kMC | pending |
| 15 QHA | pending |
| 16 AIMD-MLIP | pending |

## Structure
| Parameter | Value |
|---|---|
| Formula | CsPbI₃ (α-phase, Pm-3m) |
| Lattice constant a | 6.1800 Å |
| Volume | 236.029 Å³ |
| Atoms in cell | 5 (Cs×1, Pb×1, I×3) |
| d(Cs-I) | 4.3699 Å |
| d(Cs-Pb) | 5.3520 Å |
| d(I-I) | 4.3699 Å |
| d(I-Pb) | 3.0900 Å |

## Electronic Structure
### SCF (PBE)
| Quantity | Value |
|---|---|
| Total energy | -14.053696 eV |
| Fermi level | 3.6576 eV |
| Valence electrons | 44 |
| k-points (BZ) | 216 |
| Bands | 26 |

### Band Structure (PBE)
| Quantity | Value |
|---|---|
| VBM (rel. Eᶠ) | -0.4738 eV |
| CBM (rel. Eᶠ) | +0.6153 eV |
| Band gap (PBE) | **1.0891 eV** |
| Gap type | Direct (R-point) |
| k-points on path | 40 |

### Spin-Orbit Coupling (perturbative, PBE+SOC)
| Quantity | Value |
|---|---|
| Band gap (PBE+SOC) | **0.2999 eV** |
| SOC gap correction | -0.7892 eV |
| SOC bands | 52 (2× original) |
| k-points | 216 |
| Spin projection shape | (216, 52, 3) |

### HSE06 Hybrid Functional
_Status: pending — hse06.gpw not yet generated_

## Effective Masses and Structural Metrics
| Quantity | Value |
|---|---|
| Gap type | direct |
| Gap | 1.0891 eV |
| Direct gap | 1.0891 eV |
| VBM k-point | [0.5, 0.5, 0.5] |
| CBM k-point | [0.5, 0.5, 0.5] |
| Electron effective mass | 1.346 m₀ |
| Hole effective mass | 1.203 m₀ |
| Reduced mass | 0.635 m₀ |
| Goldschmidt tolerance factor t | 0.822 |
| Octahedral factor μ | 0.541 |
| Mean Pb-I bond | 3.0900 Å |
| Pb-I bond variance | 0.0000e+00 Å² |
| Flags | none |

## Vibrational Properties
### Γ-Point Hessian (finite-displacement, ASE)
| Quantity | Value |
|---|---|
| Modes at Γ | 15 (3N, N=5) |
| Imaginary modes (< −10 cm⁻¹) | 0 |
| Acoustic range | 5.5 – 14.4 cm⁻¹ |
| Optical range | 16.9 – 106.3 cm⁻¹ |

**All Γ-point frequencies (cm⁻¹):**

| Mode | Freq (cm⁻¹) | Character |
|---|---|---|
|  1 |     5.47 | acoustic |
|  2 |    10.53 | acoustic |
|  3 |    14.41 | acoustic |
|  4 |    16.90 | optical |
|  5 |    17.30 | optical |
|  6 |    18.19 | optical |
|  7 |    19.18 | optical |
|  8 |    21.23 | optical |
|  9 |    22.53 | optical |
| 10 |    23.75 | optical |
| 11 |    25.03 | optical |
| 12 |    25.70 | optical |
| 13 |   105.39 | optical |
| 14 |   106.03 | optical |
| 15 |   106.28 | optical |

### Phonopy Force Sets (Δ = 0.02 Å, 2×2×2 supercell)
| Displacements computed | 3 / 3 |

| Disp | Atom | Max\|F\| (eV/Å) | Mean\|F\| (eV/Å) | ASR residual | ASR (%) |
|---|---|---|---|---|---|
| 0 | atom 1  [0.02, 0.0, 0.0] | 0.00539 | 0.00045 | 9.00e-06 | 0.167% |
| 1 | atom 9  [0.02, 0.0, 0.0] | 0.08778 | 0.00195 | 5.16e-04 | 0.587% |
| 2 | atom 17  [0.014142135623731, 0.014142135623731, 0.0] | 0.07911 | 0.00171 | 2.07e-04 | 0.262% |

### Phonon Dispersion (Phonopy + ASR)
| Quantity | Value |
|---|---|
| q-points on path | 60 |
| Branches | 15 |
| Min frequency | -29.89 cm⁻¹ |
| Max frequency | 133.55 cm⁻¹ |
| Imaginary modes (< −10 cm⁻¹) | 84 |
| Stability | ⚠ 84 imaginary mode(s), worst: -29.9 cm⁻¹ |

## Quasi-Zero/Negative-Mode PES Scan
| Quantity | Value |
|---|---|
| Points computed | 20 (20 cached SCF energies) |
| Q range | -0.500 to +0.500 Å |
| Minimum E(Q)-E(0) | 0.000048 eV at Q = -0.026 Å |
| Maximum E(Q)-E(0) | 0.020414 eV at Q = -0.500 Å |
| Energy span | 20.37 meV |
| Double well detected | no |
| Barrier for criterion | 0.0 meV |
| CI-NEB | not launched (no double well) |
| Plot | `calculations/alpha/07_vibrational/pes/pes_scan.png` |

## LO-TO Correction (Born Charges + ε∞)
### Dielectric Tensor (ε∞)

| | x | y | z |
|---|---|---|---|
| x | 3.6472 | 0.0000 | 0.0000 |
| y | -0.0000 | 3.6472 | -0.0000 |
| z | -0.0000 | -0.0000 | 3.6472 |

Isotropic average: ε∞ = 3.6472

### Born Effective Charges Z* (diagonal elements)

| Atom | Z*_xx | Z*_yy | Z*_zz | Mean |Z*| |
|---|---|---|---|---|
| Cs1 | +1.3697 | +1.3699 | +1.3698 | 0.4568 |
| Pb2 | +4.9781 | +4.9794 | +4.9793 | 1.6597 |
| I3 | -0.7494 | -4.8497 | -0.7498 | 0.7058 |
| I4 | -4.8487 | -0.7499 | -0.7497 | 0.7057 |
| I5 | -0.7497 | -0.7497 | -4.8496 | 0.7057 |

Born charge ASR (Σ Z* → 0), max element: 0.0000 e
(ASR satisfied ✓)

## Optical Properties
_Status: pending — optical step not yet run_

## Device Optics (Beer-Lambert)
_Status: pending — optical step not yet run_

## HSE06 + Spin-Orbit Coupling
_Status: pending — hse06.gpw not yet generated_

## Formation Energy
| Quantity | Value |
|---|---|
| ΔHf | **-48.897417 eV/f.u.** |
| E(CsPbI₃) | -14.053696 eV/f.u. |
| E(CsI) | 34.069303 eV/f.u. |
| E(PbI₂) | 0.774418 eV/f.u. |
| Stability vs CsI + PbI₂ | stable |
| Summary | ΔHf = -48.897 eV/f.u. → STABLE vs binary decomposition |

## Point Defects (Intrinsic)
_Status: pending — defect calculations not yet run_

**Defects planned**: V_I, I_i, V_Pb, V_Cs, Pb_I, I_Pb (2×2×2 supercell, MACE geometry + DFT single-point)

## Ionic Migration (CI-NEB)
_Status: pending — NEB calculations not yet run_

**Routes planned**: V_I ⟨100⟩, V_I ⟨110⟩, I_i ⟨100⟩, V_Cs ⟨100⟩
Literature: V_I barrier ≈ 0.1–0.25 eV (Azpiroz 2015)

## Kinetic Monte Carlo (Photostability)
_Status: pending — requires NEB barriers (L4) as input_

**Method**: BKL algorithm, O(N) per event
**Inputs**: V_I hop barrier, G(x) photogeneration rate

## Thermal Stability (MACE-AIMD Screening)
_Status: pending — install mace-torch and run screen_thermal_stability()_

**Method**: NVT Langevin + MACE-MP-0, 10 ps/temperature
**Temperatures**: 300/400/500/600 K
**Costo**: ~5 min/T en CPU

## Quasi-Harmonic Approximation (QHA)
_Status: pending — requires phonon force sets at 6 volumes (~42 h)_

**Outputs**: G(T), α(T) thermal expansion, C_p(T), V_eq(T), B₀
**Validity**: T < ~320 K (mode-softening limit for α-phase)
