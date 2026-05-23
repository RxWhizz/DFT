# 01 — Inventario completo: API GPAW/ASE en uso

Generado por audit exhaustivo 2026-05-20. Cubre todos los `.py` del proyecto.

---

## Archivos fuente auditados

| Archivo | Rol principal |
|---------|---------------|
| `src/dft_cspbi3/calculator_factory.py` | Factory de calculadoras GPAW desde YAML |
| `src/dft_cspbi3/workflow_manager.py` | Orquesta todos los pasos DFT (1734 líneas) |
| `src/dft_cspbi3/convergence.py` | Tests de convergencia ecut/kpoints |
| `src/dft_cspbi3/postprocessing.py` | Extracción de propiedades desde .gpw |
| `src/dft_cspbi3/analysis/electronic.py` | Análisis electrónico (bandas, DOS) |
| `src/dft_cspbi3/analysis/optical.py` | Espectro óptico (DielectricFunction) |
| `src/dft_cspbi3/validation/phonons.py` | Fonones, cargas Born, fase Berry |
| `src/dft_cspbi3/validation/scf.py` | Validación SCF |
| `scripts/preconv_pbe_u.py` | PBE+U preconvergencia para Sn |
| `scripts/generate_visualizations.py` | Gráficas DOS/bandas |
| `run_hse06_nsc_dos.py` | HSE06 non-SCF + DOS |
| `main.py` | CLI entry point |

---

## GPAW imports por símbolo y riesgo

| Símbolo | Archivos | Riesgo master |
|---------|---------|---------------|
| `from gpaw import GPAW` | todos los archivos | **Bajo** |
| `from gpaw import Mixer, PW` | calculator_factory, workflow_manager | **Bajo** |
| `from gpaw.mixer import MixerSum` | calculator_factory (_hse06), workflow_manager | **Bajo** (verificar) |
| `from gpaw.mixer import BroydenMixer` | calculator_factory (_r2scan), workflow_manager | **Bajo** |
| `from gpaw.eigensolvers import Davidson` | calculator_factory, preconv_pbe_u | **Bajo** |
| `from gpaw.spinorbit import soc_eigenstates` | workflow_manager (6 métodos), postprocessing | **Medio** — verificar firma |
| `from gpaw.hybrids.eigenvalues import non_self_consistent_eigenvalues` | workflow_manager (~822), run_hse06_nsc_dos | **Alto** — puede moverse en master |
| `from gpaw.dos import DOSCalculator` | analysis/electronic, scripts/generate_visualizations | **Medio** |
| `from gpaw.response.df import DielectricFunction` | analysis/optical | **Medio** |
| `from gpaw.borncharges import displace_atom, _all_disp, born_charges` | validation/phonons | **Alto** — `_all_disp` es API privada |
| `from gpaw.berryphase import polarization_phase` | validation/phonons | **Medio** |
| `from gpaw.external import static_polarizability` | validation/phonons | **Medio** |
| `from gpaw.mpi import world` | workflow_manager, run_hse06_nsc_dos | **Bajo** |
| `import gpaw` (dinámico) | calculator_factory `_gpaw_symbols()` | **Bajo** — ya tiene fallback |

---

## GPAW constructor kwargs (inventario exhaustivo)

| Kwarg | Valores usados | Pasos |
|-------|---------------|-------|
| `mode` | `PW(450)` | todos |
| `xc` | `"PBEsol"`, `"PBE"`, `"SCAN"`, `"MGGA_X_R2SCAN+MGGA_C_R2SCAN"`, `{"name":"HSE06","omega":0.11}` | según paso |
| `kpts` | `{"size":[n,n,n],"gamma":True}` o bandpath object | todos |
| `fixdensity` | `True` | bands, r2scan_bands |
| `symmetry` | `"on"`, `"off"`, `{"point_group":True,"time_reversal":True}` | varios |
| `convergence` | `{energy, forces, eigenstates, density, bands}` | todos |
| `occupations` | `{"name":"fermi-dirac","width":0.05}` / `width:0.01` (HSE06) | todos |
| `mixer` | `Mixer(beta,nmaxold,weight)` / `MixerSum(...)` / `dict{backend,beta,nmaxold}` | todos |
| `eigensolver` | `Davidson(niter=4)` ✓ / `{"name":"dav","niter":3}` ← BUG en HSE06 (ya corregido) | r2scan, hse06 |
| `parallel` | `{"domain":1}`, `{"domain":(1,1,1)}` | todos |
| `setups` | `{element:dataset}` / `{element:":orbital,U"}` (Dudarev) | todos |
| `txt` | filepath string | todos |
| `maxiter` | 333 | relax |
| `nbands` | int | hse06 |

---

## Métodos GPAW calculator usados

| Método | Archivos | Estabilidad |
|--------|---------|-------------|
| `calc.get_atoms()` | múltiples | Estable |
| `calc.get_potential_energy()` | múltiples | Estable |
| `calc.get_fermi_level()` | múltiples | Estable |
| `calc.get_number_of_electrons()` | workflow_manager, run_hse06 | Estable |
| `calc.get_number_of_bands()` | analysis/electronic | Estable |
| `calc.get_bz_k_points()` | analysis/electronic | Estable |
| `calc.get_ibz_k_points()` | workflow_manager `_save_r2scan_bandgap` | Medio |
| `calc.get_eigenvalues(kpt=i, spin=0)` | múltiples | Estable |
| `calc.get_homo_lumo()` | postprocessing | Estable |
| `calc.band_structure()` | workflow_manager, postprocessing, scripts | Estable |
| `calc.write(file)` / `calc.write(file, mode="all")` | múltiples | Estable |
| `calc.attach(func, interval, *args)` | workflow_manager (HSE06 checkpoint) | Medio |
| `calc.__del__()` explícito | workflow_manager ~311 | Bajo riesgo |

---

## Accesos internos GPAW (frágiles)

| Patrón | Ubicación | Riesgo | Descripción |
|--------|-----------|--------|-------------|
| `calc.hamiltonian.xc = _XC("PBE")` + restauración en finally | `_run_soc_scan()` ~474, `_run_soc_r2scan()` ~597 | **Crítico** | Proxy PBE para augmentación PAW en SOC de MGGA |
| `calc.wfs.kd.nibzkpts`, `.weight_k` | `run_hse06_nsc_dos.py` ~146 | **Alto** | Descriptor k-points interno |
| `gpaw.borncharges._all_disp` | `validation/phonons.py` ~197 | **Alto** | API privada (underscore) |
| eigenvalue `[:, nval-1]` indexing | `workflow_manager` ~437, ~491 | **Medio** | Depende de shape del array |

---

## ASE imports y uso

| Símbolo | Uso | Estabilidad |
|---------|-----|-------------|
| `from ase.optimize import BFGS` | relax, relax_sym | Estable |
| `from ase.constraints import FixSymmetry` | relax_sym | Estable |
| `from ase.phonons import Phonons` | validation/phonons | Estable |
| `from ase.dft.dos import DOS` | postprocessing | Estable |
| `from ase.dft.bandgap import bandgap` | workflow_manager (scan, r2scan) | Estable |
| `from ase.io import read, write` | múltiples | Estable |
| `atoms.cell.bandpath(path, npoints)` | calculator_factory, workflow_manager | Estable |
| `atoms.set_constraint(FixSymmetry(...))` | workflow_manager | Estable |

---

## Dependencias declaradas (pyproject.toml)

| Paquete | Versión mínima | Notas |
|---------|---------------|-------|
| GPAW | ≥24.1.0 | Migrar a master |
| ASE | ≥3.23.0 | Actual: 3.24 ✓ |
| NumPy | ≥1.26 | |
| phonopy | ≥2.20 | |
| spglib | ≥2.0 | |
| libxc | sistema | Necesita ≥5.1 para r²SCAN |

---

## .gpw completados (no deben regresionar)

**Alpha CsPbI3:** relax, scf, bands, dos (×3), hse06, r2scan, scan, formation, effmass  
**Top8 PBE (8 materiales):** relax, scf, bands, dos, effmass (~40 .gpw)  
**Top8 R2SCAN Pb-based (MAPbI3, FAPbI3, CsPbI3, FAPbBr3):** relax_sym, r2scan, effmass  
**Top8 R2SCAN Sn-based:** solo preconv parcial (bloqueados por oscilación Pulay en 25.7.0)  

**Total: ~75 .gpw** que deben ser legibles en master (formato ULM estable).

---

## Tests existentes

| Archivo | Qué cubre |
|---------|-----------|
| `tests/test_calculator_factory.py` | Creación de calculadoras GPAW |
| `tests/test_validation_new.py` | Lógica de validación |
| `tests/test_top8.py` | Set de 8 materiales |
| `tests/test_bandgap_correction.py` | Corrección de bandgap |
| `tests/test_oghma_device.py` | Simulación dispositivo OGHMA |
| `tests/test_structure_builder.py` | Carga y construcción de estructuras |
| `tests/test_postprocessing.py` | Postprocesamiento (bandas, DOS, masas) |
| `tests/test_migration.py` | **NUEVO** — imports GPAW master, MSR1, Davidson, GPW compat |
