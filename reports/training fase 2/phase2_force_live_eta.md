# ETA vivo Fase 2A

Generado: `2026-06-09T02:52:08.888217+00:00`
Lote: `batch_000`

## Resumen ejecutivo

- ETA vivo para `143` labels a `15` iter/label: **116.94 h**.
- Throughput vivo productivo: **0.004988 iter/s**.
- Labels: `0` completos, `1` fallidos, `4` corriendo.
- Slots productivos: `3`; slots sin iteraciones medibles: `0` bloqueados, `1` calentando.
- Progreso SCF activo: `81` / `2145` iter nominales.
- RAM usada: **52.38 GiB**; RAM disponible: **10.36 GiB**; swap usado: **0.0052 GiB**.

## Jobs activos

| candidato | formula | label | estado | iter | t/iter min | ultima iter | log age min |
|---|---|---|---|---:|---:|---|---:|
| `830dbc192e4e9fd9` | `MASnBr0.35I0.653` | `U2p00` | `running` | 23/15 | 11.6 | 19:42:22 | 9.8 |
| `afb22267695ea19d` | `Cs0.54MA0.46SnI3` | `U2p00` | `running` | 0/15 | n/d |  | 5.2 |
| `c7818f9146316112` | `MA0.39Rb0.61SnI3` | `U2p00` | `running` | 25/15 | 10.7 | 19:43:49 | 8.3 |
| `ef8bdab15faa2db3` | `FAPbBr0.25Cl0.5I0.253` | `r2scan` | `running` | 33/15 | 8.4 | 19:47:14 | 4.9 |

## Jobs calentando

- `afb22267695ea19d` `Cs0.54MA0.46SnI3` esta en `U2p00` sin iteraciones aun, pero dentro del umbral de self-heal (60 min).

## Notas

- Este ETA usa solo labels en ejecucion con iteraciones SCF medibles.
- Los labels fallidos no se cuentan como completados; quedan como trabajo nominal pendiente para reintento.
- El ETA es operativo, no una metrica MACE ni una etiqueta DFT.
