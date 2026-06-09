# Training Fase 2 — MACE Fine-Tune

Esta carpeta es el tablero visual de Fase 2. Su objetivo es seguir el paso de la Fase 1
composicional a un modelado estructura-consciente con baseline **MACE-MP-0**, generación
de fases/polimorfos, etiquetado DFT con energía + fuerzas + stress y fine-tune MACE.

## Estado Actual

- Fase 1 cerrada: batches `0, 1, 2, 3, 4`.
- DFT continuo: `2508/2508` convergidos, `0` fallidos.
- Dataset surrogate: `3008` puntos.
- Motivo de paro: `convergencia (test_mae estancado 2 batches)`.
- Métrica final Fase 1: `test_mae=0.01604 eV/átomo`, `overfit_ratio=1.021`.
- Métricas reales MACE: **no disponibles todavía**.
- Etiquetas DFT Fase 2A: `0` labels,
  `0` candidatos únicos.
- Shortlist Fase 2A: `1000` candidatos,
  `20` lotes,
  `2743` etiquetas DFT esperadas.

Nota crítica: los single-points de Fase 1 son cúbicos idealizados y no contienen
fuerzas/stress. Sirven para el surrogate composicional, pero no entrenan MACE directamente.

## Artefactos Contrato

- Dataset MACE: `data/mace_finetune/phase2_seed.extxyz`.
- Splits: `data/mace_finetune/splits.json`.
- Métricas: `reports/training fase 2/mace_phase2_metrics.json`.
- Modelo: `models/mace_phase2_finetuned.model`.
- Salidas por fase: `runs/phase2_mace/{candidate_id}/{phase}/relaxed.cif, relax.log, metrics.json`.

## Diagnósticos Operativos

- [Benchmark Fase 2A](phase2_force_benchmark.md): barrido de concurrencia con watchdog anti-swap y recomendación numérica.
- [Dashboard benchmark Fase 2A](phase2_force_benchmark_dashboard.pdf): panel tipo performance dashboard con throughput, RAM, swap y KPIs; grafica solo splits `ok`.
- [ETA vivo Fase 2A](phase2_force_live_eta.md): estimación operativa desde los `r2scan.txt` activos.
- [Dashboard ETA vivo Fase 2A](phase2_force_live_eta.pdf): progreso SCF activo, t/iter y ETA del lote actual.
- Conclusión benchmark Fase 2A: usar `2x8` como configuración conservadora de producción; `4x11` queda como techo de throughput medido para corridas manuales controladas. Los splits eliminados se documentan solo en el Markdown del benchmark.
- [Informe de memoria Fase 2A](phase2_force_memory_report.md): explica por qué el setup `5x8` saturó RAM/swap en r2SCAN E+F.
- [Smoke benchmark Fase 2A](phase2_force_smoke_benchmark.md): validación seca de 10 jobs lógicos y cobertura de métodos.

## Regeneración

El tablero se regenera con `scripts/generate_phase2_training_report.py`. En esta máquina se
usó el entorno `gpaw246` porque el Python del sistema no tiene matplotlib:

```bash
MPLCONFIGDIR=/tmp/mpl-phase2 /home/luis-ochoa/miniforge3/envs/gpaw246/bin/python3 scripts/generate_phase2_training_report.py
```

## Figuras

| Figura | Archivos | Estado |
|--------|----------|--------|
| `mace_phase2_dashboard` | [mace_phase2_dashboard.png](mace_phase2_dashboard.png) / [mace_phase2_dashboard.pdf](mace_phase2_dashboard.pdf) | phase1_context |
| `dataset_coverage` | [dataset_coverage.png](dataset_coverage.png) / [dataset_coverage.pdf](dataset_coverage.pdf) | phase1_context |
| `phase_candidate_funnel` | [phase_candidate_funnel.png](phase_candidate_funnel.png) / [phase_candidate_funnel.pdf](phase_candidate_funnel.pdf) | planned_placeholder |
| `mace_baseline_benchmark` | [mace_baseline_benchmark.png](mace_baseline_benchmark.png) / [mace_baseline_benchmark.pdf](mace_baseline_benchmark.pdf) | pending_mace_data |
| `training_loss` | [training_loss.png](training_loss.png) / [training_loss.pdf](training_loss.pdf) | pending_mace_data |
| `energy_parity` | [energy_parity.png](energy_parity.png) / [energy_parity.pdf](energy_parity.pdf) | pending_mace_data |
| `force_parity` | [force_parity.png](force_parity.png) / [force_parity.pdf](force_parity.pdf) | pending_mace_data |
| `force_residuals` | [force_residuals.png](force_residuals.png) / [force_residuals.pdf](force_residuals.pdf) | pending_mace_data |
| `stress_parity` | [stress_parity.png](stress_parity.png) / [stress_parity.pdf](stress_parity.pdf) | pending_mace_data |
| `phase_ranking_accuracy` | [phase_ranking_accuracy.png](phase_ranking_accuracy.png) / [phase_ranking_accuracy.pdf](phase_ranking_accuracy.pdf) | pending_mace_data |
| `relaxation_stability` | [relaxation_stability.png](relaxation_stability.png) / [relaxation_stability.pdf](relaxation_stability.pdf) | pending_mace_data |
| `learning_curve` | [learning_curve.png](learning_curve.png) / [learning_curve.pdf](learning_curve.pdf) | pending_mace_data |
| `benchmark_runtime` | [benchmark_runtime.png](benchmark_runtime.png) / [benchmark_runtime.pdf](benchmark_runtime.pdf) | pending_mace_data |
| `phase2_force_benchmark_dashboard` | [phase2_force_benchmark_dashboard.png](phase2_force_benchmark_dashboard.png) / [phase2_force_benchmark_dashboard.pdf](phase2_force_benchmark_dashboard.pdf) | phase2a_benchmark_real |
| `phase2_force_live_eta` | [phase2_force_live_eta.png](phase2_force_live_eta.png) / [phase2_force_live_eta.pdf](phase2_force_live_eta.pdf) | phase2a_live_eta |

Estados:

- `phase1_context`: usa datos reales ya existentes para cerrar Fase 1.
- `planned_placeholder`: define el embudo/contrato operativo sin métricas reales.
- `pending_mace_data`: figura reservada hasta tener baseline, fine-tune o validación MACE.
- `phase2a_benchmark_real`: usa mediciones reales del benchmark DFT Fase 2A; las configuraciones eliminadas no se grafican.
- `phase2a_live_eta`: estimación operativa generada desde logs vivos; no es una métrica MACE.

## Política De Datos

No se reportan valores de energía, fuerzas, stress, ranking de fases, estabilidad de
relajación ni speedup MACE como reales hasta que existan estructuras etiquetadas con DFT
compatible. Las plantillas se reemplazarán con curvas y tablas reales conforme aparezcan
`phase2_seed.extxyz`, `splits.json`, logs de entrenamiento y métricas por fase.
