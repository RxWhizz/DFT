# Followup: DFT CsPbI₃ GPAW — Testing en Linux

## Contexto del proyecto

Pipeline DFT completo para CsPbI₃ (halide perovskite) con GPAW+ASE.
Directorio del proyecto: `dft-cspbi3-gpaw/`
Versión actual: `0.2.0`

El código fue desarrollado y testeado con mocks en Windows (58/58 unit tests passing).
Esta sesión es para correr el pipeline real con GPAW en Linux.

---

## Arquitectura del paquete

```
src/dft_cspbi3/
  structure_builder.py      # alpha (Pm-3m, 5at), gamma/delta (Pnma, 20at)
  calculator_factory.py     # GPAW calc factory (relax/scf/bands/dos/soc/hse06)
  convergence.py            # Ecut + k-mesh convergence → DataFrames
  postprocessing.py         # bandgap, DOS, band structure desde .gpw
  bandgap_correction.py     # Eg_corr = Eg_PBE + χSOC + χHSE
  workflow_manager.py       # DFTWorkflow: relax→scf→bands→soc→hessian→phonons
  validation/
    scf.py        # SCFReport — parsea output GPAW, verifica convergencia
    soc.py        # SOCReport — valida χSOC plausibilidad, splitting
    hessian.py    # HessianResult — H_ij finite-diff, eigenvalues, .npy cache
    phonons.py    # PhononResult — ASE Phonons supercell, cm⁻¹, imaginary detect
    stability.py  # StabilityClass (STABLE/METASTABLE/UNSTABLE)
  reporting/
    validation_report.py    # → validation_report.md
    vibrational_analysis.py # → vibrational_analysis.md
    methodology.py          # → methodology.md
    assumptions.py          # → assumptions.md
main.py  # CLI Click: run / status / report
```

**Parámetros por defecto** (`configs/default_params.yaml`):
- XC: PBEsol, Ecut: 450 eV, k-SCF: 6×6×6, k-DOS: 12×12×12
- PAW: Cs.9.PBE, Pb.14.PBE (semicore 5d — necesario para SOC), I.7.PBE
- SOC: perturbativo via `spinorbit_eigenvalues()`, χSOC ≈ −0.84 eV
- Scissor: Eg_corr ≈ 1.52 eV (exp: 1.73 eV)

---

## Setup inicial (hacer solo una vez)

```bash
# Instalar PAW datasets
gpaw install-data ~/.gpaw/

# Instalar el paquete en modo editable
cd dft-cspbi3-gpaw
pip install -e ".[dev]"

# Verificar imports
python -c "import dft_cspbi3; print(dft_cspbi3.__version__)"

# Correr unit tests (no necesitan GPAW real)
python -m pytest tests/test_validation_new.py -v
```

---

## Secuencia de testing (de barato a caro)

### Paso 1 — Dry-run (no ejecuta GPAW)
```bash
python main.py run --phase alpha --soc --validate --report --dry-run
```
Verifica que el CLI parsea bien los parámetros y encuentra los archivos.

### Paso 2 — Solo relax + SCF (más barato, ~10–30 min)
```bash
python main.py run --phase alpha
```
Genera `workdir/alpha/01_relax/` y `02_scf/` con checkpoints `.gpw`.

### Paso 3 — Pipeline completo sin fonones (~30–60 min)
```bash
python main.py run --phase alpha --soc --validate --report
```
Genera los 4 reportes Markdown en `workdir/alpha/reports/`.

### Paso 4 — Con Hessian (30 calls GPAW para alpha, ~30 min extra)
```bash
python main.py run --phase alpha --soc --validate --report --steps hessian
```

### Paso 5 — Con fonones (solo si el tiempo lo permite — supercell 2×2×2)
```bash
python main.py run --phase alpha --soc --validate --report --phonons
```
**Advertencia**: para gamma/delta (20 átomos), supercell 2×2×2 = 960 desplazamientos. Empieza siempre con alpha.

---

## Errores conocidos y sus fixes

| Error | Causa | Fix |
|-------|-------|-----|
| `ModuleNotFoundError: ase.spacegroup` | ASE no instalado | `pip install ase` |
| `FileNotFoundError: Cs.9.PBE` | PAW datasets no instalados | `gpaw install-data ~/.gpaw/` |
| `bandpath()` falla | Celda no perfectamente simétrica | Pasar `path='GXMGR'` en `compute_phonons` |
| SCF no converge | Mixer muy agresivo | Bajar `beta` en `calculator_factory.py` a 0.02 |
| `KeyError: 'energies'` en band structure | Formato `.gpw` distinto | Verificar versión GPAW ≥ 24.1.0 |

---

## Qué revisar en los resultados

### SCF convergente
- `scf_report.converged == True`
- `scf_report.oscillating == False`
- Energy change final < 1e-4 eV

### SOC plausible
- `soc_report.chi_soc` entre −1.5 y 0.0 eV (típico: −0.84 eV para CsPbI₃)
- `soc_report.has_splitting == True`

### Estabilidad dinámica (alpha es metaestable a T=0)
- Se esperan frecuencias imaginarias en alpha (fase de alta temperatura)
- gamma debe salir STABLE o METASTABLE
- delta debe salir STABLE

### Band gap esperado
- PBE sin SOC: ~1.5 eV
- PBE + SOC: ~0.7 eV
- Corregido (scissor): ~1.52 eV vs experimental 1.73 eV

---

## Prompt para Claude en la sesión de followup

```
Estoy continuando el desarrollo del pipeline DFT para CsPbI₃ con GPAW en Linux.

El proyecto está en dft-cspbi3-gpaw/, versión 0.2.0. El código fue desarrollado
en Windows con tests mock (58/58 passing). Esta es la primera ejecución con GPAW real.

[Pega aquí el output del error o el resultado que quieres discutir]

El contexto completo del proyecto está en FOLLOWUP_LINUX.md en la raíz del proyecto.
```

---

## Archivos clave para debug

- `workdir/alpha/01_relax/relax.gpw` — checkpoint relax
- `workdir/alpha/02_scf/scf.gpw` — checkpoint SCF
- `workdir/alpha/reports/validation_report.md` — reporte principal
- `workdir/alpha/07_vibrational/hessian/` — .npy caches del Hessian
- `workdir/alpha/07_vibrational/phonons/phonon.*.pckl` — cache ASE Phonons
