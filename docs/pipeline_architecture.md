# Arquitectura del pipeline DFT/surrogate

Documento de arquitectura conservadora para el pipeline de perovskitas ABX3. No cambia la logica cientifica actual; describe responsabilidades, riesgos y una ruta gradual de refactor.

## Proposito

El proyecto combina calculos DFT con GPAW, evaluacion surrogate/heuristica y generacion de resultados para reportes de tesis. El objetivo cientifico se mantiene: construir o cargar estructuras de perovskitas, ejecutar pasos DFT reproducibles, evaluar propiedades fotovoltaicas y comparar resultados DFT con estimaciones surrogate.

## Arquitectura actual

- Entrada principal: `main.py`.
- Entrada alternativa: `scripts/run_full_workflow.py`.
- Motor DFT: `src/dft_cspbi3/workflow_manager.py`.
- Construccion de estructuras: `src/dft_cspbi3/structure_builder.py`.
- Configuracion GPAW: `src/dft_cspbi3/calculator_factory.py` y `configs/*.yaml`.
- Scoring fotovoltaico: `src/dft_cspbi3/analysis/scoring.py`.
- Surrogate: `src/ml_surrogate/*.py`.
- Analisis y graficas: `src/dft_cspbi3/analysis/`, `src/dft_cspbi3/plotting.py`, `scripts/top8_*.py`, `scripts/generate_*.py`.
- Resultados persistentes: `calculations/`, `models/`, `data/`, `imagenes/`.

## Separacion propuesta

- Generacion de candidatos: `src/dft_cspbi3/candidates.py`.
- Evaluacion surrogate/heuristica: `src/dft_cspbi3/surrogate_runner.py` usando `ml_surrogate.integration`.
- Preparacion DFT: `StructureBuilder`, `GPAWCalculatorFactory` y helpers internos del workflow.
- Ejecucion DFT: `DFTWorkflow` sin cambiar su API publica.
- Analisis de resultados: `src/dft_cspbi3/analysis/`.
- Graficas/reportes: `src/dft_cspbi3/reporting/`, `src/dft_cspbi3/plotting.py`, `scripts/generate_*.py`.
- Configuracion y modos: `src/dft_cspbi3/pipeline_modes.py`, `configs/*.yaml`.
- Cache: `src/dft_cspbi3/cache.py`.

## Modos de ejecucion

- `surrogate_only`: valida candidatos y evalua surrogate/heuristica. No ejecuta GPAW.
- `dft_only`: ejecuta pasos DFT indicados y usa salidas existentes cuando el workflow ya las detecta.
- `hybrid`: usa surrogate para priorizar o complementar y DFT para candidatos seleccionados. La politica de seleccion debe quedar documentada antes de activar cambios en `main.py` o `workflow_manager.py`.

## Riesgos detectados

- `workflow_manager.py` concentra muchas responsabilidades y supera 1500 lineas.
- `top8.py` supera 500 lineas.
- `pyproject.toml` declara entry points hacia `dft_cspbi3.cli`, pero no se encontro `src/dft_cspbi3/cli.py`.
- Hay comentarios/docstrings mezclados en espanol e ingles; algunos caracteres se ven mal en PowerShell por codificacion de consola, no necesariamente por archivos corruptos.
- `.git/index.lock` existe con 0 bytes desde `2026-05-28 22:26:35`; parece potencialmente stale, pero hay procesos `git` activos y no debe borrarse sin confirmacion.
- Muchos resultados son archivos cientificos pesados o bitacoras. No deben borrarse, renombrarse ni moverse.

## Plan conservador

1. Documentar arquitectura y riesgos.
2. Agregar pruebas de comportamiento para Goldschmidt, ABX3, scoring y seleccion de modo.
3. Agregar modulos aditivos sin conectarlos al flujo principal.
4. Revisar diff antes de tocar archivos criticos.
5. Refactorizar internamente solo despues de confirmar archivo por archivo.

