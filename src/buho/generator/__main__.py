"""CLI del generador BUHO.

Uso:
    python -m buho.generator generate          --config config/generator.yaml
    python -m buho.generator filter            --config config/generator.yaml
    python -m buho.generator build-structures  --top 500 [--config ...]
"""
from __future__ import annotations

import sys
from pathlib import Path

import click
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))


def _load_config(config: str) -> dict:
    with open(config) as f:
        return yaml.safe_load(f)


@click.group()
def cli():
    """BUHO — generador de candidatos ABX3."""


@cli.command("generate")
@click.option("--config", default="config/generator.yaml", show_default=True,
              help="Ruta al YAML de configuración.")
@click.option("--out", default=None, help="Ruta de salida JSONL (sobrescribe config).")
def generate(config, out):
    """Genera candidatos brutos ABX3 (puros y mixtos) y los guarda en JSONL."""
    from buho.generator.heuristic_generator import HeuristicGenerator

    cfg = _load_config(config)
    out_path = out or cfg.get("paths", {}).get("raw_candidates", "data/raw/generated_candidates.jsonl")

    gen = HeuristicGenerator(config)
    click.echo("Generando candidatos...")
    candidates = gen.generate()
    click.echo(f"  Generados: {len(candidates)}")

    HeuristicGenerator.save_jsonl(candidates, out_path)
    click.echo(f"  Guardados en: {out_path}")

    # Distribución por modo
    from collections import Counter
    mode_counts = Counter(c.generation_mode for c in candidates)
    for mode, n in sorted(mode_counts.items()):
        click.echo(f"    {mode}: {n}")


@cli.command("filter")
@click.option("--config", default="config/generator.yaml", show_default=True)
@click.option("--in", "in_path", default=None, help="JSONL de entrada (sobrescribe config).")
@click.option("--out", default=None, help="CSV de salida (sobrescribe config).")
def filter_cmd(config, in_path, out):
    """Aplica filtros físicos a los candidatos generados y guarda los que pasan."""
    import pandas as pd
    from buho.generator.heuristic_generator import HeuristicGenerator
    from buho.filters.physical_filters import PhysicalFilter
    from buho.scoring.pre_dft_score import PreDFTScorer

    cfg = _load_config(config)
    paths = cfg.get("paths", {})
    in_file = in_path or paths.get("raw_candidates", "data/raw/generated_candidates.jsonl")
    out_csv = out or paths.get("filtered_candidates", "data/processed/filtered_candidates.csv")

    click.echo(f"Cargando candidatos desde {in_file}...")
    candidates = HeuristicGenerator.load_jsonl(in_file)
    click.echo(f"  Cargados: {len(candidates)}")

    filt = PhysicalFilter(cfg)
    result = filt.apply(candidates)
    click.echo(result.summary())

    scorer = PreDFTScorer(cfg)
    scored = scorer.score_all(result.passed)
    scored.sort(key=lambda s: -s.pre_dft_score)

    df = PreDFTScorer.to_dataframe(scored)
    Path(out_csv).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False)
    click.echo(f"  Guardados {len(df)} candidatos filtrados en: {out_csv}")

    # Salvar también el top-N para DFT
    n_dft = cfg.get("generation", {}).get("n_candidates_dft", 500)
    top_path = paths.get("top_candidates", "data/processed/top500_candidates.csv")
    df.head(n_dft).to_csv(top_path, index=False)
    click.echo(f"  Top-{n_dft} guardados en: {top_path}")


@cli.command("build-structures")
@click.option("--config", default="config/generator.yaml", show_default=True)
@click.option("--top", default=500, show_default=True, help="Número de estructuras a construir.")
@click.option("--in", "in_path", default=None, help="CSV de candidatos filtrados.")
@click.option("--out-dir", default=None, help="Directorio de salida (sobrescribe config).")
@click.option("--seed", default=None, type=int, help="Semilla aleatoria para superceldas.")
def build_structures(config, top, in_path, out_dir, seed):
    """Construye estructuras CIF/POSCAR/traj para los top-N candidatos."""
    import pandas as pd
    from buho.generator.heuristic_generator import GeneratedCandidate, HeuristicGenerator
    from buho.structure.build_abx3 import ABX3StructureBuilder

    cfg = _load_config(config)
    paths = cfg.get("paths", {})
    in_file = in_path or paths.get("top_candidates", "data/processed/top500_candidates.csv")
    out_root = Path(out_dir) if out_dir else Path(paths.get("relax_dir", "runs/relax_basic"))

    if in_file.endswith(".jsonl"):
        candidates_raw = HeuristicGenerator.load_jsonl(in_file)[:top]
    else:
        df = pd.read_csv(in_file).head(top)
        # Recargar desde JSONL para tener el objeto completo
        jsonl = paths.get("raw_candidates", "data/raw/generated_candidates.jsonl")
        all_candidates = {c.candidate_id: c for c in HeuristicGenerator.load_jsonl(jsonl)}
        candidates_raw = [all_candidates[cid] for cid in df["candidate_id"] if cid in all_candidates]

    rng_seed = seed if seed is not None else cfg.get("random_seed", 42)
    builder = ABX3StructureBuilder(cfg, random_seed=rng_seed)

    click.echo(f"Construyendo {len(candidates_raw)} estructuras en {out_root}/...")
    built = 0
    for c in candidates_raw:
        job_dir = out_root / c.candidate_id
        job_dir.mkdir(parents=True, exist_ok=True)
        try:
            builder.build(c, out_dir=job_dir, export=True)
            built += 1
        except Exception as e:
            click.echo(f"  ✗ {c.formula}: {e}", err=True)

    click.echo(f"  Construidas: {built}/{len(candidates_raw)}")


if __name__ == "__main__":
    cli()
