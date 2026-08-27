# BUHO: descubrimiento de perovskitas fotovoltaicas

Pipeline completo para buscar perovskitas ABX₃ con bandgap útil en fotovoltaica:
genera candidatos, los criba con un modelo de aprendizaje automático, calcula
los supervivientes con DFT, y reentrena el modelo con lo aprendido.

Backend de cálculo: **GPAW**. Estructuras: **ASE**. Interfaz: aplicación de
escritorio autónoma.

## El ciclo

```
   generar          cribar              calcular            aprender
  ─────────      ────────────         ──────────         ─────────────
  Heurística  →  Cascada HTS      →   DFT (GPAW)    →    Reentrenar el
  ABX₃ mixtas    3 tiers              PBE / r2SCAN       surrogate con
                 física → ML → MLFF   bandgap, energía   los resultados
                                                              │
                          └───────────────────────────────────┘
```

Cada vuelta criba más fino, porque el modelo aprende de los cálculos que él
mismo pidió. Eso es lo que separa el *active learning* de un simple «predecir
y filtrar».

### 1. Generación

`src/buho/generator/` produce composiciones ABX₃, puras y mixtas en cualquiera
de los tres sitios, con sus factores de Goldschmidt y octaédrico. Un candidato
mixto como `Cs₀.₅₂FA₀.₄₈SnI₃` sale con sus fracciones por sitio, no como una
etiqueta suelta.

### 2. Cribado

`src/buho/screening/cascade.py` es una torre de tres tiers donde cada uno solo
evalúa lo que sobrevivió al anterior:

| Tier | Qué mira | Coste |
|---|---|---|
| 0. Física | Cotas de tolerancia, factor octaédrico, neutralidad de carga | µs |
| 1. Surrogate | Bandgap predicho ± σ contra la ventana fotovoltaica | ms |
| 2. MLFF | Energía de formación con MEGNet/M3GNet | s |

El Tier 1 criba **con holgura de σ**: el surrogate tiene un MAE de 0.31 eV y la
ventana mide 0.7 eV, así que cribar por la estimación puntual tiraría materiales
cuyo bandgap real sí cae dentro. En una prueba de 100 candidatos, esa holgura
rescató 10.

### 3. Cálculo

Los supervivientes se materializan como estructuras cristalinas
(`src/buho/structure/`) y se preparan como trabajos DFT que un runner lanza con
la concurrencia que aguante la máquina. El paquete `src/dft_cspbi3/` es el que
sabe de GPAW: relajación, SCF, bandas, DOS, acoplamiento espín-órbita y
corrección scissor.

### 4. Aprendizaje

`src/buho/active_learning/` acumula los resultados DFT, reentrena el surrogate y
prepara el siguiente lote. La adquisición usa UCB (`score + β·σ`) para no
quedarse solo con lo que ya parece bueno.

## La aplicación

Todo lo anterior se conduce desde una aplicación de escritorio con el motor
empaquetado dentro: no necesita Python, Node ni el repositorio.

- **En vivo**: qué está haciendo el sistema y cuánto le queda, estimado con la
  mediana real de los trabajos ya terminados.
- **Cribado**: lanza la cascada y enseña cuántos caen en cada tier.
- **Candidatos**: los viables, verificados por DFT, ordenados por score
  fotovoltaico. Exportables a CSV.
- **Predictor**: precisión del modelo contra los cálculos hechos.
- **Estructuras**: visor 3D con bolas y palos, exportable a PNG.
- **Resultados**: informes, figuras y el log de GPAW en vivo.
- **Lotes**: lanzar, detener y calibrar cuántos trabajos concurrentes aguanta
  la máquina.

Se descarga desde [Releases](https://github.com/RxWhizz/DFT/releases). Hay una
versión de escritorio y otra que se abre en el navegador. Ver
[Monitor (GUI)](#monitor-gui) más abajo.

## Por qué GPAW sobre VASP

| Aspecto | GPAW | VASP |
|---|---|---|
| Licencia | GPLv3 (open-source) | Comercial (~4 000 €/grupo) |
| Método PAW | Nativo (`gpaw-setups`) | Nativo (`POTCAR`) |
| Integración Python | Directa (objetos ASE, API Python) | Limitada (archivos POSCAR/INCAR) |
| Pseudopotenciales externos | No necesita, trae los suyos | Requiere POTCAR compilado |
| SOC | `spinorbit_eigenvalues()` + no-colineal | `LSORBIT = .TRUE.` + `LNONCOLLINEAR` |
| Híbridos | HSE06 vía `xc={'name':'HSE06','omega':0.11}` | `HFSCREEN`, `AEXX` |
| Ondas planas | `mode=PW(450)` | `ENCUT = 450` |
| Workflows Python | Clases nativas, sin wrappers | Requiere pyiron, AiiDA, atomate, etc. |
| Paralelización | MPI + OpenMP nativo | MPI nativo |

## Equivalencias VASP → GPAW

| VASP | GPAW | Notas |
|---|---|---|
| `ENCUT = 450` | `mode=PW(450)` | Ecut en eV, idéntico significado físico |
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
DFT/
├── src/
│   ├── buho/                     # El pipeline de descubrimiento
│   │   ├── generator/            #   candidatos ABX3 puros y mixtos
│   │   ├── screening/cascade.py  #   torre de cribado de 3 tiers
│   │   ├── structure/            #   construcción de la celda cristalina
│   │   ├── dft_jobs/             #   prepara los trabajos DFT
│   │   ├── active_learning/      #   acumula, reentrena, prepara el siguiente
│   │   ├── phase2_force/         #   relajación con MLFF antes del DFT
│   │   ├── bench/                #   calibración de rendimiento por máquina
│   │   └── gpaw_setup.py         #   localiza los datasets PAW
│   │
│   ├── dft_cspbi3/               # El cálculo DFT con GPAW
│   │   ├── structure_builder.py  #   las tres fases de CsPbI3
│   │   ├── calculator_factory.py #   calculadoras desde YAML
│   │   ├── workflow_manager.py   #   relax → scf → bands → dos → soc
│   │   ├── convergence.py        #   barrido de Ecut y k-mesh
│   │   ├── bandgap_correction.py #   scissor: chi_SOC + chi_HSE
│   │   └── analysis/             #   óptica, fonones, post-proceso
│   │
│   ├── ml_surrogate/             # El predictor de bandgap
│   │   ├── features.py           #   radios, electronegatividades, t, mu
│   │   ├── model.py              #   ensemble RF + GBR con sigma bootstrap
│   │   └── gnn_predictor.py      #   MEGNet/M3GNet, carga diferida
│   │
│   └── monitor_api/              # El backend de la interfaz
│       ├── paths.py              #   bundle / datos / configuración
│       ├── poller.py             #   vigila los lotes y lanza runners
│       ├── router.py             #   la API REST
│       ├── launcher.py           #   arranque, congelado o desde el repo
│       └── services/             #   cribado, candidatos, ML, actividad…
│
├── apps/dft_monitor_flutter/     # La aplicación de escritorio
├── frontend/                     # El SPA de la versión web
├── packaging/                    # Specs de PyInstaller y .desktop
├── scripts/                      # CLIs: runners, benchmarks, figuras, build
├── configs/                      # Parámetros DFT y del monitor
├── structures/                   # Fases de referencia y top 8
├── models/                       # Surrogates entrenados (.pkl + métricas)
└── tests/                        # 502 tests (461 sin necesitar GPAW)
```

Los directorios de datos (`runs/`, `local_runs/`, `data/`, `reports/`,
`imagenes/`, `calculations/`) son enlaces al volumen de trabajo y no viajan en
el repositorio.

## Empezar

**Solo mirar y conducir el pipeline**: descarga la aplicación desde
[Releases](https://github.com/RxWhizz/DFT/releases). No necesita nada instalado:

```bash
tar xzf dft-monitor-desktop-0.2.0-linux-x86_64.tar.gz
./dft-monitor-desktop-0.2.0-linux-x86_64/dft_monitor_flutter
```

**Correr el pipeline de verdad** hace falta GPAW, porque los cálculos son
reales. Sigue la instalación de abajo y luego:

```bash
# Comprobar que el entorno está sano antes de nada
buho doctor

# Una vuelta completa del ciclo: acumula lo calculado, reentrena el surrogate,
# genera el siguiente lote y lo deja preparado.
buho active-learning advance

# Lanzar el runner sobre un lote preparado
buho dft-jobs run-relax

# Medir cuántos trabajos concurrentes y cuántos núcleos aguanta la máquina
buho bench machine
```

Desde la aplicación es lo mismo sin comandos: **Cribado** lanza la cascada y
enseña cuántos caen en cada tier, **Empezar DFT** prepara los supervivientes, y
**Lotes** los ejecuta con la concurrencia configurada.

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
- `Cs.9.PBE`: semicore 5s²5p⁶6s¹ (9 electrones de valencia)
- `Pb.14.PBE`: semicore 5d¹⁰6s²6p² (14 electrones, **crítico para SOC**)
- `I.7.PBE`: 5s²5p⁵ (7 electrones)

### Paso 3: Instalar este paquete

```bash
git clone https://github.com/RxWhizz/DFT.git
cd DFT
pip install -e ".[dev]"
```

## El CLI

Cada capacidad del pipeline tiene un comando. Después de instalar el paquete
(Paso 3, arriba) queda `buho` en el PATH:

```bash
buho --help
```

Son **30 grupos y 140 comandos**. Lo primero que conviene correr es el
diagnóstico, que revisa el intérprete, los datasets PAW, los datos y los modelos
antes de que falle un lote entero:

```bash
buho doctor
```

### Una vuelta del ciclo, comando a comando

```bash
# 1. Generar candidatos ABX3 y construir sus estructuras
buho generate generate
buho generate build-structures

# 2. Cribar con la cascada de tres tiers
buho screening run --n-candidates 500 --n-batches 1
buho screening tiers              # cuántos caen en cada tier

# 3. Preparar y lanzar los cálculos DFT
buho dft-jobs prepare-relax
buho dft-jobs run-relax
buho dft-jobs collect-results

# 4. Reentrenar el surrogate con lo que salió
buho ml train-from-dft
buho active-learning advance
```

Y para ver dónde va todo sin interrumpir nada:

```bash
buho status              # estado del workflow, sin cargar GPAW
buho batches list        # lotes conocidos y su avance
buho activity runners    # qué procesos están vivos ahora mismo
buho candidates list     # candidatos viables y verificados
```

### Los 30 grupos

| Grupo | Cmds | Para qué |
|---|---:|---|
| `active-learning` | 4 | Bucle de aprendizaje activo por lotes |
| `activity` | 2 | Actividad real de runners y procesos |
| `agent` | 5 | Agente local del monitor |
| `analysis` | 13 | Análisis científico de salidas DFT |
| `batches` | 1 | Inspección y control de lotes |
| `bench` | 16 | Benchmarks, calibración y rendimiento |
| `calc` | 10 | Cálculos DFT, pasos del workflow y postproceso |
| `candidates` | 1 | Consulta de candidatos generados o verificados |
| `data` | 3 | Ingesta y extracción de datasets |
| `dft-jobs` | 4 | Preparación, recolección y runners de trabajos DFT |
| `doctor` | 1 | Diagnóstico de entorno, PAW, datos y modelos |
| `files` | 2 | Acceso controlado a archivos de resultados |
| `g0w0` | 4 | Correcciones G0W0 |
| `generate` | 4 | Generación, filtrado y estructuras ABX3 |
| `jobs` | 2 | Artefactos y logs de trabajos |
| `ml` | 9 | Surrogates composicionales y predicción |
| `mlip` | 10 | Entrenamiento, validación y empaquetado MLIP/MACE |
| `monitor` | 5 | Servidor, rutas y utilidades del monitor |
| `notify` | 3 | Notificaciones por Telegram |
| `paw` | 2 | Inspección de datasets PAW de GPAW |
| `phase2-force` | 10 | Fase 2A: etiquetado DFT de energía y fuerzas |
| `report` | 6 | Reportes, figuras y visualizaciones |
| `run` | 1 | Ejecuta el workflow DFT |
| `screening` | 3 | Cascada de cribado HTS |
| `status` | 1 | Estado del workflow sin cargar GPAW |
| `structures` | 2 | Estructuras de referencia y pre-generadas |
| `top8` | 7 | Flujos comparativos de las top-8 perovskitas |
| `u-scan` | 6 | Barridos de Hubbard U con r2SCAN/SOC/DOS |
| `validate` | 1 | Validaciones científicas |
| `watchdog` | 2 | Guardas de recursos |

Los grupos pesados llevan su propio `--help` con las opciones reales: `buho calc
steps` lista los pasos del workflow con el estado de cada artefacto, `buho paw
check` avisa si falta un dataset antes de lanzar nada, y `buho bench machine`
calibra cuántos trabajos concurrentes y cuántos núcleos aguanta el equipo.

## La parte DFT: α-CsPbI₃ en 5 comandos

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

# ejecutar todo automático: DFT PBE por material y luego AI
scripts/run_top8_auto.sh

# inicializar/supervisar en segundo plano con MPI_N=7 por defecto
scripts/supervise_top8_auto.sh start
scripts/supervise_top8_auto.sh status
scripts/supervise_top8_auto.sh phase-log
scripts/supervise_top8_auto.sh calc-log

# refrescar la tabla después de corridas parciales o completas
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

El runner automático acepta estas variables de entorno:

```bash
# prueba sin cálculos pesados
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

Los logs quedan en `calculations/top8_pbe/logs/` y el resumen de ejecución en
`calculations/top8_pbe/top8_auto_status.csv`.
El supervisor guarda el unit activo en `calculations/top8_pbe/top8_auto.unit`;
para detenerlo usa `scripts/supervise_top8_auto.sh stop`.

### Paso opcional: física de dispositivo con OghmaNano

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
| Experimento (α, 5K) | 1.73 | n/d | n/d |

**Estrategia scissor (Eg = E_PBE+D3 + χSOC + χHSE):**
- χSOC = Eg(PBE+SOC) − Eg(PBE) ≈ −0.84 eV. El SOC reduce dramáticamente Eg en Pb
- χHSE = Eg(HSE06) − Eg(PBE) ≈ +0.32 eV. HSE06 abre el gap
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
# Requiere cálculo SCF completo no-colineal, ~4× más costoso
```

## Monitor (GUI)

Hay **dos formas de usar la interfaz**, con el mismo backend detrás. No son
alternativas rivales: resuelven situaciones distintas.

| | **Monitor DFT** (escritorio) | **Monitor DFT (servidor web)** |
|---|---|---|
| Cómo se ve | Ventana nativa | Pestaña del navegador |
| Motor | Embebido, congelado dentro | El del repositorio o el binario |
| Necesita Python | No | Sí (o el binario congelado) |
| Necesita el repositorio | No | Sí, salvo con el binario |
| Acceso desde otra máquina | No | Sí, con `--host 0.0.0.0` y token |
| Se lanza con | Icono del escritorio o del menú | `dft-monitor-web` |
| Artefacto | `dft-monitor-desktop-<v>-<plataforma>.tar.gz` | `dft-monitor-web-<v>-<plataforma>.tar.gz` |
| Se compila con | `scripts/build_desktop.sh` | `scripts/build_web.sh` |
| Peso | ~137 MB | ~94 MB |

**Usa la de escritorio** para trabajar a diario en tu máquina: se abre de un
doble clic y no depende de nada instalado. **Usa la web** cuando quieras mirar
el pipeline desde otro equipo, o cuando ya estés en el repositorio y prefieras
el navegador.

Ambas comparten backend: FastAPI sirve la API y el SPA de React en un solo
proceso y un solo origen. La de escritorio lo arranca por dentro en un puerto
efímero; la web lo expone donde le digas.

### La app de escritorio

```bash
bash scripts/build_desktop.sh     # → dist/dft-monitor-desktop-<versión>-<plataforma>.tar.gz
bash scripts/install_launcher.sh  # instala icono, menú y acceso directo
```

Congela el motor con PyInstaller, compila la app Flutter, mete el motor dentro
del bundle y comprueba el contrato de arranque antes de comprimir. El resultado
no necesita Python, Node ni el repositorio: el `.desktop` fija `DFT_DATA_ROOT`
para que encuentre tus datos.

### El servidor web: instalación desde el binario

Cada tag publica en [Releases](https://github.com/RxWhizz/DFT/releases) un
artefacto autocontenido: **no necesita Python, ni Node, ni el repositorio**.
Lleva dentro el SPA compilado, el surrogate ML y las estructuras de referencia.

```bash
# Linux
tar xzf dft-monitor-0.2.0-linux-x86_64.tar.gz
./dft-monitor/dft-monitor --data-root /ruta/a/tus/datos
```

En Windows, descomprime el `.zip` y ejecuta `dft-monitor.exe`.

`--data-root` es el directorio que contiene `runs/`, `local_runs/`,
`calculations/`, `reports/`… Si se omite, se busca hacia arriba desde el
directorio actual. La configuración va a `~/.config/dft-monitor/monitor.yaml`
(`%APPDATA%` en Windows), no al repositorio.

`GET /api/health` dice exactamente dónde busca cada cosa:

```json
"paths":    { "frozen": true, "bundle_root": "…/_internal",
              "data_root": "…/mis-datos", "config_dir": "~/.config/dft-monitor" },
"platform": { "os": "linux", "hardware_temps": true, "runner_launch": true }
```

`platform` refleja lo que de verdad se puede hacer en esa máquina, comprobado y
no supuesto: sin sensores de temperatura (Windows) la GUI oculta esas fichas, y
sin un intérprete de Python o sin los `scripts/` del pipeline, los endpoints de
lanzar runners responden **501** en vez de fallar.

Verifica la descarga con `sha256sum -c SHA256SUMS`.

#### Compilar el binario en local

```bash
bash scripts/build_web.sh      # → dist/dft-monitor-<versión>-<plataforma>.tar.gz
```

Compila el SPA, preconvierte las estructuras (con eso `ase` no entra en el
artefacto), congela con PyInstaller y **prueba el resultado** (salud, SPA,
estructuras y una predicción ML) antes de comprimir. Se distribuye como
directorio comprimido y no como ejecutable único porque `--onefile` con este
tamaño descomprimiría todo a un temporal en cada arranque.

La versión sale de `src/monitor_api/__init__.py` y es la única: la usan
`pyproject.toml`, la app, `/api/health`, la cabecera del SPA, y la CI aborta si
un tag no coincide.

### Puesta en marcha desde el repositorio

Un solo comando, desde cualquier directorio:

```bash
./bin/dft-monitor-web
```

La primera vez crea el entorno virtual, instala las dependencias, genera
`configs/monitor.yaml` apuntando a un `runs_dir` que exista, compila el frontend
y abre el navegador. Las siguientes arranca directo.

```bash
./bin/dft-monitor-web --port 9000        # otro puerto
./bin/dft-monitor-web --host 0.0.0.0     # accesible en la LAN (exige token)
./bin/dft-monitor-web --no-browser       # sin abrir el navegador
./bin/dft-monitor-web --reload           # hot-reload para desarrollar
```

Para tenerlo como comando del sistema y en el menú de aplicaciones:

```bash
bash scripts/install_launcher.sh     # symlink en ~/.local/bin + entrada .desktop
dft-monitor
```

Todo va a `~/.local`, sin `sudo`. Se revierte con `--uninstall`.

### Puesta en marcha manual

```bash
pip install -e ".[web]"
cp configs/monitor.example.yaml configs/monitor.yaml   # ajusta runs_dir y auth.token
cd frontend && npm install && npm run build && cd ..
python3 scripts/start_monitor.py
```

Sin frontend compilado el servidor arranca igual y sirve solo la API.

### Desarrollo del frontend

```bash
python scripts/start_monitor.py --reload         # backend en :8000
cd frontend && npm run dev                       # SPA en :5173 con proxy a :8000
```

Los tipos de TypeScript se derivan de los modelos Pydantic, así que un cambio en
el backend rompe el build del frontend en vez de fallar en tiempo de ejecución:

```bash
python scripts/dump_openapi.py     # vuelca src/monitor_api/openapi.json
cd frontend && npm run gen:api     # regenera src/lib/api.d.ts
```

### Secretos

Las claves no van en `monitor.yaml`: ese fichero se comparte, se copia al
directorio de configuración al instalar y se edita a mano, así que es el
candidato natural a colarse en un commit. Van en un `.env`, que está
gitignorado y no viaja dentro de los binarios publicados.

```bash
cp .env.example .env
```

| Variable | Para qué |
|---|---|
| `DFT_MONITOR_TOKEN` | Token compartido de la interfaz web. Ponerlo activa la autenticación |
| `DFT_MONITOR_SESSION_SECRET` | Firma de las cookies. Vacío genera uno nuevo en cada arranque y cierra las sesiones abiertas |
| `DFT_MONITOR_TELEGRAM_BOT_TOKEN` | Token de @BotFather. Vacío desactiva el bot |
| `DFT_MONITOR_TELEGRAM_CHAT_ID` | Chat autorizado; los mensajes de cualquier otro se ignoran |

El `.env` se busca en la ruta que indique `DFT_ENV_FILE`, luego junto a
`monitor.yaml`, luego en la raíz de datos y por último en el directorio actual.
**Lo que ya esté en el entorno gana siempre**, así que un
`DFT_MONITOR_TOKEN=xxx buho monitor serve` puntual no lo pisa un fichero viejo.

### Acceso remoto y seguridad

El monitor puede matar procesos y lanzar runners, así que:

- Escucha en `127.0.0.1` por defecto.
- `--host 0.0.0.0` **se niega a arrancar** si no hay token configurado.
- El token se canjea por una cookie de sesión firmada, `HttpOnly` y `SameSite`,
  que protege por igual el REST y el WebSocket (el navegador no admite cabeceras
  propias en el handshake de un WebSocket).
- Los intentos de login se limitan por IP y quedan en `logs/monitor_audit.jsonl`.

Para llegar desde fuera de la LAN, usa **Tailscale o WireGuard** en vez de abrir
el puerto. Un token sobre HTTP plano en internet abierto no es protección
suficiente; si aun así se expone, debe ir tras un proxy con TLS y
`monitor.auth.https_only: true`.

### Vistas

| Vista | Contenido |
|---|---|
| **Live** | Recuento por estado, hardware con sparklines, heatmap por núcleo, progreso de batches, jobs activos y consola de eventos |
| **Jobs** | Tabla virtualizada con filtros y panel de detalle: trazas SCF, frames, log y ficha del candidato |
| **Candidatos** | Scatter de tolerancia Goldschmidt vs factor octaédrico con las zonas de aceptación, embudo de cribado y tabla |
| **ML** | Predicción de bandgap con incertidumbre, parity plot frente a DFT y experimento, métricas de los modelos |
| **Estructuras** | Visor 3D (3Dmol.js) de fases, top-8 y estructuras de cada job, con supercelda y celda unidad |
| **Resultados** | Reportes Markdown renderizados y galerías desde los `visualization_manifest.json` |

### Endpoints

| Endpoint | Descripción |
|---|---|
| `GET /api/health` | Montaje de `runs_dir`, frescura del poller, clientes WS |
| `GET /api/jobs` | Jobs paginados, con filtro por estado, búsqueda y orden |
| `GET /api/jobs/converged` | Convergidos ordenados por fórmula |
| `GET /api/jobs/{id}` · `/ping` · `/stats` | Detalle, lectura instantánea, re-parseo |
| `GET /api/jobs/{id}/traces` · `/log` · `/metadata` | Series SCF y frames · cola del log · ficha del candidato |
| `GET /api/summary` · `/api/batches` | Recuento global · por batch, con throughput y ETA |
| `GET /api/system` · `/api/system/history` | Hardware ahora · ventana de 1 hora |
| `GET /api/candidates` | Candidatos del generador, con facetas y cotas de filtro |
| `GET /api/models` · `POST /api/ml/predict` · `GET /api/ml/top8` | Métricas · predicción · comparativa ML/DFT/exp |
| `GET /api/structures` · `/api/structures/content` | Inventario · CIF (convierte los JSON de ASE al vuelo) |
| `GET /api/reports` · `/document` · `/figure` | Documentos y galerías · Markdown · figuras |
| `GET /api/statusfull` · `/api/status/report` | Reportes en texto (los de Telegram) |
| `POST /api/notify/*` | Envío manual a Telegram |
| `WS /ws/events` | Cambios de estado en vivo, con `seq` y aviso de huecos |

**Acciones de control**, destructivas, confirmadas en la UI y registradas en `logs/monitor_audit.jsonl`:

| Endpoint | Descripción |
|---|---|
| `POST /api/jobs/{id}/kill` | Termina los procesos del job |
| `POST /api/jobs/{id}/retry` | Devuelve un job fallido a la cola |
| `POST /api/batches/{id}/start` | Lanza el runner de un batch |

> El PID que guarda `status.json` se verifica contra `/proc/<pid>/cwd` antes de
> usarlo: puede llevar meses escrito y haberse reciclado, y el matador termina
> el grupo de procesos completo del PID que reciba.

> `runs/` y `calculations/` son symlinks a un volumen externo. Si no está
> montado, `GET /api/health` devuelve `runs_mounted: false` y la GUI muestra un
> aviso, en lugar de un panel vacío indistinguible de "no hay trabajo".

## Tests

```bash
# La suite completa
PYTHONPATH=src pytest tests/ -q

# Solo el monitor, el cribado y el empaquetado: los más rápidos
PYTHONPATH=src pytest tests/test_monitor_api.py tests/test_packaging.py \
    tests/test_activity.py tests/test_seguimiento_lote.py \
    tests/test_geometria_abx3.py tests/test_gpaw_setup.py -q

# Con cobertura
PYTHONPATH=src pytest tests/ --cov=src --cov-report=html
```

**531 tests pasan y 7 se saltan; ninguno falla.** Los 7 saltados dependen del
entorno y dicen por qué al saltarse: `.gpw` de r2scan que solo lee la GPAW que
los escribió, y el mezclador MSR1, que únicamente existe en GPAW master.

Los tests no dependen del orden en que corran. Que lo hicieran costó caro:
pytest importa **todos** los ficheros de test durante la recolección, así que
un fichero que sustituía `gpaw` por una maqueta al importarse se la dejaba
puesta a los que corrían antes que él por orden alfabético. Salían fallos como
«'gpaw' is not a package» que no se reproducían en aislamiento. La regla que
queda: las maquetas se instalan dentro de un fixture, nunca al importar el
módulo, y se retiran al terminar.

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

GPLv3, compatible con GPAW y ASE.
