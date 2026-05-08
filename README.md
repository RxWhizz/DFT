# dft-cspbi3-gpaw

Automated DFT simulation package for CsPbI₃ halide perovskite polymorphs (α, γ, δ)
using **GPAW** as the DFT backend and **ASE** for structure manipulation.

## Por qué GPAW sobre VASP

| Aspecto | GPAW | VASP |
|---|---|---|
| Licencia | GPLv3 (open-source) | Comercial (~4 000 €/grupo) |
| Método PAW | Nativo (`gpaw-setups`) | Nativo (`POTCAR`) |
| Integración Python | Directa (objetos ASE, API Python) | Limitada (archivos POSCAR/INCAR) |
| Pseudopotenciales externos | No necesita — datasets propios | Requiere POTCAR compilado |
| SOC | `spinorbit_eigenvalues()` + no-colineal | `LSORBIT = .TRUE.` + `LNONCOLLINEAR` |
| Híbridos | HSE06 vía `xc={'name':'HSE06','omega':0.11}` | `HFSCREEN`, `AEXX` |
| Ondas planas | `mode=PW(450)` | `ENCUT = 450` |
| Workflows Python | Clases nativas, sin wrappers | Requiere pyiron, AiiDA, atomate, etc. |
| Paralelización | MPI + OpenMP nativo | MPI nativo |

## Equivalencias VASP → GPAW

| VASP | GPAW | Notas |
|---|---|---|
| `ENCUT = 450` | `mode=PW(450)` | Ecut en eV — idéntico significado físico |
| `POTCAR` (Cs_sv, Pb_d, I) | `setups={'Cs':'Cs.9.PBE','Pb':'Pb.14.PBE','I':'I.7.PBE'}` | Datasets PAW equivalentes |
| `LSORBIT = .TRUE.` | `spinorbit_eigenvalues(calc)` | SOC perturbativo post-SCF |
| `LNONCOLLINEAR = .TRUE.` | `nspins=4` en GPAW | SOC no-colineal completo |
| `ICHARG = 11` | `GPAW('scf.gpw', fixdensity=True)` | Cálculo non-SCF con densidad fija |
| `IBRION = 2` | `BFGS(atoms)` | Optimización de geometría |
| `EDIFF = 1e-6` | `convergence={'energy': 1e-6}` | Criterio de convergencia SCF |
| `EDIFFG = -0.01` | `fmax=0.01` en BFGS | Criterio de convergencia fuerzas (eV/Å) |
| `ISMEAR = -1; SIGMA = 0.05` | `occupations={'name':'fermi-dirac','width':0.05}` | Ocupaciones térmicas |
| `NSW = 333` | `maxiter=333` | Máximo de pasos SCF |
| `ISYM = 2` | `symmetry='on'` | Uso de simetría |
| `KPOINTS` (Monkhorst-Pack) | `kpts={'size':[6,6,6],'gamma':True}` | Malla k con punto Γ |
| `LORBIT = 11` | `dos.get_dos(atom=i, orbital='p')` | DOS proyectado por orbital |
| `GGA = PS` (PBEsol) | `xc='PBEsol'` | Funcional de intercambio-correlación |
| `HFSCREEN = 0.2` | `xc={'name':'HSE06','omega':0.11}` | ω(Bohr⁻¹) ≈ 0.2 Å⁻¹ |

## Estructura del repositorio

```
dft-cspbi3-gpaw/
├── README.md
├── pyproject.toml
├── requirements.txt
├── configs/
│   └── default_params.yaml          # Parámetros DFT centralizados
├── structures/
│   ├── alpha_cubic.json             # α-Pm̄3m, 5 átomos
│   ├── gamma_ortho.json             # γ-Pnma, 20 átomos
│   └── delta_ortho.json             # δ-Pnma, 20 átomos (fase amarilla)
├── src/
│   └── dft_cspbi3/
│       ├── __init__.py
│       ├── structure_builder.py     # crystal() ASE para las 3 fases
│       ├── calculator_factory.py    # GPAW calculators desde YAML
│       ├── workflow_manager.py      # relax→scf→bands→dos→soc
│       ├── convergence.py           # barrido Ecut y k-mesh
│       ├── postprocessing.py        # extrae Eg, DOS, bandas
│       ├── bandgap_correction.py    # scissor operator χSOC + χHSE
│       └── plotting.py              # band structure, DOS, convergencia
├── scripts/
│   ├── run_full_workflow.py         # CLI completo (Click)
│   ├── run_convergence_test.py      # CLI de convergencia
│   └── apply_scissor.py            # CLI corrección scissor
└── tests/
    ├── test_structure_builder.py
    ├── test_calculator_factory.py
    ├── test_bandgap_correction.py
    └── test_postprocessing.py
```

## Instalación

### Paso 1: Instalar GPAW y ASE

```bash
pip install gpaw ase
```

Para compilar GPAW con soporte MPI completo (recomendado para producción):

```bash
# Ubuntu/Debian
sudo apt-get install libxc-dev libfftw3-dev libopenblas-dev
pip install gpaw

# Verificar instalación
python -c "import gpaw; print(gpaw.__version__)"
```

### Paso 2: Descargar los datasets PAW

```bash
gpaw install-data ~/.gpaw/datasets
# O en directorio personalizado:
gpaw install-data /path/to/datasets --register
```

Datasets usados para CsPbI₃:
- `Cs.9.PBE` — semicore 5s²5p⁶6s¹ (9 electrones de valencia)
- `Pb.14.PBE` — semicore 5d¹⁰6s²6p² (14 electrones, **crítico para SOC**)
- `I.7.PBE` — 5s²5p⁵ (7 electrones)

### Paso 3: Instalar este paquete

```bash
git clone https://github.com/rxwhizz/gpaw-repo.git
cd gpaw-repo/dft-cspbi3-gpaw
pip install -e ".[dev]"
```

## Quickstart — α-CsPbI₃ en 5 comandos

```bash
# 1. Verificar que la estructura α tiene 5 átomos y a₀ ≈ 6.18 Å
python -c "
from dft_cspbi3 import StructureBuilder
a = StructureBuilder.build_alpha()
print(f'{len(a)} atoms, a0={a.cell[0,0]:.3f} Å, SG={a.info[\"space_group\"]}')
"

# 2. Comprobar convergencia Ecut y k-mesh (necesita GPAW instalado)
python scripts/run_convergence_test.py --test both --phase alpha

# 3. Correr workflow completo: relax → SCF → bandas → DOS → SOC
python scripts/run_full_workflow.py --phase alpha --steps relax,scf,bands,dos,soc

# 4. Modo dry-run (solo genera inputs, no ejecuta GPAW)
python scripts/run_full_workflow.py --phase alpha --dry-run

# 5. Aplicar corrección scissor y generar plot
python scripts/apply_scissor.py \
    --pbe-gpw calculations/alpha/02_scf/scf.gpw \
    --bands-gpw calculations/alpha/03_bands/bands.gpw \
    --phase alpha --report
```

### Paso opcional: OghmaNano device physics

OghmaNano no es ML; es un simulador físico de dispositivo
drift-diffusion/óptica. En este repo queda como paso DFT opcional para preparar
un paquete de dispositivo desde los resultados DFT y para parsear resultados de
Oghma (`sim_info.dat`) si ya existe una corrida validada.

```bash
# instalar el runner Ubuntu si tienes sudo
bash scripts/install_oghma_ubuntu.sh /ruta/a/oghma-8.1.deb

# preparar inputs en calculations/alpha/14_oghma_device/
python main.py run --phase alpha --steps oghma_device
```

La automatización no controla la GUI. Si el core `oghma_core` queda disponible,
el paso puede detectarlo; la ejecución headless solo debe activarse en
`configs/default_params.yaml` cuando el proyecto/template de Oghma haya sido
validado. El paso escribe `method_comparison.html` para visualizar DFT/SQ,
OghmaNano y el espacio reservado para AINAGENT ML lado a lado.

### Con MPI (paralelización)

```bash
# 8 procesos MPI
mpirun -n 8 gpaw python scripts/run_full_workflow.py --phase alpha --cores 8

# En SLURM:
srun -n 32 gpaw python scripts/run_full_workflow.py --phase gamma
```

## Metodología DFT para CsPbI₃

### Parámetros clave

```python
from gpaw import GPAW, PW, Mixer
from dft_cspbi3 import GPAWCalculatorFactory, StructureBuilder

atoms = StructureBuilder.build_alpha()
factory = GPAWCalculatorFactory()

# Relajación estructural con PBEsol + D3
calc_relax = factory.create("relax")
# → mode=PW(450), xc='PBEsol', kpts=[6,6,6], Mixer(beta=0.05)

# SCF de alta precisión
calc_scf = factory.create("scf")
# → convergence={'energy':1e-8}, occupations={'name':'fermi-dirac','width':0.05}

# Bandas non-SCF
calc_bands = factory.create("bands", atoms=atoms)
# → fixdensity=True, symmetry='off', path='XRMGR'

# HSE06 (reducido 4×4×4 por coste)
calc_hse = factory.create("hse06")
# → xc={'name':'HSE06','omega':0.11}
```

### Workflow completo desde Python

```python
from dft_cspbi3 import DFTWorkflow

wf = DFTWorkflow(phase="alpha", work_dir="./calcs")
wf.run(steps=["relax", "scf", "bands", "dos", "soc"])
wf.get_status()
```

### Fases CsPbI₃

| Fase | Grupo espacial | N átomos | a (Å) | b (Å) | c (Å) | Color | T estabilidad |
|---|---|---|---|---|---|---|---|
| α (cúbica) | Pm̄3m (#221) | 5 | 6.18 | 6.18 | 6.18 | negra | > 330 °C |
| γ (ortorrómbica) | Pnma (#62) | 20 | 8.855 | 8.579 | 12.47 | negra | 25 °C (metaestable) |
| δ (ortorrómbica) | Pnma (#62) | 20 | 10.47 | 4.80 | 17.77 | amarilla | 25 °C (estable) |

La fase γ usa tilt octaédrico de Glazer **a⁻b⁺a⁻** (distorsión de los octaedros PbI₆).
La fase δ tiene octaedros de **aristas compartidas** (no esquinas), sin efecto perovskita.

## Cancelación de errores SOC/HSE06 en Pb

El error de PBE en sistemas de Pb proviene de dos fuentes opuestas que se
pueden separar y corregir independientemente:

| Método | Eg (eV) | Error vs. exp. | Coste relativo |
|---|---|---|---|
| PBE (sin SOC) | 1.44 | −0.29 eV (subestima) | 1× (referencia) |
| PBE + SOC | 0.60 | −1.13 eV (muy incorrecto) | 2–3× |
| HSE06 (sin SOC) | 1.76 | +0.03 eV (casi exacto) | ~30× |
| HSE06 + SOC | 1.55 | −0.18 eV | ~60× |
| **Scissor (PBE+D3 + χSOC + χHSE)** | **~1.52** | **~−0.2 eV** | **~5×** |
| Experimental (α, 5K) | 1.73 | — | — |

**Estrategia scissor (Eg = E_PBE+D3 + χSOC + χHSE):**
- χSOC = Eg(PBE+SOC) − Eg(PBE) ≈ −0.84 eV — SOC reduce dramáticamente Eg en Pb
- χHSE = Eg(HSE06) − Eg(PBE) ≈ +0.32 eV — HSE06 abre el gap
- Ambos calculados en celdas pequeñas y transferidos al sistema real
- Equivalente a HSE06+SOC pero **~10× más barato**

```python
from dft_cspbi3.bandgap_correction import ScissorCorrection

corrector = ScissorCorrection()

# Con archivos .gpw disponibles:
result = corrector.run_full_correction(
    gpw_pbe="02_scf/scf.gpw",
    gpw_pbe_soc="05_soc/soc.gpw",   # opcional
    gpw_hse="06_hse06/hse06.gpw",   # opcional
    phase="alpha",
)
print(f"Eg_corr = {result.e_corrected:.3f} eV")

# Sin archivos, usando valores de literatura:
corrector.report(phase="alpha")
```

## Convergencia

Los parámetros por defecto están preconvergidos para α-CsPbI₃:

```bash
# Barrer Ecut de 300 a 550 eV
python scripts/run_convergence_test.py --test encut --ecut-values 300,350,400,450,500,550

# Barrer k-mesh de 4×4×4 a 10×10×10
python scripts/run_convergence_test.py --test kpoints --kpt-meshes 4,6,8,10
```

Criterio de convergencia: **< 1 meV/átomo** en energía total.
Resultado típico: Ecut = 450 eV, k-mesh = 6×6×6 para α-CsPbI₃.

## SOC en GPAW

### Modo perturbativo (recomendado)

```python
from gpaw import GPAW
from gpaw.spinorbit import spinorbit_eigenvalues

calc = GPAW("scf.gpw")
e_kn, s_kn = spinorbit_eigenvalues(calc, theta=0, phi=0)
# e_kn: eigenvalores con SOC [nkpts × nbands×2], eV
# s_kn: proyecciones de espín
```

### Modo no-colineal (cálculo completo)

```python
from gpaw import GPAW, PW
calc = GPAW(mode=PW(450), xc='PBEsol', nspins=4, ...)
# Requiere cálculo SCF completo no-colineal — ~4× más costoso
```

## Tests

```bash
# Todos los tests (no requiere GPAW instalado — usan mocks)
pytest tests/ -v

# Con cobertura
pytest tests/ --cov=dft_cspbi3 --cov-report=html

# Test específico
pytest tests/test_structure_builder.py -v
pytest tests/test_bandgap_correction.py -v
```

Los tests de `test_calculator_factory.py` y `test_postprocessing.py` usan
`unittest.mock` para parchear el módulo `gpaw`, por lo que corren sin GPAW instalado.

## Desarrollo

```bash
# Formateo y linting
ruff check src/ tests/
ruff format src/ tests/

# Type checking
mypy src/dft_cspbi3/

# Instalar dependencias de desarrollo
pip install -e ".[dev]"
```

## Citar

Si usas este código, por favor cita las herramientas subyacentes:

- GPAW: J. J. Mortensen et al., *J. Chem. Phys.* **160**, 092503 (2024)
- ASE: Ask Hjorth Larsen et al., *J. Phys.: Condens. Matter* **29**, 273002 (2017)
- PBEsol: J. P. Perdew et al., *Phys. Rev. Lett.* **100**, 136406 (2008)
- HSE06: J. Heyd, G. E. Scuseria, M. Ernzerhof, *J. Chem. Phys.* **118**, 8207 (2003)
- DFT-D3: S. Grimme et al., *J. Chem. Phys.* **132**, 154104 (2010)

## Licencia

GPLv3 — compatible con GPAW y ASE.
