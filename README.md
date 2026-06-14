# DFT Perovskitas Haluros | GPAW

Pipeline de cálculos DFT para comparación experimental-ML de perovskitas haluro ABX₃.  
**Backend**: GPAW (Python nativo). **Estructuras**: ASE.  
**Fecha estado**: 2026-06-14

---

## Objetivo del proyecto

Construir una base DFT rigurosa para 8 materiales candidatos identificados por ML:
- **4 Pb-based**: CsPbI3, MAPbI3, FAPbI3, FAPbBr3 → G0W0@PBE + SOC
- **4 Sn-based**: CsSnI3, MASnI3, FASnI3, FASnBr3 → r²SCAN+U + SOC (U=2.5 eV)

Comparar directamente propiedades DFT vs predicciones ML (ALIGNN, MACE, mBJ).

---

## Materiales y estado de cálculos

| Material | Fórmula | Estado relax | Estado SCF | Gap PBE | Gap final | Notas |
|----------|---------|---|---|---|---|---|
| **CsPbI3-α** | Cs1Pb1I3 | ✅ | ✅ DOS, bandas, SOC | 1.089 eV | G0W0 en curso | Hessiano estable; fonones 20/30 |
| **MAPbI3** | (CH3NH3)1Pb1I3 | ⏳ | ⏳ | — | G0W0 pendiente | Catión orgánico MA |
| **FAPbI3** | (HC(NH2)2)1Pb1I3 | ⏳ | ⏳ | — | G0W0 pendiente | Catión orgánico FA |
| **FAPbBr3** | (HC(NH2)2)1Pb1Br3 | ⏳ | ⏳ | — | G0W0 pendiente | Haluro Br |
| **CsSnI3** | Cs1Sn1I3 | ✅ | ✅ U-scan | 1.872 eV @ U=2.5 | **1.359 eV** ✓ exp~1.3 | r²SCAN+U validado |
| **MASnI3** | (CH3NH3)1Sn1I3 | ⏳ | ⏳ | — | r²SCAN+U pendiente | Target: 1.1–1.4 eV |
| **FASnI3** | (HC(NH2)2)1Sn1I3 | ⏳ | ⏳ | — | r²SCAN+U pendiente | Target: 1.2–1.5 eV |
| **FASnBr3** | (HC(NH2)2)1Sn1Br3 | ✅ preconv | ⏳ | 1.558 eV (PBE+U) | r²SCAN+U pendiente | Target: 1.8–2.3 eV |

---

## Metodología DFT

### Estructura común para todos los materiales

| Parámetro | Valor | Comentario |
|-----------|-------|-----------|
| Método PAW | GPAW | Setups PBE vía `gpaw install-data` |
| Corte ondas planas | 450 eV | Convergencia típica ABX3 |
| Malla k (relax/SCF) | 6×6×6 Γ-centrada | Primitiva de 5 átomos (Cs) o 1 fórmula |
| Convergencia SCF | densidad 1e-4 | Criterio dominante para convergencia |
| Fermi-Dirac smearing | 0.2 eV (r²SCAN), 0.1 eV (PBE+U) | Evita oscilaciones en Sn-based |

### Para **Sn-based** (CsSnI3, MASnI3, FASnI3, FASnBr3)

**Funcional**: r²SCAN+U (metaGGA + Hubbard en Sn-5s)  
**U calibrado**: 2.5 eV (validado en CsSnI3 — reproduce gap exp. 1.3 eV)  
**Pipeline** (u_scan_r2scan.py):

```
1. preconv PBEsol+U (density=1e-2)  →  estructura inicial para U-scan
2. U-ramping r²SCAN  →  [U=0, 1.0, 2.0]  (warm starts)
3. U fine-scan  →  [U=2.0, 2.25, 2.5, 2.75] eV  (16–19 iters cada uno)
4. SOC perturbativo  →  ignora XC (MGGA)  →  Δ_SOC ≈ −0.51 eV
5. PDOS  →  Reader API directo  →  caracteres orbital (I-p, Sn-p, etc)
```

**Por qué U-ramping:**  
Convergencia directa a U=3.5 falla (falsos mínimos locales en paisaje DFT+U de Sn-5s).  
U-ramping desde U=0 guía al mixer al mínimo correcto. Descubrimiento: **U=3.5 sobrecorrige** — U=2.5 es óptimo.

**CsSnI3 — referencia validada**:
| U (eV) | gap r²SCAN | gap + SOC | Δ_SOC | Exp. |
|--------|-----------|----------|-------|------|
| 2.5 | 1.872 | **1.359** | −0.514 | **1.30 ✓** |

### Para **Pb-based** (CsPbI3, MAPbI3, FAPbI3, FAPbBr3)

**Funcional**: G0W0@PBE (perturbación MBPT sin parámetros empíricos)  
**Ventaja**: benchmark independiente para validar si Pb necesita corrección Hubbard  
**Pipeline** (g0w0_groundstate.py + g0w0_run.py):

```
1. Relax PBE  →  estructura relajada
2. Groundstate PBE (600 bandas, Ecut=600 eV)
3. G0W0 PPA (Plasmon-Pole Approximation, ecut_gw=100 eV, extrapol. 74/86/100)
4. Ecut extrapolation  →  Σ(∞) = A + B/ecut³
5. SOC perturbativo  →  sobre G0W0@PBE
```

**CsPbI3 — en curso (2026-05-25)**:
- Groundstate PBE: gap=1.288 eV, 600 bandas ✅
- G0W0 PPA: 4/19 k-puntos off-Γ completados 🔄

---

## Estructura del repositorio

```
dft/
├── README.md
├── pyproject.toml
├── requirements.txt
│
├── configs/
│   └── default_params.yaml          # Parámetros DFT, YAML centralizado
│
├── calculations/                    # Resultados por material y paso
│   ├── alpha/
│   │   ├── 01_relax/
│   │   ├── 02_scf/
│   │   ├── 03_bands/
│   │   ├── 04_dos/
│   │   ├── 05_soc/
│   │   ├── 07_vibrational/
│   │   └── ...
│   └── [otros materiales]/
│
├── src/
│   ├── dft_cspbi3/                 # Core DFT workflows
│   │   ├── structure_builder.py    # ASE crystal() para ABX3
│   │   ├── calculator_factory.py   # GPAW desde YAML
│   │   ├── workflow_manager.py     # orquestar pasos: relax→scf→bands→dos→soc
│   │   ├── convergence.py          # barridos Ecut, k-mesh
│   │   ├── postprocessing.py       # extrae Eg, DOS, bandas
│   │   ├── bandgap_correction.py   # scissor operator
│   │   ├── top8.py                 # generador Top-8 estructuras
│   │   ├── analysis/               # análisis por material
│   │   ├── validation/             # validación phonons, hessian
│   │   ├── reporting/              # reportes y tablas DFT vs ML
│   │   └── plotting.py             # banda, DOS, convergencia
│   │
│   ├── ml_surrogate/               # Modelos ML (ALIGNN, MACE)
│   ├── buho/                       # Herramientas secundarias
│   └── monitor_api/                # Monitor de convergencia
│
├── scripts/                        # CLI principales
│   ├── main.py                     # CLI maestro (Click)
│   ├── u_ramp_r2scan.py            # U-ramping para Sn-based
│   ├── u_scan_r2scan.py            # U fine-scan r²SCAN+U
│   ├── u_scan_soc_dos.py           # SOC + DOS post-U-scan
│   ├── u_scan_pdos.py              # PDOS con Reader API
│   ├── g0w0_groundstate.py         # Groundstate 600 bandas para G0W0
│   ├── g0w0_run.py                 # G0W0 PPA runner
│   ├── g0w0_soc.py                 # SOC sobre G0W0
│   └── [otros scripts]/
│
├── migration/
│   ├── bitacora.md                 # Timeline experimentos, hallazgos claves
│   └── [documentos convergencia]/
│
└── tests/
    ├── test_structure_builder.py
    ├── test_workflow_manager.py
    └── ...
```

---

## Instalación y configuración

### 1. Instalar GPAW con MPI

```bash
# Dependencias (Ubuntu/Debian)
sudo apt-get install libxc-dev libfftw3-dev libopenblas-dev libopenmpi-dev

# GPAW desde pip
pip install gpaw>=24.1.0 ase>=3.23.0

# Descargar datasets PAW
gpaw install-data ~/.gpaw/gpaw-setups-24.11.0
export GPAW_SETUP_PATH=~/.gpaw/gpaw-setups-24.11.0
```

### 2. Clonar y configurar proyecto

```bash
git clone <repo> dft
cd dft
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 3. Variables de entorno (MPI, cálculos)

```bash
# Configuración por sesión
export GPAW_SETUP_PATH=~/.gpaw/gpaw-setups-24.11.0
export GPAW_CONFIG=$(pwd)/siteconfig.py
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1

# siteconfig.py debe especificar:
# - compiler = 'mpicc'
# - libxc_version = '5.2.3'
```

---

## Uso: ejecutar cálculos

### CsSnI3 (Sn-based): reproducir U=2.5 eV validado

```bash
# 1. Preconv PBEsol+U
mpirun -n 7 python scripts/u_ramp_r2scan.py --mat CsSnI3

# 2. U fine-scan r²SCAN+U [2.0, 2.25, 2.5, 2.75] eV
mpirun -n 22 python scripts/u_scan_r2scan.py --mat CsSnI3

# 3. SOC + DOS
mpirun -n 4 python scripts/u_scan_soc_dos.py --mat CsSnI3

# 4. PDOS
python scripts/u_scan_pdos.py --mat CsSnI3
```

Resultado esperado: **gap(SOC @ U=2.5) = 1.359 eV** ✓ (exp ~1.3 eV)

### CsPbI3 (Pb-based): correr G0W0

```bash
# 1. Groundstate PBE (600 bandas)
mpirun -n 22 python scripts/g0w0_groundstate.py --mat CsPbI3

# 2. G0W0 PPA (ecut=100 eV, extrapolación)
mpirun -n 4 python scripts/g0w0_run.py --mat CsPbI3

# 3. SOC perturbativo
python scripts/g0w0_soc.py --mat CsPbI3
```

### CLI maestro: ejecutar múltiples pasos

```bash
python main.py run --phase alpha --steps relax scf bands dos soc --validate
python main.py run --material CsSnI3 --method r2scan-u --u-scan 2.0 2.25 2.5 2.75
```

---

## Hallazgos principales

### Convergencia SCF para Sn-based

**Problema**: oscilación energética ±1–4 eV sin convergencia densidad.  
**Causa raíz**: doble pozo en paisaje DFT+U de Sn-5s → mixer salta entre mínimos locales.  
**Solución**: U-ramping desde U=0 (guía al mínimo correcto) + beta pequeño (movimiento local).

### U óptimo para Sn

| Material | U testeado | U óptimo | Gap SOC | Exp |
|----------|-----------|---------|---------|-----|
| CsSnI3 | 0–3.5 eV | **2.5 eV** | 1.359 eV | 1.30 eV ✓ |
| MASnI3 | pendiente | ~2.5? | pendiente | 1.24 eV |
| FASnI3 | pendiente | ~2.5? | pendiente | 1.41 eV |
| FASnBr3 | pendiente | ~2.5? | pendiente | 2.05 eV |

**Descubrimiento**: U=3.5 eV sobrecorrige el gap (fue ansatz inicial incorrecto).

### G0W0 como benchmark (Pb-based)

G0W0 evita parámetros empíricos. En progreso:
- **CsPbI3**: groundstate ✅, G0W0 4/19 q-puntos 🔄
- **MAPbI3, FAPbI3, FAPbBr3**: pendientes

---

## Comparación DFT vs ML

Base de validación construida en [migration/DFT_CONTEXT_TOP8.md](migration/DFT_CONTEXT_TOP8.md):

| Propiedad | DFT | ML (ALIGNN) | Diferencia |
|-----------|-----|-----------|-----------|
| Bandgap CsPbI3 | 1.29–1.59 eV (G0W0) | 1.598 eV (mBJ) | < 0.05 eV |
| Energía formación | DFT ref | ML gap | en auditoría |
| Masa efectiva e⁻ | DFT PBE+SOC | ALIGNN | en auditoría |
| Dielectrico | DFT RPA | ALIGNN | en auditoría |

---

## Dependencias

Mínimas (pyproject.toml):
```
gpaw>=24.1.0          # DFT solver
ase>=3.23.0           # Estructuras/optimización
numpy, pandas, scipy  # Cálculos numéricos
pyyaml                # Archivos de configuración
click                 # CLI
phonopy>=2.20         # Fonones
spglib>=2.0           # Simetría
matplotlib            # Gráficos
```

---

## Referencia rápida

| Tarea | Comando | Tiempo |
|-------|---------|--------|
| Relax CsPbI3 (PBE, 7 cores) | `mpirun -n 7 ... main.py run --steps relax` | ~30 min |
| U-scan CsSnI3 (r²SCAN+U, 22 cores) | `mpirun -n 22 python scripts/u_scan_r2scan.py` | ~15 min (5 U-puntos) |
| Fonones α (supercelda 2×2×2, MPI) | `mpirun -n 7 main.py run --steps phonons --validate` | ~6 h (10 desplazamientos) |
| G0W0 CsPbI3 (4 cores, ecut=100) | `mpirun -n 4 python scripts/g0w0_run.py` | ~40 h (full BZ) |

---

## Citas y referencias

- **GPAW**: J. J. Mortensen et al., Phys. Rev. B **71**, 035109 (2005)
- **r²SCAN**: J. Sun et al., Phys. Rev. Lett. **115**, 036402 (2015)
- **G0W0**: M. S. Hybertsen & S. G. Louie, Phys. Rev. B **34**, 5390 (1986)
- **Perovskitas haluro**: Top-8 ML validados en [DFT_CONTEXT_TOP8.md](migration/DFT_CONTEXT_TOP8.md)

---

**Última actualización**: 2026-06-14  
**Estado proyecto**: Sn-based metodología ✅, Pb-based G0W0 en curso 🔄

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

## Inicio rápido — α-CsPbI₃ en 5 comandos

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

## Top 8 ML vs DFT en PBE

El archivo `DFT_CONTEXT_TOP8.md` se implementa como una base comparativa PBE
para los 8 candidatos ML. El preparador genera estructuras iniciales cubicas,
un CSV con el esquema ML/DFT y un runner que no incluye HSE06.

```bash
# preparar estructuras, CSV y runner
.venv/bin/python scripts/setup_top8_pbe.py --overwrite-structures

# validar el flujo sin ejecutar GPAW pesado
DRY_RUN=1 calculations/top8_pbe/run_top8_pbe.sh

# ejecutar PBE para los 8 candidatos
calculations/top8_pbe/run_top8_pbe.sh

# ejecutar todo automatico: DFT PBE por material y luego AI
scripts/run_top8_auto.sh

# inicializar/supervisar en segundo plano con MPI_N=7 por defecto
scripts/supervise_top8_auto.sh start
scripts/supervise_top8_auto.sh status
scripts/supervise_top8_auto.sh phase-log
scripts/supervise_top8_auto.sh calc-log

# refrescar la tabla despues de corridas parciales o completas
.venv/bin/python scripts/setup_top8_pbe.py --collect-only
```

Por defecto el runner usa:
`relax,scf,bands,dos,soc,effective_masses,score`.
SOC es perturbativo sobre PBE y se usa para masas efectivas cuando existe el
archivo fino de bandas. La tabla se escribe en
`calculations/top8_pbe/top8_pbe_comparison.csv`.
Cuando `score` esta incluido y `MPI_N>1`, el runner separa automaticamente la
corrida: los pasos DFT pesados usan MPI y `score` se ejecuta serial por defecto
(`SCORE_MPI_N=1`) para evitar escrituras JSON concurrentes.

El runner automatico acepta variables de entorno utiles:

```bash
# prueba sin calculos pesados
DRY_RUN=1 scripts/run_top8_auto.sh

# correr en MPI y continuar aunque un material falle
MPI_N=7 STOP_ON_ERROR=0 scripts/run_top8_auto.sh

# correr en segundo plano con systemd --user y MPI
MPI_N=7 STOP_ON_ERROR=0 scripts/supervise_top8_auto.sh start

# reintentar solo score sin MPI
MPI_N=1 RUN_AI=0 DFT_STEPS=score PHASES="MAPbI3 MASnI3" scripts/run_top8_auto.sh

# solo DFT, solo una formula
RUN_AI=0 PHASES="CsSnI3" scripts/run_top8_auto.sh

# solo refrescar/ejecutar AI contra el CSV DFT existente
RUN_DFT=0 RUN_AI=1 scripts/run_top8_auto.sh
```

Los logs quedan en `calculations/top8_pbe/logs/` y el resumen de ejecucion en
`calculations/top8_pbe/top8_auto_status.csv`.
El supervisor guarda el unit activo en `calculations/top8_pbe/top8_auto.unit`;
para detenerlo usa `scripts/supervise_top8_auto.sh stop`.

### Paso opcional: fisica dispositivo OghmaNano

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
| Experimento (α, 5K) | 1.73 | — | — |

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

# Chequeo tipos
mypy src/dft_cspbi3/

# Instalar dependencias de desarrollo
pip install -e ".[dev]"
```

## Citar

Si usas este código, cita herramientas base:

- GPAW: J. J. Mortensen et al., *J. Chem. Phys.* **160**, 092503 (2024)
- ASE: Ask Hjorth Larsen et al., *J. Phys.: Condens. Matter* **29**, 273002 (2017)
- PBEsol: J. P. Perdew et al., *Phys. Rev. Lett.* **100**, 136406 (2008)
- HSE06: J. Heyd, G. E. Scuseria, M. Ernzerhof, *J. Chem. Phys.* **118**, 8207 (2003)
- DFT-D3: S. Grimme et al., *J. Chem. Phys.* **132**, 154104 (2010)

## Licencia

GPLv3 — compatible con GPAW y ASE.
