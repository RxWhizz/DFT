# Phase 2A Smoke Benchmark

Generated: `2026-06-08T06:34:51.240938+00:00`

Startup gate: **PASS**

Reason: All smokes passed; it is safe to start the runner with the configured storage policy.

## Checks

| Check | Status | Seconds | Error |
|------|--------|---------|-------|
| `py_compile` | `pass` | 0.033 |  |
| `direct_tests` | `pass` | 0.005 |  |
| `gpaw_env` | `pass` | 0.275 |  |
| `selection` | `pass` | 0.020 |  |
| `method_plan` | `pass` | 0.001 |  |
| `prepare_and_runner_dry_run` | `pass` | 0.882 |  |
| `active_processes` | `pass` | 0.097 |  |
| `storage` | `pass` | 0.000 |  |

## Method Coverage

- Non-Sn path: `r2scan`.
- Sn path: `U2p00`, `U2p25`, `U2p50`, `U2p75` sequential inside one logical job.
- Logical jobs in smoke benchmark: `10`.
- Smoke runs dir: `/media/luis-ochoa/Nuevo vol/dft/runs/_phase2_force_smokes/20260608T063450Z`.

## Scheduling Benchmark

- Recommended split from previous benchmark: `5x8`.
- Slots: `5`.
- Cores/slot: `8`.
- Total MPI cores: `40`.
- Reference throughput: `0.7485` iter/s.
- Reference peak RAM: `16.15` GB.
- Source: `reports/performance_benchmark.csv`.

## Phase 2A Workload

- Candidates: `1000`.
- Batches: `20`.
- Expected DFT labels: `2743`.
- Sn per batch min/max: `22` / `32`.

## Storage And Active Runner Gate

- Default runs dir: `/media/luis-ochoa/Nuevo vol/dft/runs/phase2_force`.
- Repo free: `18.41` GB.
- External volume: `/media/luis-ochoa/Nuevo vol`.
- External mounted: `True`.
- Require external: `True`.
- Official runs dir exists: `True`.
- Official jobs visible: `1000`.
- Official statuses: `{'pending': 1000}`.

## Artifacts

- JSON: [`phase2_force_smoke_benchmark.json`](phase2_force_smoke_benchmark.json)
- PNG: [`phase2_force_smoke_benchmark.png`](phase2_force_smoke_benchmark.png)
- PDF: [`phase2_force_smoke_benchmark.pdf`](phase2_force_smoke_benchmark.pdf)
