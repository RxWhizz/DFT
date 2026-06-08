# Informe De Memoria — Fase 2A DFT E+F(+stress)

Fecha: `2026-06-07`

## Resumen

La corrida real acotada de 10 candidatos con setup `5 slots x 8 cores` fue detenida manualmente porque la memoria subió hasta casi saturar la RAM física:

- RAM observada antes de parar: ~`60 GiB` usados de `62 GiB`.
- Swap observado antes de parar: ~`15 GiB` usados.
- RAM después de parar: ~`4.3 GiB` usados y ~`57 GiB` libres.
- Procesos activos durante la prueba: `5` jobs DFT simultáneos x `8` procesos MPI = `40` procesos `python input.py`.

La causa no es el `FIRE` por sí solo. La causa dominante es que Fase 2A cambió de una carga ligera tipo Fase 1 a una carga mucho más pesada:

- superceldas de `40` átomos,
- r2SCAN/r2SCAN+U,
- ondas planas `PW(450)`,
- malla `2x2x2` k-points,
- `8` ranks MPI por job,
- paralelización solo por k-points: `{"kpt": 8, "domain": 1, "band": 1}`,
- `5` jobs simultáneos.

## Evidencia Del Setup

El template generado para Fase 2A usa:

- `PW(450)`.
- `xc = MGGA_X_R2SCAN+MGGA_C_R2SCAN`.
- `kpts = [2, 2, 2]` para estructuras de más de 10 átomos.
- `parallel = {"kpt": 8, "domain": 1, "band": 1}` en los jobs de 8 cores.
- `FIRE(...).run(fmax=0.0, steps=2)`.

Referencia local: `src/buho/phase2_force/prepare.py`, bloque `_kpts_for_atoms()` y `_calc_kwargs()`.

El runner lanza cada job como:

```bash
mpiexec -n 8 python input.py
```

Referencia local: `src/buho/phase2_force/runner.py`, función `launch_job()`.

## Tamaño De Los 10 Candidatos Probados

Los primeros 10 candidatos del batch 0 son todos superceldas `2x2x2` de `40` átomos. Esto es importante: no son celdas primitivas de 5 átomos.

| candidato | fórmula | átomos | etiquetas esperadas |
|---|---:|---:|---:|
| `a70c82b021986f18` | `Cs0.94MA0.059SnI3` | 40 | 4 U-scan |
| `ef8bdab15faa2db3` | `FAPbBr0.25Cl0.5I0.253` | 40 | 1 r2SCAN |
| `c7818f9146316112` | `MA0.39Rb0.61SnI3` | 40 | 4 U-scan |
| `830dbc192e4e9fd9` | `MASnBr0.35I0.653` | 40 | 4 U-scan |
| `afb22267695ea19d` | `Cs0.54MA0.46SnI3` | 40 | 4 U-scan |
| `24f88dd9663a6ba0` | `FA0.5MA0.5PbCl3` | 40 | 1 r2SCAN |
| `2c09cab8e268c3e7` | `CsGe0.094Sn0.91I3` | 40 | 4 U-scan |
| `4ce24f2543f721ab` | `FA0.41Rb0.59SnI3` | 40 | 4 U-scan |
| `8777a166c1c8a4be` | `MASnBr0.2I0.83` | 40 | 4 U-scan |
| `7564c462877d2bcb` | `Cs0.59FA0.41SnI3` | 40 | 4 U-scan |

Nota: el U-scan de Sn no multiplica la memoria dentro de un candidato, porque las U se ejecutan secuencialmente dentro del mismo job lógico. Sí aumenta mucho el tiempo total.

## Estimaciones Internas De GPAW

GPAW alcanzó a escribir estimaciones de memoria en algunos `r2scan.txt` antes de detener la prueba.

| caso | coeficientes PW | bands | valencia | calculator | wavefunctions | density |
|---|---:|---:|---:|---:|---:|---:|
| `ef8bdab15.../r2scan` | 120,713-120,958 | 208 | 352 e- | 1,452.73 MiB | 847.30 MiB | 491.92 MiB |
| `c7818f91.../U2p00` | 151,323-151,684 | 208 | n/d | 1,850.70 MiB | 1,053.50 MiB | 660.78 MiB |
| `830dbc19.../U2p00` | 140,233-140,464 | 208 | n/d | 1,754.55 MiB | 978.71 MiB | 640.02 MiB |

Interpretación:

- Cada rank MPI puede estar alrededor de `1.5-1.9 GiB` solo para el cálculo GPAW, antes de contar overhead de Python/MPI/BLAS/cache.
- Con `8` ranks por job, un job puede ocupar del orden de `12-15 GiB` en la parte pesada.
- Con `5` jobs simultáneos, la demanda esperada cae naturalmente en `60-75 GiB`, que coincide con la observación de `60 GiB` RAM + `15 GiB` swap.

Además, `ps` mostró varios ranks individuales con RSS de `2.4-3.1 GiB` durante la prueba, así que el overhead real puede superar la estimación inicial de GPAW.

## Por Qué El Benchmark 5x8 Anterior No Predijo Esto

El benchmark previo en `reports/performance_benchmark.csv` marcaba `5x8` como recomendado con RAM pico `16.15 GB`. Ese dato sigue siendo útil para la carga que se midió ahí, pero no representa esta nueva carga Fase 2A.

La diferencia clave:

- Fase 1: carga más ligera, orientada a single-points/flujo anterior.
- Fase 2A: r2SCAN/r2SCAN+U + fuerzas + superceldas de 40 átomos + 2 pasos FIRE + `2x2x2` k-points.

Por eso `5x8` pasó de ser una buena configuración de throughput a ser una configuración agresiva de memoria.

## Factores Que Más Pesan

1. `40` átomos por estructura
   Las estructuras mixtas se construyen como superceldas `2x2x2`. Eso multiplica el tamaño base frente a una celda ABX3 de 5 átomos.

2. `2x2x2` k-points en la supercelda
   GPAW reporta `8 k-points` y ~`120k-151k` coeficientes de ondas planas.

3. `PW(450)`
   El cutoff aumenta el número de coeficientes PW y por tanto memoria de wavefunctions/eigensolver.

4. r2SCAN/r2SCAN+U
   Meta-GGA requiere más campos/grids que PBE. En las estimaciones, wavefunctions + eigensolver + density dominan.

5. Paralelización `kpt=8, domain=1`
   Cada rank trabaja k-points, pero muchas estructuras de datos de densidad/Hamiltoniano/mixer no se distribuyen como en domain decomposition. Eso favorece throughput, pero replica memoria.

6. `5` jobs simultáneos
   El problema escala casi linealmente con slots. `5 x 8 ranks` produjo `40` procesos GPAW pesados.

## Recomendación Operativa

No usar `5x8` para Fase 2A con la configuración actual.

Recomendación inmediata:

- Correr Fase 2A con `2 slots x 8 cores`.
- Probar `3 slots x 8 cores` solo con watchdog de RAM y sin swap creciente.
- Mantener `--limit` en pruebas cortas hasta tener benchmark específico de Fase 2A.

Comando sugerido para la siguiente prueba controlada:

```bash
PYTHONPATH=src python3 scripts/phase2_force_runner.py \
  --batch-id 0 \
  --slots 2 \
  --cores 8 \
  --limit 10 \
  --resume \
  --start-real
```

## Próximas Pruebas Recomendadas

1. Benchmark Fase 2A real de memoria:
   - `1x8`, `2x8`, `3x8`, quizá `4x8`.
   - Medir RAM pico, swap pico, tiempo por iteración y etiquetas convergidas.

2. Probar parallel layouts menos replicantes:
   - `{"kpt": 4, "domain": 2, "band": 1}`
   - `{"kpt": 2, "domain": 4, "band": 1}`
   Solo si GPAW 24.6 se mantiene estable con r2SCAN.

3. Evaluar k-points para seed MACE:
   - `2x2x2` es caro.
   - `1x1x1` en supercelda podría ser suficiente para una primera semilla E+F si se documenta como menor fidelidad.

4. Considerar estrategia de dos niveles:
   - pre-relax o smoke barato,
   - etiqueta r2SCAN final solo para candidatos que sobrevivan.

## Conclusión

La memoria alta es esperada con el setup actual. El cuello de botella no es un leak evidente: es la combinación de superceldas de 40 átomos, r2SCAN/r2SCAN+U, `PW(450)`, `2x2x2` k-points y 40 procesos MPI simultáneos. Para esta fase, `5x8` debe tratarse como demasiado agresivo hasta que se pruebe un layout de paralelización más eficiente o se reduzca fidelidad/k-points en el smoke inicial.
