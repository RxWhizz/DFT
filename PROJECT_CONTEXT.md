# DFT CsPbI₃ GPAW — Project Context & Resume Guide

**Date**: 2026-04-24  
**Phase in progress**: alpha (Pm-3m, 5 atoms, a₀=6.18 Å)

---

## OghmaNano / photovoltaic handoff update - 2026-05-09

The photovoltaic/OghmaNano work now lives under `generador fv/` with a
dedicated Windows venv at `generador fv/.venv`.

Current status:
- OghmaNano runs natively on Windows with `oghma_core.exe` in worker mode.
- The alpha device step has completed once and produced `sim_info.dat`, `jv.csv`,
  optical output, snapshots, plots, and `debug_outputs/DEBUG_REPORT.md`.
- Current parsed metrics after the `.npy` optical rerun with Urbach tail plus
  fine JV sweep: PCE = 13.90685 %, Voc = 0.8953726 V,
  Jsc = -21.9942765 mA/cm2, FF = 0.7061798.
- Current JV settings: Vstart = 0.0 V, Vstop = 1.2 V, Vstep = 0.01 V,
  electrical y mesh = 120 points, optical y mesh = 300 points.
- Current solver iteration caps: maxelectricalitt = 500,
  maxelectricalitt_ramp = 500, max_newton_iterations = 500.
- Jsc from Oghma is treated as A/m2 and converted defensively to mA/cm2.
- Signed PV power is plotted as `P = -V*J` without clipping by current sign;
  it is positive in the photovoltaic quadrant, crosses zero at Voc, and becomes
  negative under forward injection after Voc. The current `jv.csv` has one
  positive power maximum at ~0.68629 V and no secondary positive peak.
- Geometry sanity now passes: `device_stack.json` matches the Oghma template
  stack at 1050 nm total thickness, absorber 250-750 nm, and the generation
  peak is inside the absorber.
- Oghma `sim/snapshots/` are JV-bias snapshots, not time transients; plots and
  reports should treat their x-axis as snapshot/bias index.
- The required optical `.npy` files now exist in `calculations/alpha/11_optical/`.
  They were generated from the completed RPA `dielectric_function.csv`, deriving
  n/k from sqrt(epsilon), alpha from `4*pi*k/lambda`, and applying a smooth
  Urbach sub-gap tail below Eg = 1.5858 eV with Eu = 25 meV before exporting
  device arrays. The hard sub-gap alpha=0 cutoff is no longer used.

Key files for this branch of work:
- `generador fv/src/dft_cspbi3/analysis/oghma_device.py`
- `generador fv/scripts/debug_oghma_outputs.py`
- `generador fv/tests/test_oghma_device.py`
- `generador fv/calculations/alpha/14_oghma_device/debug_outputs/DEBUG_REPORT.md`
- `generador fv/OGHMA_DEBUG_CONTEXT.md`

---

## Environment

```
Python 3.12.3  (.venv at project root)
GPAW 25.7.0
ASE  3.28.0
LibXC 5.2.3
OpenMPI 4.1.6
Hardware: 8-core Intel Xeon (shared-memory), ~16 GB RAM
```

Environment variables needed for every run:
```bash
export GPAW_SETUP_PATH=~/.gpaw/gpaw-setups-24.11.0
export GPAW_CONFIG=$(pwd)/siteconfig.py
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
```

PAW datasets: `~/.gpaw/gpaw-setups-24.11.0/{Cs,Pb,I}.PBE.gz`  
siteconfig.py: LibXC + MPI with `compiler = 'mpicc'`

---

## Completed steps — alpha

| Step | Output | Status |
|---|---|---|
| relax | `calculations/alpha/01_relax/relax.gpw` | DONE |
| scf | `calculations/alpha/02_scf/scf.gpw` | DONE |
| bands | `calculations/alpha/03_bands/bands.gpw` | DONE |
| dos | `calculations/alpha/04_dos/dos.gpw` | DONE |
| soc | `calculations/alpha/05_soc/soc_eigenvalues.npy` | DONE |
| hessian | `calculations/alpha/07_vibrational/hessian/hessian.npy` | DONE — 0 imaginary modes |
| **phonons** | `calculations/alpha/07_vibrational/phonons/phonon/` | **20/30 done — RESUME NEEDED** |

Key results:
- Eg(PBE) = 1.089 eV (direct, Γ)
- Eg(PBE+SOC) = 0.300 eV → χSOC = −0.789 eV
- Hessian: min λ = +0.017 eV/Å², all positive → Γ-stable
- Eg(exp, alpha) = 1.73 eV (Sutton et al. ACS Energy Lett. 2018)

---

## Phonons: resume procedure

**State**: 20/30 displacements done (atoms 0–3 partial). ASE cache in:  
`calculations/alpha/07_vibrational/phonons/phonon/`

**IMPORTANT**: Before relaunching, always check for 0-byte JSON files and delete them:
```bash
find calculations/alpha/07_vibrational/phonons/phonon/ -name "*.json" -size 0 -delete
```

**Resume command** (from project root):
```bash
cd /home/luis-ochoa/Documents/Vscode/py/dft-cspbi3-gpaw-main
export GPAW_SETUP_PATH=~/.gpaw/gpaw-setups-24.11.0
export GPAW_CONFIG=$(pwd)/siteconfig.py
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
mpirun -n 7 .venv/bin/python3 main.py run --phase alpha --steps phonons --validate --report
```

Each of the remaining ~10 displacements takes ~37 min with 7 MPI cores.  
ETA to complete: ~6 hours from cold start.

Phonon parameters:
- Supercell: 2×2×2 (40 atoms)
- k-mesh supercell: 3×3×3 (scaled from 6×6×6 primitive)
- Δ = 0.05 Å, symmetry=off
- 30 total displacements = 5 atoms × 3 directions × 2 signs (±)

---

## Pending code changes (from approved plan)

### Step 2 — `src/dft_cspbi3/bandgap_correction.py`

Add to `ScissorResult` dataclass:
```python
e_hse_soc: Optional[float] = None
delta_additivity: Optional[float] = None   # e_hse_soc − e_corrected
mae_vs_hse_soc: Optional[float] = None
chi_soc_source: str = "computed"           # "computed" | "literature"
chi_hse_source: str = "literature"
k_mesh_hse: Optional[list] = None
```

Replace flat `REFERENCE` dict with per-phase nested structure:
```python
REFERENCE = {
    "alpha": {
        "experimental": 1.73,
        "exp_reference": "Sutton et al. ACS Energy Lett. 2018",
        "pbe_no_soc": 1.089,   # this work
        "pbe_soc": 0.300,      # this work
        "chi_soc_this_work": -0.789,
    },
    "gamma": {
        "experimental": 1.68,
        "exp_reference": "Steele et al. JACS 2019",
    },
    "delta": {
        "experimental": 2.82,
        "exp_reference": "Sutton et al. ACS Energy Lett. 2018",
    },
}
```

Add method `compute_hse_soc_gap(hse_gpw)` that calls `get_soc_bandgap(hse_gpw)` and populates `delta_additivity = e_hse_soc - e_corrected`.

### Step 3 — `configs/default_params.yaml`

Replace flat `bandgap_reference` section with:
```yaml
bandgap_reference:
  alpha:
    experimental: 1.73
    exp_reference: "Sutton et al. ACS Energy Lett. 2018"
    pbe_no_soc: 1.089
    pbe_soc: 0.300
    chi_soc_this_work: -0.789
  gamma:
    experimental: 1.68
    exp_reference: "Steele et al. JACS 2019"
  delta:
    experimental: 2.82
    exp_reference: "Sutton et al. ACS Energy Lett. 2018"
```

### Step 4 — `src/dft_cspbi3/reporting/validation_report.py`

Section 5 (band gap) must show full table:
- Eg(PBE), Eg(PBE+SOC), χSOC (source)
- Eg(HSE06) if available, χHSE (source)
- Eg(HSE06+SOC) if available ← primary result
- δ_add (additivity error) if both PBE+scissor and HSE06+SOC present
- MAE vs experiment + reference
- Flag ⚠️ if HSE06 not yet done

### Step 5 — LO-TO splitting

New files/changes needed:

**`src/dft_cspbi3/validation/phonons.py`**: add `compute_born_charges(scf_gpw)` using GPAW Berry-phase (finite electric field in 3 directions × 2 signs = 6 SCF calls). Returns `(Z_born: ndarray shape (N,3,3), eps_inf: ndarray shape (3,3))`. Save as `born_charges.npy` + `dielectric_tensor.npy`.

**`src/dft_cspbi3/workflow_manager.py`**: add `_run_loto(step_dir)` that calls `compute_born_charges(scf_gpw)` then re-runs phonon band structure with Gonze-Lee correction: `ph.set_born_charges(Z_av, epsN)` before `ph.get_band_structure()`.

**`STEP_ORDER` and `STEP_DIRS`** in workflow_manager.py: add `"loto": "08_loto"`.

Estimated cost: ~30–60 min for alpha (6 SCF on primitive cell).

---

## Planned calculations still to run

| Calculation | Command | Est. time | Purpose |
|---|---|---|---|
| HSE06 (alpha) | `mpirun -n 7 ... main.py run --phase alpha --steps hse06` | 3–8 h | Eg(HSE06) for χHSE this-work |
| SOC on HSE06 | manual `soc_eigenstates(hse06.gpw)` | ~10 min | δ_add = Eg(HSE06+SOC) − Eg(PBE+scissor) |
| LO-TO (alpha) | after `_run_loto` implemented | ~1 h | LO-TO splitting for Γ-point phonons |
| gamma phase | `mpirun -n 7 ... main.py run --phase gamma --steps relax scf bands dos soc` | ~2 days | phase comparison |
| delta phase | same | ~3 days | wide-gap phase, δ comparison |

---

## Key files

| File | Role |
|---|---|
| `src/dft_cspbi3/workflow_manager.py` | Orchestrates all steps |
| `src/dft_cspbi3/bandgap_correction.py` | Scissor + HSE+SOC corrections |
| `src/dft_cspbi3/calculator_factory.py` | GPAW calculator creation |
| `src/dft_cspbi3/validation/phonons.py` | `compute_phonons()` and future `compute_born_charges()` |
| `src/dft_cspbi3/reporting/validation_report.py` | Markdown report generation |
| `configs/default_params.yaml` | All calculation parameters |
| `calculations/alpha/reports/methodology.md` | Scientific methodology document |
| `siteconfig.py` | GPAW build config (LibXC + MPI) |
| `main.py` | CLI entry point |

---

## Known issues / bugs fixed

1. **k-mesh on supercell**: Fixed in `_run_phonons()` — scale inversely: `kpts_sc = [max(1, k // n) for k, n in zip(prim_kpts, supercell)]`
2. **symmetry=off required**: All finite-displacement calculations (hessian, phonons) must use `symmetry: "off"` in params_override. Crystal symmetry is broken by atomic displacements.
3. **0-byte cache files after crash**: Always `find ... -size 0 -delete` before resuming ASE Phonons.
4. **siteconfig.py MPI**: Must have explicit `compiler = 'mpicc'` — setting only `mpi = True` raises ValueError at GPAW build time.

---

## Methodology document

`calculations/alpha/reports/methodology.md` — completed sections:
- Sec 3: PAW datasets (filenames, frozen cores, scalar-relativistic)
- Sec 7: SOC via `soc_eigenstates()`, χSOC = −0.789 eV
- Sec 8 (8.0–8.7): full band gap correction rewrite with error budget (0.15–0.35 eV), method comparison table, use-case classification
- Sec 9.2: phonon methodology with k-mesh rationale, known limitations
- Sec 9.3: LO-TO splitting — planned, not yet computed
- Sec 10: exact software versions
