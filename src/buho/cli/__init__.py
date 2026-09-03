"""CLI unificado de BUHO."""

from __future__ import annotations

import logging

import click

from buho import __version__

from ._common import HELP_OPTS
from .calc import calc, run_cmd, status_cmd
from .domains import ALL_GROUPS
from .environment import doctor, paw
from .setup import setup


@click.group("buho", context_settings=HELP_OPTS)
@click.option("--debug", is_flag=True, help="Activa logs DEBUG.")
@click.version_option(version=__version__, prog_name="buho")
def main(debug: bool) -> None:
    """Framework BUHO para descubrimiento y calculos DFT de perovskitas."""
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


main.add_command(doctor)
main.add_command(paw)
main.add_command(setup)
main.add_command(calc)

# Compatibilidad con el antiguo `python main.py run/status`.
main.add_command(run_cmd)
main.add_command(status_cmd)

for group in ALL_GROUPS:
    if group.name not in main.commands:
        main.add_command(group)


cli = main


__all__ = ["main", "cli"]
