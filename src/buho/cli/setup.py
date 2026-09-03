"""`buho setup`: comprueba el entorno y lo repara.

`buho doctor` dice *que* falta. Esto ademas sabe *como* arreglarlo y lo
ejecuta, que es la diferencia entre un diagnostico y un wizard.
"""

from __future__ import annotations

from typing import Any

import click
import yaml

from buho import setup_wizard

from ._common import HELP_OPTS, data_root, echo_json, echo_result, json_option

_ICONO = {True: "OK", False: "--"}


def _config() -> dict[str, Any]:
    """generator.yaml efectivo, sin reventar si no existe."""
    try:
        from monitor_api import paths

        ruta = paths.resolve_data("config/generator.yaml")
        if not ruta.is_file():
            ruta = paths.bundle_file("config", "generator.yaml")
    except Exception:  # noqa: BLE001 - fuera del monitor, cae al repo
        ruta = data_root() / "config" / "generator.yaml"
    try:
        with ruta.open(encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except OSError:
        return {}


def _check_human(data: dict[str, Any]) -> str:
    lineas = [
        f"Entorno PEROVOWL: {data['status']}",
        f"  Python: {data['python']} ({data['executable']})",
        f"  Plataforma: {data['plataforma']}"
        + ("  [binario congelado]" if data.get("frozen") else ""),
        "",
    ]
    for cap in data["capacidades"]:
        marca = _ICONO[cap["ok"]]
        etiqueta = "" if cap["requerido"] else "  (opcional)"
        lineas.append(f"  [{marca}] {cap['titulo']}{etiqueta}")
        if cap["ok"]:
            versiones = (cap.get("detalle") or {}).get("versiones")
            if isinstance(versiones, dict) and versiones:
                resumen = ", ".join(f"{k} {v}" for k, v in list(versiones.items())[:4])
                lineas.append(f"        {resumen}")
            continue
        if cap.get("error"):
            lineas.append(f"        {cap['error']}")
        if cap.get("remediacion"):
            lineas.append(f"        -> {cap['remediacion']}")
        if cap.get("comando"):
            lineas.append(f"        $ {cap['comando']}")
    return "\n".join(lineas)


@click.group("setup", context_settings=HELP_OPTS)
def setup() -> None:
    """Comprueba y repara los entornos que necesita el pipeline."""


@setup.command("check", context_settings=HELP_OPTS)
@click.option("--fast", is_flag=True,
              help="Omite la sonda MLFF, que lanza un proceso y tarda segundos.")
@click.option("--strict", is_flag=True, help="Sale con codigo 1 si algo requerido falla.")
@json_option
def setup_check(fast: bool, strict: bool, as_json: bool) -> None:
    """Matriz de capacidades: que funciona, que falta y con que comando se arregla."""
    data = setup_wizard.check(_config(), project_root=data_root(), incluir_mlff=not fast)
    echo_result(data, as_json=as_json, human=_check_human)
    if strict and not data["ok"]:
        raise click.exceptions.Exit(1)


_TARGETS = ["mlff", *sorted(setup_wizard.GRUPOS_PIP)]


@setup.command("plan", context_settings=HELP_OPTS)
@click.argument("target", type=click.Choice(_TARGETS))
@click.option("--cuda", is_flag=True, help="Rueda CUDA de torch en vez de la de CPU.")
@click.option("--env-name", default=None, help="Nombre del entorno MLFF en WSL.")
@click.option("--distro", default=None, help="Distro WSL donde instalar.")
@click.option("--recreate", is_flag=True, help="Borra el entorno antes de crearlo.")
@json_option
def setup_plan(target: str, cuda: bool, env_name: str | None, distro: str | None,
               recreate: bool, as_json: bool) -> None:
    """Ensena los comandos que se ejecutarian, sin ejecutar ninguno."""
    plan = _construir_plan(target, cuda, env_name, distro, recreate)
    if as_json:
        echo_json(plan.as_dict())
        return
    click.echo(_plan_human(plan))


def _construir_plan(target: str, cuda: bool, env_name: str | None,
                    distro: str | None, recreate: bool) -> setup_wizard.Plan:
    opciones: dict[str, Any] = {}
    if target == "mlff":
        opciones = {"cuda": cuda, "env_name": env_name,
                    "distro": distro, "recrear": recreate}
    try:
        return setup_wizard.plan(target, config=_config(), **opciones)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc


def _plan_human(plan: setup_wizard.Plan) -> str:
    lineas = [f"Plan '{plan.target}': {len(plan.steps)} paso(s)", ""]
    for i, step in enumerate(plan.steps, 1):
        marca = " (opcional)" if step.opcional else ""
        lineas.append(f"  {i}. {step.name}{marca} - {step.descripcion}")
        lineas.append(f"     $ {step.shell()}")
    if plan.notas:
        lineas.append("")
        lineas.append("Notas:")
        lineas.extend(f"  - {nota}" for nota in plan.notas)
    return "\n".join(lineas)


@setup.command("install", context_settings=HELP_OPTS)
@click.argument("target", type=click.Choice(_TARGETS))
@click.option("--yes", "-y", is_flag=True, help="No pide confirmacion.")
@click.option("--dry-run", is_flag=True, help="Solo ensena el plan.")
@click.option("--cuda", is_flag=True, help="Rueda CUDA de torch en vez de la de CPU.")
@click.option("--env-name", default=None, help="Nombre del entorno MLFF en WSL.")
@click.option("--distro", default=None, help="Distro WSL donde instalar.")
@click.option("--recreate", is_flag=True, help="Borra el entorno antes de crearlo.")
@json_option
def setup_install(target: str, yes: bool, dry_run: bool, cuda: bool,
                  env_name: str | None, distro: str | None, recreate: bool,
                  as_json: bool) -> None:
    """Instala lo que falta para TARGET."""
    plan = _construir_plan(target, cuda, env_name, distro, recreate)

    if not plan.steps:
        mensaje = {"status": "skipped", "target": target, "notas": plan.notas}
        echo_result(mensaje, as_json=as_json,
                    human=lambda d: "Nada que hacer.\n" + "\n".join(f"  - {n}" for n in d["notas"]))
        return

    if dry_run:
        if as_json:
            echo_json({"status": "dry-run", **plan.as_dict()})
        else:
            click.echo(_plan_human(plan))
        return

    if not as_json:
        click.echo(_plan_human(plan))
        click.echo("")
    if not yes and not click.confirm(f"Ejecutar el plan '{target}'?", default=False):
        raise click.exceptions.Exit(1)

    # En JSON se acumula y se emite un solo objeto al final, para que la salida
    # siga siendo parseable; en modo humano se transmite segun ocurre.
    resultado = setup_wizard.execute(
        plan, on_output=None if as_json else click.echo
    )
    if as_json:
        echo_json({"target": target, **resultado})
    else:
        click.echo("")
        click.echo("OK" if resultado["status"] == "ok" else f"FALLO: {resultado.get('error')}")
    if resultado["status"] != "ok":
        raise click.exceptions.Exit(1)
