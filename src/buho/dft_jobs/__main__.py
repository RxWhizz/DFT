"""CLI para los trabajos DFT del cribado.

El funcional es PBE, no r2SCAN: r2SCAN se descartó aquí por coste (a un core
son unos 195 s por iteración, unos cinco días para 482 superceldas) y queda
reservado para la caracterización profunda.

Uso:
    buho dft-jobs prepare-relax --top 500 [--config ...]
    buho dft-jobs collect-results [--relax-dir runs/relax_basic]

El módulo se invoca como `python -m buho.dft_jobs`; `buho.dft` no existe.
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
    """Trabajos DFT del cribado: preparar, lanzar y recolectar."""


@cli.command("prepare-relax")
@click.option("--config", default="config/generator.yaml", show_default=True)
@click.option("--top", default=500, show_default=True, help="Número de candidatos.")
@click.option("--in", "in_path", default=None, help="CSV de top candidatos.")
@click.option("--out-dir", default=None, help="Directorio raíz de jobs.")
@click.option("--cores", default=1, show_default=True, help="Cores MPI para run.sh.")
@click.option("--python", "python_exe", default="python3", show_default=True)
def prepare_relax(config, top, in_path, out_dir, cores, python_exe):
    """Crea directorios de relajación DFT para los top-N candidatos."""
    import pandas as pd
    from buho.generator.heuristic_generator import HeuristicGenerator
    from buho.dft_jobs.prepare_relaxation_jobs import RelaxationJobPreparer

    cfg = _load_config(config)
    paths = cfg.get("paths", {})
    in_file = in_path or paths.get("top_candidates", "data/processed/top500_candidates.csv")
    out_root = Path(out_dir) if out_dir else Path(paths.get("relax_dir", "runs/relax_basic"))

    df = pd.read_csv(in_file).head(top)
    jsonl = paths.get("raw_candidates", "data/raw/generated_candidates.jsonl")
    all_cands = {c.candidate_id: c for c in HeuristicGenerator.load_jsonl(jsonl)}
    candidates = [all_cands[cid] for cid in df["candidate_id"] if cid in all_cands]

    click.echo(f"Preparando {len(candidates)} jobs en {out_root}/...")
    prep = RelaxationJobPreparer(cfg, project_root=ROOT, n_cores=cores, python=python_exe)
    prepared = prep.prepare(candidates, out_root=out_root, config_src=Path(config))
    click.echo(f"  Jobs listos: {len(prepared)}")


@cli.command("collect-results")
@click.option("--config", default="config/generator.yaml", show_default=True)
@click.option("--relax-dir", default=None, help="Directorio raíz de jobs.")
@click.option("--out-dir", default=None, help="Directorio de salida de resultados.")
def collect_results(config, relax_dir, out_dir):
    """Recolecta resultados DFT de todos los jobs y guarda CSV/JSONL."""
    from buho.dft_jobs.collect_results import ResultCollector

    cfg = _load_config(config)
    paths = cfg.get("paths", {})
    rd = Path(relax_dir) if relax_dir else Path(paths.get("relax_dir", "runs/relax_basic"))
    od = Path(out_dir) if out_dir else Path("data/processed")

    click.echo(f"Recolectando resultados desde {rd}/...")
    collector = ResultCollector(project_root=ROOT)
    df = collector.collect_all(rd)

    if df.empty:
        click.echo("  No se encontraron resultados.")
        return

    converged = df["converged"].sum() if "converged" in df.columns else 0
    click.echo(f"  Total: {len(df)}  Convergidos: {converged}")
    collector.save(df, od)


if __name__ == "__main__":
    cli()
