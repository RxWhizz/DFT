"""CLI del loop de active learning por batches.

    # Cribar un batch SIN DFT (smoke): genera, cascada, selecciona, artefactos
    python -m buho.active_learning run-batch --batch-id 0 --dry-run

    # Batch completo: + prepara jobs DFT (y opcionalmente lanza el runner)
    python -m buho.active_learning run-batch --batch-id 0 --launch

    # Tras terminar el DFT: recolecta + (opcional) reentrena el surrogate
    python -m buho.active_learning finalize-batch --batch-id 0 --retrain

    # Estado de los batches
    python -m buho.active_learning status
"""
from __future__ import annotations

import json
from pathlib import Path

import click

from buho.active_learning.batch_loop import ROOT, BatchLoop


@click.group()
def cli():
    """BUHO — active learning por batches (generador continuo + cascada + DFT)."""


@cli.command("run-batch")
@click.option("--batch-id", type=int, required=True, help="Índice del batch (seed offset).")
@click.option("--config", default="config/generator.yaml", show_default=True)
@click.option("--dry-run", is_flag=True, help="Cribar sin preparar/lanzar DFT.")
@click.option("--launch", is_flag=True, help="Lanzar el runner DFT (5×8) tras preparar.")
def run_batch(batch_id, config, dry_run, launch):
    """Genera un batch, lo criba (Tier 0-2) y prepara DFT para los seleccionados."""
    loop = BatchLoop(config_path=config, project_root=ROOT)
    m = loop.run_batch(batch_id, dry_run=dry_run, launch=launch)
    click.echo(json.dumps(m, indent=2))


@cli.command("finalize-batch")
@click.option("--batch-id", type=int, required=True)
@click.option("--config", default="config/generator.yaml", show_default=True)
@click.option("--retrain", is_flag=True, help="Reentrenar el surrogate con los resultados.")
def finalize_batch(batch_id, config, retrain):
    """Recolecta resultados DFT del batch y opcionalmente reentrena el surrogate."""
    loop = BatchLoop(config_path=config, project_root=ROOT)
    m = loop.finalize_batch(batch_id, retrain=retrain)
    click.echo(json.dumps(m, indent=2))


@cli.command("status")
@click.option("--batch-id", type=int, default=None, help="Un batch específico (o todos).")
def status(batch_id):
    """Muestra el estado de los batches (lee batch_manifest.json)."""
    bdir = ROOT / "data" / "batches"
    if not bdir.exists():
        click.echo("(sin batches todavía)")
        return
    dirs = ([bdir / f"batch_{batch_id:03d}"] if batch_id is not None
            else sorted(bdir.glob("batch_*")))
    for d in dirs:
        mf = d / "batch_manifest.json"
        if not mf.exists():
            continue
        m = json.loads(mf.read_text())
        click.echo(f"{d.name}: status={m.get('status')} "
                   f"gen={m.get('n_generated')} sel={m.get('n_selected_dft')} "
                   f"conv={m.get('n_dft_converged','-')} "
                   f"appended={m.get('n_appended_training','-')}")


if __name__ == "__main__":
    cli()
