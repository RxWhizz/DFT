# Resumen de Rendimiento DFT

Generado: 2026-06-06 20:34

## Resumen Ejecutivo

- Configuracion recomendada: **5x8** = **5 slots x 8 cores**, GPAW 24.6, domain=8, HT apagado.
- Mejor throughput con cores fisicos: **0.7485 iter/s**, **16.15 GB** RAM pico y **5.0 h** estimadas para 482 superceldas.
- Mejor throughput con HT observado: **4x22** con **0.5595 iter/s**, por debajo del optimo fisico.
- Interpretacion: PW-DFT queda limitado por FFT/ancho de banda de memoria; HT agrega contencion y presion de RAM sin mejorar throughput.

## Tabla Maestra

| mode     | split   |   slots |   cores per slot |   total cores |   jobs ok |   jobs total |   t iter s |   throughput iter s |   peak ram gb |   eta 482 h |
|:---------|:--------|--------:|-----------------:|--------------:|----------:|-------------:|-----------:|--------------------:|--------------:|------------:|
| physical | 1x44    |       1 |               44 |            44 |         1 |            1 |       2.3  |              0.4348 |         13.34 |         8.6 |
| physical | 2x22    |       2 |               22 |            44 |         2 |            2 |       3.05 |              0.6559 |         13.82 |         5.7 |
| physical | 3x14    |       3 |               14 |            42 |         3 |            3 |       4.4  |              0.6818 |         14.3  |         5.5 |
| physical | 4x11    |       4 |               11 |            44 |         4 |            4 |       5.45 |              0.7409 |         15.29 |         5.1 |
| physical | 5x8     |       5 |                8 |            40 |         5 |            5 |       6.68 |              0.7485 |         16.15 |         5   |
| physical | 8x5     |       8 |                5 |            40 |         8 |            8 |      11.44 |              0.703  |         19.02 |         5.3 |
| physical | 11x4    |      11 |                4 |            44 |        11 |           11 |      15.77 |              0.6976 |         24.23 |         5.4 |
| ht       | 2x44    |       2 |               44 |            88 |         2 |            2 |       4.35 |              0.4598 |         25.38 |         8.2 |
| ht       | 4x22    |       4 |               22 |            88 |         4 |            4 |       7.15 |              0.5595 |         26.33 |         6.7 |
| ht       | 8x11    |       8 |               11 |            88 |         8 |            8 |      15.16 |              0.5284 |         31.07 |         7.1 |
| ht       | 11x8    |      11 |                8 |            88 |        11 |           11 |      19.89 |              0.5531 |         35.53 |         6.8 |

## Escalamiento Por Domain

|   domain cores |   wall s |   iters |   t iter s |   speedup vs 1core |
|---------------:|---------:|--------:|-----------:|-------------------:|
|              1 |    266.1 |      12 |       20.1 |               1    |
|              2 |    147.5 |      12 |       10.9 |               1.8  |
|              4 |     81.5 |      12 |        5.9 |               3.27 |
|              8 |     48.1 |      12 |        3.1 |               5.53 |

## Prueba De Concurrencia A 1 Core

|   slots |   avg t iter s |   throughput iter s |
|--------:|---------------:|--------------------:|
|       1 |           30.6 |              0.0327 |
|       2 |           55.3 |              0.0369 |
|       4 |          132.1 |              0.0306 |

## Figuras

- [Throughput bars](figures/performance_throughput.png)
- [RAM vs throughput tradeoff](figures/performance_ram_tradeoff.png)
- [ETA for 482 supercells](figures/performance_eta_482.png)
- [Domain scaling](figures/performance_domain_scaling.png)
- [1-core concurrency](figures/performance_concurrency_1core.png)
- [Dashboard](figures/performance_dashboard.png)

## Archivos De Datos

- [Clean benchmark CSV](performance_benchmark.csv)
- [Clean benchmark JSON](performance_benchmark.json)
- [Domain scaling CSV](performance_domain_scaling.csv)
- [1-core concurrency CSV](performance_concurrency_1core.csv)

## Fuentes Crudas

- [Physical-core sweep log](sweep_benchmark.log)
- [HT sweep log](sweep_ht_benchmark.log)
- [GPAW 24.6 benchmark log](gpaw246_benchmark.log)
- [Concurrency benchmark JSON](concurrency_benchmark.json)

## Decision

Usar **5x8** en produccion. Es la configuracion ganadora en throughput entre splits fisicos y tambien la de menor ETA (5.0 h). Mantener HT apagado para esta carga.
