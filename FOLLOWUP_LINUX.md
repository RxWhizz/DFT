# Seguimiento Linux: DFT CsPbI₃ GPAW

## Contexto

Pipeline DFT para CsPbI₃ con GPAW+ASE.  
Repo: `dft-cspbi3-gpaw/`  
Versión: `0.2.0`

Codigo desarrollado con mocks en Windows. Objetivo: correr GPAW real en Linux.

## Arquitectura

```text
src/dft_cspbi3/
  structure_builder.py      # alpha, beta, gamma, delta
  calculator_factory.py     # GPAW factory: relax/scf/bands/dos/soc/hse06
  convergence.py            # Ecut + k-mesh
  postprocessing.py         # bandgap, DOS, bandas
  bandgap_correction.py     # Eg_corr = Eg_PBE + χSOC + χHSE
  workflow_manager.py       # relax→scf→bands→soc→hessian→phonons
  validation/
    scf.py
    soc.py
    hessian.py
    phonons.py
    stability.py
  reporting/
    validation_report.py
    vibrational_analysis.py
    methodology.py
    assumptions.py
main.py
```

Parametros default:
- XC: PBEsol.
- Ecut: 450 eV.
- k-SCF: 6×6×6.
- k-DOS: 12×12×12.
- PAW: Cs.9.PBE, Pb.14.PBE, I.7.PBE.
- SOC: perturbativo, `spinorbit_eigenvalues()`.
- Scissor: Eg_corr ≈ 1.52 eV.

## Setup

```bash
gpaw install-data ~/.gpaw/
cd dft-cspbi3-gpaw
pip install -e ".[dev]"
python -c "import dft_cspbi3; print(dft_cspbi3.__version__)"
python -m pytest tests/test_validation_new.py -v
```

## Secuencia pruebas

### 1. Dry-run
```bash
python main.py run --phase alpha --soc --validate --report --dry-run
```

### 2. Relax + SCF
```bash
python main.py run --phase alpha
```

### 3. Pipeline sin fonones
```bash
python main.py run --phase alpha --soc --validate --report
```

### 4. Hessian
```bash
python main.py run --phase alpha --soc --validate --report --steps hessian
```

### 5. Phonons
```bash
python main.py run --phase alpha --soc --validate --report --phonons
```

Gamma/delta: 20 atomos. 2×2×2 → 960 desplazamientos. Empezar con alpha.

## Errores conocidos

| Error | Causa | Fix |
|---|---|---|
| `ModuleNotFoundError: ase.spacegroup` | ASE falta | `pip install ase` |
| `FileNotFoundError: Cs.9.PBE` | PAW falta | `gpaw install-data ~/.gpaw/` |
| `bandpath()` falla | Celda no simetrica | pasar `path='GXMGR'` |
| SCF no converge | Mixer agresivo | `beta=0.02` |
| `KeyError: 'energies'` | `.gpw` distinto | GPAW ≥ 24.1.0 |

## Revisar resultados

SCF:
- `scf_report.converged == True`
- `scf_report.oscillating == False`
- ΔE final < 1e-4 eV

SOC:
- `soc_report.chi_soc` entre −1.5 y 0.0 eV.
- `soc_report.has_splitting == True`

Estabilidad:
- alpha puede tener frecuencias imaginarias a T=0.
- gamma: STABLE o METASTABLE.
- delta: STABLE.

Bandgap:
- PBE sin SOC: ~1.5 eV.
- PBE + SOC: ~0.7 eV.
- Scissor: ~1.52 eV vs exp 1.73 eV.

## Prompt seguimiento

```text
Continuo pipeline DFT para CsPbI₃ con GPAW en Linux.

Proyecto: dft-cspbi3-gpaw/, version 0.2.0.
Codigo probado con mocks. Ahora ejecucion GPAW real.

[Pegar output/error]

Contexto: FOLLOWUP_LINUX.md.
```

## Archivos debug

- `workdir/alpha/01_relax/relax.gpw`
- `workdir/alpha/02_scf/scf.gpw`
- `workdir/alpha/reports/validation_report.md`
- `workdir/alpha/07_vibrational/hessian/`
- `workdir/alpha/07_vibrational/phonons/phonon.*.pckl`
