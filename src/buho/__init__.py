"""BUHO — Pipeline de Descubrimiento de Perovskitas ABX3.

Fase 1: Generación → Filtrado → Estructuras → DFT básico (r2SCAN)

Uso rápido:
    python -m buho.generator generate --config config/generator.yaml
    python -m buho.generator filter   --config config/generator.yaml
    python -m buho.generator build-structures --top 500
    python -m buho.dft prepare-relax  --top 500
    python -m buho.dft collect-results
"""
__version__ = "0.1.0"
