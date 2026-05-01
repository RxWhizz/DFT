#!/usr/bin/env python
"""CLI script to run a full DFT workflow for CsPbI3 phases using GPAW."""

import logging
import sys
from pathlib import Path

import click

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_full_workflow")

# Ensure src is importable when running from the repo root
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dft_cspbi3 import DFTWorkflow


@click.command()
@click.option(
    "--phase",
    type=click.Choice(["alpha", "gamma", "delta"]),
    default="alpha",
    show_default=True,
    help="CsPbI3 polymorph phase.",
)
@click.option(
    "--steps",
    default="relax,scf,bands,dos,soc",
    show_default=True,
    help="Comma-separated list of workflow steps to execute.",
)
@click.option(
    "--config",
    default="configs/default_params.yaml",
    show_default=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to YAML configuration file.",
)
@click.option(
    "--workdir",
    default="./calculations",
    show_default=True,
    type=click.Path(),
    help="Root directory for calculation subdirectories.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Prepare input files without executing GPAW calculations.",
)
@click.option(
    "--cores",
    default=1,
    show_default=True,
    type=int,
    help="Number of MPI cores for GPAW parallelization.",
)
@click.option(
    "--status",
    is_flag=True,
    default=False,
    help="Print current workflow status table and exit.",
)
def main(phase, steps, config, workdir, dry_run, cores, status):
    """Run a complete DFT workflow for CsPbI3 (α, γ, or δ phase) using GPAW.

    Example:

        python run_full_workflow.py --phase alpha --steps relax,scf,bands

        mpirun -n 8 gpaw python run_full_workflow.py --phase alpha --cores 8

    Steps available: relax, scf, bands, dos, soc, hse06
    """
    if cores > 1:
        logger.info(
            "Running with %d MPI cores. Launch via: mpirun -n %d gpaw python %s",
            cores, cores, Path(__file__).name,
        )

    workflow = DFTWorkflow(
        phase=phase,
        config_path=config,
        work_dir=workdir,
        dry_run=dry_run,
    )

    if status:
        workflow.get_status()
        return

    step_list = [s.strip() for s in steps.split(",") if s.strip()]
    logger.info(
        "Starting workflow: phase=%s, steps=%s, dry_run=%s",
        phase, step_list, dry_run,
    )

    if dry_run:
        click.echo("[DRY RUN] Workflow steps to execute:")
        for s in step_list:
            click.echo(f"  - {s}")

    workflow.run(steps=step_list)
    workflow.get_status()

    click.echo(f"\nWorkflow complete. Results in: {workflow.work_dir}")


if __name__ == "__main__":
    main()
