![](docs/screenshots/monitor-dft-candidatos.png)

![](docs/screenshots/monitor-dft-estructura.png)

![](docs/screenshots/monitor-dft-cribado.png)

# BUHO: descubrimiento de perovskitas fotovoltaicas

Busca perovskitas de haluro ABX₃ con un bandgap útil para células solares. No
las prueba una a una: genera composiciones por millares, las criba con modelos
baratos, calcula con DFT solo las que sobreviven, y usa esos cálculos para
cribar mejor la vuelta siguiente.

El espacio de búsqueda son 5 cationes A (Cs, Rb, K, MA, FA), 3 metales B (Pb,
Sn, Ge) y 3 haluros X (I, Br, Cl), puros o mezclados dentro de cada sitio. Con
fracciones continuas el espacio es infinito, así que se recorre por lotes
reproducibles en vez de enumerarlo.

Motor de cálculo: **GPAW**. Estructuras: **ASE**. Se conduce desde una
aplicación de escritorio o desde la línea de comandos.

## Las dos mitades

El repositorio hace dos cosas distintas, y entender dónde acaba una y empieza la
otra explica casi todo lo demás.

**Descubrimiento** (`src/buho/`): mucho material, poco cálculo por material.
Recorre el espacio composicional buscando candidatos prometedores. El DFT que
usa es deliberadamente barato: PBE, Γ-only, single-point. No busca el número
correcto, busca separar lo que merece la pena de lo que no.

**Caracterización** (`src/dft_cspbi3/`): un material, mucho cálculo. Cuando un
candidato pasa el cribado, este workflow de 26 pasos lo caracteriza en serio:
relajación, SCF, bandas, DOS, acoplamiento espín-órbita, meta-GGA (SCAN,
r²SCAN), híbridos (HSE06), fonones, masas efectivas, límite de
Shockley-Queisser. Ahí sí importa el número exacto.

El puente entre las dos son las **top-8**: los mejores candidatos del cribado
pasan al workflow profundo, y lo que este devuelve reentrena el modelo que hace
el cribado.

## El ciclo

```
     generar             cribar           calcular        aprender
  ─────────────   ───────────────────   ────────────   ─────────────
  Composiciones   Cascada de 3 tiers:   DFT barato:    Reentrenar el
  ABX₃ mixtas,    física, surrogate     PBE, Γ-only,   surrogate con
  por lotes       y MLFF                single-point   lo calculado
        ▲                                                    │
        └────────────────────────────────────────────────────┘
```

Cada vuelta criba mejor, porque el modelo aprende de los cálculos que él mismo
pidió. Eso es lo que separa el aprendizaje activo de un simple «predecir y
filtrar»: el modelo no espera datos, los encarga.

### 1. Generación

`src/buho/generator/heuristic_generator.py` compone candidatos ABX₃ mezclando
dentro de cada sitio: dos cationes A, dos metales B, o hasta tres haluros X.
Las fracciones pueden venir de una rejilla discreta o muestrearse de forma
continua, que es el modo por defecto.

Un candidato mixto sale con sus fracciones por sitio, no como una etiqueta
suelta: `Cs₀.₅₂FA₀.₄₈SnI₃` son dos cationes A con sus proporciones, y de ahí se
derivan radios y electronegatividades efectivos. Los radios son Shannon 1976,
con Kieslich 2014 para MA y FA.

El muestreo es reproducible: la semilla de cada lote es `random_seed + N`, así
que el lote 7 sale igual hoy que dentro de un año. Un registro persistente evita
repetir composiciones ya vistas entre lotes.

### 2. Cribado

`src/buho/screening/cascade.py` es una torre de tres tiers. Lo importante no es
que puntúe, sino que **cada tier descarta y el siguiente solo evalúa lo que
sobrevivió**: ahí está todo el ahorro.

| Tier | Qué mira | Coste por candidato |
|---|---|---|
| 0. Física | Factor de Goldschmidt (0.80–1.10), octaédrico (0.40–0.90), neutralidad de carga, volumen | µs |
| 1. Surrogate | Bandgap predicho ± σ contra la ventana fotovoltaica de 1.1–1.8 eV | ~2 ms |
| 2. MLFF | Se construye la estructura y MEGNet/M3GNet dan energía de formación | ~0.5 s |

El Tier 1 criba **con holgura de σ**, y es una decisión deliberada. El surrogate
tiene un MAE de unos 0.31 eV y la ventana mide 0.7 eV de ancho: cribar por la
estimación puntual tiraría materiales cuyo bandgap real sí cae dentro. Un
candidato con Eg = 0.95 ± 0.18 eV sigue siendo plausible frente a un límite de
1.1 eV, así que pasa. El Tier 2 aplica la misma idea con la discrepancia entre
MEGNet y M3GNet.

Los descartados **no desaparecen**: siguen en el resultado con `dropped_at_tier`
y `drop_reason`, porque sin esa traza no se puede auditar por qué se fue un
material. Todo se vuelca a `cascade_scores.csv`.

El ranking final combina tres términos:

```
total = band_score(cercanía a 1.45 eV) + stab_score(energía de formación) + β·σ
```

Ese último término es la exploración: premia a los candidatos sobre los que el
modelo está inseguro, no solo a los que ya parecen buenos. Es una adquisición
tipo UCB.

### 3. Cálculo

Los supervivientes se materializan como cristales (`src/buho/structure/`): celda
unitaria para composiciones puras, supercelda 2×2×2 de 40 átomos para las
mezclas. MA y FA se sustituyen por un pseudoátomo, porque una molécula orgánica
completa no cabe en el presupuesto de un cribado.

El DFT de esta fase es **a propósito barato**: PBE, `ecut` 300 eV, malla 2×2×2 o
Γ-only en superceldas, y single-point en lugar de relajación. r²SCAN se descartó
aquí por coste: a un core son ~195 s por iteración, unos cinco días para 482
superceldas. Se reserva para la caracterización profunda.

`src/buho/dft_jobs/` prepara los directorios y un runner los lanza con la
concurrencia que aguante la máquina, que se mide con `buho bench machine`.

### 4. Aprendizaje

`src/buho/active_learning/batch_loop.py` cierra el ciclo. Recoge los resultados
DFT con una guarda de valores atípicos, anexa solo las filas fiables al conjunto
de entrenamiento y reentrena el surrogate, que es un ensemble de RandomForest y
GradientBoosting con incertidumbre por bootstrap. Árboles poco profundos y
pocas muestras por hoja, porque el conjunto de datos es pequeño y sobreajustar
sería fácil.

Cada lote deja su rastro en `data/batches/batch_NNN/`: los candidatos, las
puntuaciones de la cascada, los seleccionados, los resultados y un manifiesto.

### 5. Un potencial propio

El Tier 2 del cribado se apoya en MEGNet y M3GNet, que son modelos generales:
saben de todo un poco y de perovskitas de haluro nada en particular. La Fase 2A
(`src/buho/phase2_force/`) existe para sustituirlos por uno propio.

En vez de pedir al DFT solo la energía, le pide **energía y fuerzas** de cada
configuración, que es lo que necesita un potencial interatómico para aprender.
Con ese conjunto se afina un MACE partiendo de MACE-MP-0. Sin Hubbard U y sin
relajación, para que las etiquetas sean consistentes con los datos con los que
se preentrenó el modelo base.

```bash
buho phase2-force select      # qué candidatos etiquetar
buho phase2-force prepare     # montar los trabajos
buho phase2-force run         # calcular
buho phase2-force collect     # armar el dataset
buho phase2-force mace-train  # afinar el potencial
```

Es la parte que más cómputo ha consumido del proyecto: los lotes viven en
`local_runs/phase2_force/batch_NNN/`, con un directorio por candidato. El
runner se vigila solo: si un trabajo pasa horas sin escribir log de SCF, un
watchdog lo mata y lo marca, en vez de dejarlo ocupando núcleos sin avanzar.

## Caracterización profunda

Cuando un candidato pasa el cribado, `src/dft_cspbi3/` lo caracteriza en serio:
26 pasos encadenados, desde la relajación hasta el límite de eficiencia.

```
relax → relax_sym → scf → bands → dos → soc → soc_pbe
scan → scan_soc → soc_scan → r2scan → soc_r2scan
hse06 → hse06_nonscf → soc_hse06 → hse06_scissor
hessian → phonons → pes → loto
formation_energy → effective_masses → optical → sq_limit
oghma_device → score
```

```bash
buho calc steps      # los pasos y el estado de cada artefacto
buho calc run        # el workflow completo
buho calc step scf   # un paso suelto
```

El material de validación es α-CsPbI₃, y sobre él está medida la metodología:
parámetros, cancelación de errores entre SOC y HSE06 en el plomo, convergencia
de `ecut` y malla k, y las equivalencias con VASP para quien venga de ahí. Todo
eso está en **[docs/metodologia-dft.md](docs/metodologia-dft.md)**.

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
- **Trabajos**: cada cálculo con su estado, sus artefactos y sus logs.
- **Diagnóstico**: qué ve el motor, dónde tiene los datos y qué le falta.

Se descarga desde [Releases](https://github.com/RxWhizz/DFT/releases). Hay una
versión de escritorio y otra que se abre en el navegador. La puesta en marcha,
los endpoints, el acceso remoto y dónde van las claves están en
**[docs/monitor.md](docs/monitor.md)**.

## Estructura del repositorio

```
DFT/
├── src/
│   ├── buho/                     # El pipeline de descubrimiento
│   │   ├── generator/            #   candidatos ABX3 puros y mixtos
│   │   ├── screening/cascade.py  #   torre de cribado de 3 tiers
│   │   ├── structure/            #   construcción de la celda cristalina
│   │   ├── dft_jobs/             #   prepara los trabajos DFT
│   │   ├── filters/              #   Goldschmidt, octaédrico, carga, volumen
│   │   ├── scoring/              #   score heurístico previo al DFT
│   │   ├── active_learning/      #   acumula, reentrena, prepara el siguiente
│   │   ├── phase2_force/         #   etiquetado DFT de energía y fuerzas
│   │   │                         #   para sembrar un potencial MACE
│   │   ├── bench/                #   calibración de rendimiento por máquina
│   │   ├── cli/                  #   los 30 grupos de comandos
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
├── config/generator.yaml         # Espacio químico, cribado y adquisición
├── configs/                      # Parámetros DFT y del monitor
├── structures/                   # Fases de referencia y top 8
├── models/                       # Surrogates entrenados (.pkl + métricas)
└── tests/                        # 541 tests
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

Los datasets por defecto de GPAW ya traen la valencia que hace falta, así que no
hay que configurar nada:

| Dataset | Valencia | Electrones |
|---|---|---|
| `Cs.PBE` | 5s²5p⁶6s¹ | 9 |
| `Pb.PBE` | 5d¹⁰6s²6p² | 14, con el 5d dentro: |
| `I.PBE` | 5s²5p⁵ | 7 |


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



