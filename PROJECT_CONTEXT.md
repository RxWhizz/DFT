# Contexto Proyecto DFT CsPbI₃ GPAW

**Fecha**: 2026-04-24  
**Fase activa**: alpha (Pm-3m, 5 atomos, a₀=6.18 Å)

## Entorno

```text
Python 3.12.3  (.venv en raiz)
GPAW 25.7.0
ASE  3.28.0
LibXC 5.2.3
OpenMPI 4.1.6
Hardware: Intel Xeon 8 cores, ~16 GB RAM
```

Variables por corrida:
```bash
export GPAW_SETUP_PATH=~/.gpaw/gpaw-setups-24.11.0
export GPAW_CONFIG=$(pwd)/siteconfig.py
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
```

Datasets PAW: `~/.gpaw/gpaw-setups-24.11.0/{Cs,Pb,I}.PBE.gz`  
`siteconfig.py`: LibXC + MPI con `compiler = 'mpicc'`

## Alpha: pasos

| Paso | Salida | Estado |
|---|---|---|
| relax | `calculations/alpha/01_relax/relax.gpw` | HECHO |
| scf | `calculations/alpha/02_scf/scf.gpw` | HECHO |
| bands | `calculations/alpha/03_bands/bands.gpw` | HECHO |
| dos | `calculations/alpha/04_dos/dos.gpw` | HECHO |
| soc | `calculations/alpha/05_soc/soc_eigenvalues.npy` | HECHO |
| hessian | `calculations/alpha/07_vibrational/hessian/hessian.npy` | HECHO; 0 modos imaginarios |
| phonons | `calculations/alpha/07_vibrational/phonons/phonon/` | 20/30 hecho; reanudar |

Resultados clave:
- Eg(PBE) = 1.089 eV, directo Γ.
- Eg(PBE+SOC) = 0.300 eV → χSOC = −0.789 eV.
- Hessian: min λ = +0.017 eV/Å² → Γ estable.
- Eg(exp, alpha) = 1.73 eV. Fuente: Sutton et al. ACS Energy Lett. 2018.

## Reanudar phonons

Estado: 20/30 desplazamientos completos. Cache ASE:
`calculations/alpha/07_vibrational/phonons/phonon/`

Antes:
```bash
find calculations/alpha/07_vibrational/phonons/phonon/ -name "*.json" -size 0 -delete
```

Comando:
```bash
cd /home/luis-ochoa/Documents/Vscode/py/dft-cspbi3-gpaw-main
export GPAW_SETUP_PATH=~/.gpaw/gpaw-setups-24.11.0
export GPAW_CONFIG=$(pwd)/siteconfig.py
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
mpirun -n 7 .venv/bin/python3 main.py run --phase alpha --steps phonons --validate --report
```

Costo: ~37 min/desplazamiento con 7 MPI cores. Restan ~10 → ~6 h.

Parametros phonon:
- Supercelda: 2×2×2 (40 atomos).
- k-mesh supercelda: 3×3×3.
- Δ = 0.05 Å, symmetry=off.
- 30 desplazamientos = 5 atomos × 3 direcciones × 2 signos.

## Cambios planeados

1. `src/dft_cspbi3/bandgap_correction.py`
   - Añadir `e_hse_soc`, `delta_additivity`, `mae_vs_hse_soc`.
   - Referencias por fase.
   - `compute_hse_soc_gap(hse_gpw)`.

2. `configs/default_params.yaml`
   - `bandgap_reference` por fase.

3. `src/dft_cspbi3/reporting/validation_report.py`
   - Tabla completa: PBE, PBE+SOC, χSOC, HSE06, χHSE, HSE06+SOC, δ_add, MAE.

4. LO-TO
   - `compute_born_charges(scf_gpw)` en `validation/phonons.py`.
   - `_run_loto(step_dir)` en `workflow_manager.py`.
   - Añadir `loto: 08_loto`.

## Calculos pendientes

| Calculo | Comando | Tiempo | Motivo |
|---|---|---:|---|
| HSE06 alpha | `mpirun -n 7 ... main.py run --phase alpha --steps hse06` | 3-8 h | χHSE propio |
| SOC sobre HSE06 | manual `soc_eigenstates(hse06.gpw)` | ~10 min | δ_add |
| LO-TO alpha | tras `_run_loto` | ~1 h | splitting Γ |
| gamma | `mpirun -n 7 ... main.py run --phase gamma --steps relax scf bands dos soc` | ~2 dias | comparar fase |
| delta | igual | ~3 dias | fase wide-gap |

## Archivos clave

| Archivo | Rol |
|---|---|
| `src/dft_cspbi3/workflow_manager.py` | Orquesta pasos |
| `src/dft_cspbi3/bandgap_correction.py` | Scissor + HSE+SOC |
| `src/dft_cspbi3/calculator_factory.py` | Calculadoras GPAW |
| `src/dft_cspbi3/validation/phonons.py` | Phonons + futuro Born charges |
| `src/dft_cspbi3/reporting/validation_report.py` | Reporte Markdown |
| `configs/default_params.yaml` | Parametros |
| `calculations/alpha/reports/methodology.md` | Metodologia |
| `siteconfig.py` | Build GPAW |
| `main.py` | CLI |

## Bugs conocidos

1. k-mesh supercelda: usar `kpts_sc = [max(1, k // n) for k, n in zip(prim_kpts, supercell)]`.
2. Desplazamientos finitos: `symmetry: "off"`.
3. Cache 0 bytes: borrar antes de reanudar.
4. MPI GPAW: `compiler = 'mpicc'` obligatorio.

## Metodologia

`calculations/alpha/reports/methodology.md` contiene:
- PAW datasets.
- SOC y χSOC.
- Correccion bandgap + presupuesto error.
- Phonon metodologia.
- LO-TO planeado.
- Versiones software.
