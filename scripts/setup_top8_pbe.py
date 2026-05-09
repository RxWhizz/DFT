#!/usr/bin/env python3
"""Prepara y recolecta workspace comparativo PBE Top 8."""

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
    help="Directorio raíz cálculos Top 8 PBE.",
)
@click.option(
    "--structures-dir",
    default="structures/top8",
    show_default=True,
    type=click.Path(),
    help="Directorio estructuras iniciales Top 8.",
)
@click.option(
    "--comparison-csv",
    default=None,
    type=click.Path(),
    help="Ruta CSV salida. Default: <workdir>/top8_pbe_comparison.csv.",
)
@click.option(
    "--collect-only",
    is_flag=True,
    help="Solo refresca CSV desde salidas existentes.",
)
@click.option(
    "--overwrite-structures",
    is_flag=True,
    help="Regenera JSON/CIF aunque existan.",
)
def main(
    workdir: str,
    structures_dir: str,
    comparison_csv: str | None,
    collect_only: bool,
    overwrite_structures: bool,
) -> None:
    """Crea inputs PBE y CSV base para candidatos ML Top 8."""
    work = Path(workdir)
    csv_path = Path(comparison_csv) if comparison_csv else work / "top8_pbe_comparison.csv"

    if collect_only:
        path = write_comparison_csv(csv_path, work_dir=work)
        click.echo(f"CSV refrescado: {path}")
        return

    paths = prepare_top8_pbe_workspace(
        work_dir=work,
        structures_dir=structures_dir,
        comparison_csv=csv_path,
        overwrite_structures=overwrite_structures,
    )
    click.echo(f"Estructuras: {paths['structures_dir']}")
    click.echo(f"CSV comparacion: {paths['comparison_csv']}")
    click.echo(f"Script corrida: {paths['run_script']}")
    click.echo("Workflow default: PBE solo: relax, scf, bands, dos, soc, effective_masses, score")


if __name__ == "__main__":
    main()
