#!/usr/bin/env python3
"""Prepare and collect the PBE Top 8 DFT comparison workspace."""

from __future__ import annotations

import sys
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dft_cspbi3.top8 import prepare_top8_pbe_workspace, write_comparison_csv


@click.command()
@click.option(
    "--workdir",
    default="calculations/top8_pbe",
    show_default=True,
    type=click.Path(),
    help="Root directory for Top 8 PBE calculations.",
)
@click.option(
    "--structures-dir",
    default="structures/top8",
    show_default=True,
    type=click.Path(),
    help="Directory for generated Top 8 starting structures.",
)
@click.option(
    "--comparison-csv",
    default=None,
    type=click.Path(),
    help="Output CSV path. Defaults to <workdir>/top8_pbe_comparison.csv.",
)
@click.option(
    "--collect-only",
    is_flag=True,
    help="Only refresh the comparison CSV from existing outputs.",
)
@click.option(
    "--overwrite-structures",
    is_flag=True,
    help="Regenerate structure JSON/CIF files even if they already exist.",
)
def main(
    workdir: str,
    structures_dir: str,
    comparison_csv: str | None,
    collect_only: bool,
    overwrite_structures: bool,
) -> None:
    """Create PBE inputs and a CSV scaffold for the Top 8 ML candidates."""
    work = Path(workdir)
    csv_path = Path(comparison_csv) if comparison_csv else work / "top8_pbe_comparison.csv"

    if collect_only:
        path = write_comparison_csv(csv_path, work_dir=work)
        click.echo(f"Refreshed comparison CSV: {path}")
        return

    paths = prepare_top8_pbe_workspace(
        work_dir=work,
        structures_dir=structures_dir,
        comparison_csv=csv_path,
        overwrite_structures=overwrite_structures,
    )
    click.echo(f"Structures: {paths['structures_dir']}")
    click.echo(f"Comparison CSV: {paths['comparison_csv']}")
    click.echo(f"Run script: {paths['run_script']}")
    click.echo("Default workflow is PBE only: relax, scf, bands, dos, soc, effective_masses, score")


if __name__ == "__main__":
    main()
