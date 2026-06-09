# Benchmark Fase 2A DFT E+F

Generado: `2026-06-08T22:45:52.118196+00:00`

## Resumen Ejecutivo

- Split recomendado: **4x11** = **4 slots x 11 cores**.
- Throughput agregado: **0.01113 iter/s**.
- t/iter promedio: **361.00 s**.
- Tiempo aproximado para 50 labels a `15` iter: **18.72 h**.
- Tiempo aproximado para batch 0 completo (`143` labels) a `15` iter: **53.53 h**.
- RAM pico: **47.58 GiB**; swap pico: **0.981 GiB**.
- Memoria minima disponible: **15.16 GiB**.
- Recomendacion conservadora para produccion Fase 2A: **2x8** = **2 slots x 8 cores**.
- Motivo: mantiene el contrato operativo de jobs de 8 cores y uso bajo de swap (**0.256 GiB**) con **18.61 GiB** disponibles en el peor punto.
- Splits ok: `6`; abortados por watchdog: `6`; fallidos: `0`; omitidos: `2`.
- Watchdog: RAM usada >= `60.0 GiB`, swap > `10.0 GiB`, memoria disponible < `4.0 GiB`.
- Las infografias del dashboard excluyen splits eliminados; solo grafican configuraciones `ok`.

## Conclusion Operativa

- Usar **2x8** como configuracion inicial de produccion para Fase 2A.
- No relanzar el benchmark completo desde VSCode; si se necesita otro barrido, correrlo fuera de la sesion grafica.
- **4x11** queda como techo de throughput medido, util para corridas manuales controladas si se acepta salir del esquema estricto de 8 cores por job.
- No usar configuraciones con muchos jobs de 1-2 cores: duplican memoria, procesos y presion de swap sin mejorar estabilidad.

## Tabla Maestra

| split | mode | slots | cores/slot | status | jobs ok | t/iter s | throughput | RAM pico GiB | swap pico GiB | motivo |
|---|---|---:|---:|---|---:|---:|---:|---:|---:|---|
| `1x44` | `physical` | 1 | 44 | `ok` | 1 | 111.0 | 0.00901 | 36.28 | 0.986 | maxiter_reached_split_stopped |
| `2x22` | `physical` | 2 | 22 | `ok` | 2 | 202.0 | 0.0099 | 40.47 | 0.983 | maxiter_reached_split_stopped |
| `3x14` | `physical` | 3 | 14 | `ok` | 3 | 303.0 | 0.0099 | 49.44 | 0.982 | maxiter_reached_split_stopped |
| `4x11` | `physical` | 4 | 11 | `ok` | 4 | 361.0 | 0.01113 | 47.58 | 0.981 | maxiter_reached_split_stopped |
| `5x8` | `physical` | 5 | 8 | `aborted_by_watchdog` | 0 |  | 0.0 | 61.6 | 1.097 | ram_used_gb=61.60 >= 60.00 |
| `8x5` | `physical` | 8 | 5 | `aborted_by_watchdog` | 0 |  | 0.0 | 58.77 | 1.516 | mem_available_gb=3.97 < 4.00 |
| `11x4` | `physical` | 11 | 4 | `aborted_by_watchdog` | 0 |  | 0.0 | 61.5 | 1.476 | ram_used_gb=61.50 >= 60.00 |
| `22x2` | `physical` | 22 | 2 | `aborted_by_watchdog` | 0 |  | 0.0 | 59.65 | 0.254 | mem_available_gb=3.09 < 4.00 |
| `44x1` | `physical` | 44 | 1 | `skipped` | 0 |  | 0.0 |  |  | manual_skip_after_repeated_vscode_gpu_crash |
| `1x8` | `phase2_8core` | 1 | 8 | `ok` | 1 | 174.0 | 0.00575 | 24.69 | 0.256 | maxiter_reached_split_stopped |
| `2x8` | `phase2_8core` | 2 | 8 | `ok` | 2 | 226.5 | 0.00883 | 44.12 | 0.256 | maxiter_reached_split_stopped |
| `3x8` | `phase2_8core` | 3 | 8 | `aborted_by_watchdog` | 0 |  | 0.0 | 59.34 | 0.256 | mem_available_gb=3.40 < 4.00 |
| `4x8` | `phase2_8core` | 4 | 8 | `aborted_by_watchdog` | 0 |  | 0.0 | 60.57 | 0.273 | ram_used_gb=60.57 >= 60.00 |
| `22x1` | `added_1core` | 22 | 1 | `skipped` | 0 |  | 0.0 | 37.9 | 6.702 | manual_elimination_after_vscode_gpu_crash; flight_recorder_swap_peak_gb=6.702; dft_processes=68; xdg_desktop_portal_gpf_amdgpu_reset |

## Splits Eliminados

Estos splits no se incluyen en las infografias. Se conservan aqui solo como auditoria y para evitar relanzarlos.

| split | status | motivo | RAM pico GiB | swap pico GiB | memoria minima disponible GiB |
|---|---|---|---:|---:|---:|
| `5x8` | `aborted_by_watchdog` | ram_used_gb=61.60 >= 60.00 | 61.6 | 1.097 | 1.14 |
| `8x5` | `aborted_by_watchdog` | mem_available_gb=3.97 < 4.00 | 58.77 | 1.516 | 3.97 |
| `11x4` | `aborted_by_watchdog` | ram_used_gb=61.50 >= 60.00 | 61.5 | 1.476 | 1.23 |
| `22x2` | `aborted_by_watchdog` | mem_available_gb=3.09 < 4.00 | 59.65 | 0.254 | 3.09 |
| `44x1` | `skipped` | manual_skip_after_repeated_vscode_gpu_crash |  |  |  |
| `3x8` | `aborted_by_watchdog` | mem_available_gb=3.40 < 4.00 | 59.34 | 0.256 | 3.4 |
| `4x8` | `aborted_by_watchdog` | ram_used_gb=60.57 >= 60.00 | 60.57 | 0.273 | 2.17 |
| `22x1` | `skipped` | manual_elimination_after_vscode_gpu_crash; flight_recorder_swap_peak_gb=6.702; dft_processes=68; xdg_desktop_portal_gpf_amdgpu_reset | 37.9 | 6.702 | 24.84 |

## Dashboard

- [Dashboard PNG](phase2_force_benchmark_dashboard.png)
- [Dashboard PDF](phase2_force_benchmark_dashboard.pdf)

Nota: el dashboard muestra solo splits `ok`; los eliminados estan documentados en la seccion anterior.

## Datos

- [CSV](phase2_force_benchmark.csv)
- [JSON](phase2_force_benchmark.json)

## Nota

Este benchmark decide concurrencia segura. No produce etiquetas MACE ni modifica estados oficiales de Fase 2A.
