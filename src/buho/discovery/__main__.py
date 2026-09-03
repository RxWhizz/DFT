"""CLI for the autonomous PEROVOWL discovery loop."""

from __future__ import annotations

import click

from buho.discovery.engine import DiscoveryLoop


@click.group()
def cli() -> None:
    """Discovery loop: ML ranking -> DFT -> retrain -> repeat."""


def _roots(func):
    """Raices de datos, como opciones compartidas.

    El monitor lanza este CLI como subproceso y no comparte su configuracion de
    rutas con el: sin poder pasarlas, el bucle escribiria el estado en la raiz
    por defecto del repositorio en vez de en la que el monitor esta leyendo, y
    la GUI no veria avanzar nada.
    """
    for opcion in (
        click.option("--models-root", default=None, help="Raiz donde viven models/."),
        click.option("--data-root", default=None, help="Raiz de datos de salida."),
        click.option("--project-root", default=None, help="Raiz del proyecto."),
    ):
        func = opcion(func)
    return func


def _build(config: str, project_root: str | None = None, data_root: str | None = None,
           models_root: str | None = None) -> DiscoveryLoop:
    from pathlib import Path

    return DiscoveryLoop(
        config_path=config,
        project_root=Path(project_root) if project_root else None,
        data_root=Path(data_root) if data_root else None,
        models_root=Path(models_root) if models_root else None,
    )


@cli.command("init")
@click.option("--config", default="config/generator.yaml", show_default=True)
@click.option("--reset", is_flag=True, help="Recrear candidatos, ledger y estado.")
@click.option("--json", "as_json", is_flag=True, help="Imprimir salida como JSON.")
def init(config: str, reset: bool, as_json: bool) -> None:
    loop = DiscoveryLoop(config_path=config)
    _emit(loop.init_space(reset=reset), as_json)


@cli.command("run")
@click.option("--config", default="config/generator.yaml", show_default=True)
@click.option("--dry-run", is_flag=True, help="Selecciona la ronda sin preparar DFT real.")
@click.option("--no-runner", is_flag=True, help="Prepara DFT pero no lanza el runner.")
@click.option("--no-mlff", is_flag=True, help="No ejecutar el Tier 2 MLFF en esta pasada.")
@click.option("--max-rounds", type=int, default=None, help="Limite de rondas para esta invocacion.")
@click.option("--json", "as_json", is_flag=True, help="Imprimir salida como JSON.")
@_roots
def run(config: str, dry_run: bool, no_runner: bool, no_mlff: bool, max_rounds: int | None,
        as_json: bool, project_root: str | None, data_root: str | None,
        models_root: str | None) -> None:
    loop = _build(config, project_root, data_root, models_root)
    _emit(
        loop.run_forever(
            dry_run=dry_run,
            start_runner=not no_runner,
            use_mlff=False if no_mlff else None,
            max_rounds=max_rounds,
        ),
        as_json,
    )


@cli.command("status")
@click.option("--config", default="config/generator.yaml", show_default=True)
@click.option("--json", "as_json", is_flag=True, help="Imprimir salida como JSON.")
def status(config: str, as_json: bool) -> None:
    _emit(DiscoveryLoop(config_path=config).status(), as_json)


@cli.command("pause")
@click.option("--config", default="config/generator.yaml", show_default=True)
@click.option("--json", "as_json", is_flag=True, help="Imprimir salida como JSON.")
def pause(config: str, as_json: bool) -> None:
    _emit(DiscoveryLoop(config_path=config).pause(), as_json)


@cli.command("resume")
@click.option("--config", default="config/generator.yaml", show_default=True)
@click.option("--json", "as_json", is_flag=True, help="Imprimir salida como JSON.")
def resume(config: str, as_json: bool) -> None:
    _emit(DiscoveryLoop(config_path=config).resume(), as_json)


@cli.command("export")
@click.option("--config", default="config/generator.yaml", show_default=True)
@click.option("--json", "as_json", is_flag=True, help="Imprimir salida como JSON.")
def export(config: str, as_json: bool) -> None:
    _emit(DiscoveryLoop(config_path=config).export(), as_json)


def _emit(data: dict, as_json: bool) -> None:
    import json

    if as_json:
        click.echo(json.dumps(data, indent=2, ensure_ascii=False, default=str))
        return
    state = data.get("state", data)
    coverage = data.get("coverage", {})
    click.echo(
        "discovery status={status} round={round} coverage={seen}/{total} ({percent}%)".format(
            status=state.get("status", "unknown"),
            round=state.get("current_round", "-"),
            seen=coverage.get("seen", 0),
            total=coverage.get("total", 0),
            percent=coverage.get("percent", 0),
        )
    )


if __name__ == "__main__":
    cli()
