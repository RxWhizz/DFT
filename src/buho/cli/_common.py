"""Utilidades compartidas del CLI unificado de BUHO."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import click

HELP_OPTS = {"help_option_names": ["-h", "--help"]}
PASSTHROUGH = {
    **HELP_OPTS,
    "ignore_unknown_options": True,
    "allow_extra_args": True,
}


def json_option(func: Callable[..., Any]) -> Callable[..., Any]:
    return click.option(
        "--json",
        "as_json",
        is_flag=True,
        help="Imprime la salida como JSON.",
    )(func)


def echo_json(data: Any) -> None:
    click.echo(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def echo_result(data: Any, *, as_json: bool, human: Callable[[Any], str] | None = None) -> None:
    if as_json:
        echo_json(data)
        return
    if human is not None:
        click.echo(human(data))
    elif isinstance(data, str):
        click.echo(data)
    else:
        echo_json(data)


def data_path(relative: str | Path) -> Path:
    from monitor_api import paths

    return paths.resolve_data(relative)


def data_root() -> Path:
    from monitor_api import paths

    return paths.data_root()


def bundle_file(*parts: str) -> Path:
    from monitor_api import paths

    return paths.bundle_file(*parts)


def import_available(module: str) -> bool:
    import importlib.util

    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def run_script(relative: str, args: Iterable[str]) -> None:
    script = data_path(relative)
    if not script.is_file():
        raise click.ClickException(f"No se encuentra el script: {script}")

    cmd = [sys.executable, str(script), *args]
    env = os.environ.copy()
    src = data_root() / "src"
    env["PYTHONPATH"] = (
        str(src) if not env.get("PYTHONPATH") else f"{src}{os.pathsep}{env['PYTHONPATH']}"
    )
    completed = subprocess.run(cmd, cwd=str(data_root()), env=env, check=False)
    raise click.exceptions.Exit(completed.returncode)


def run_module(module: str, args: Iterable[str]) -> None:
    cmd = [sys.executable, "-m", module, *args]
    env = os.environ.copy()
    src = data_root() / "src"
    env["PYTHONPATH"] = (
        str(src) if not env.get("PYTHONPATH") else f"{src}{os.pathsep}{env['PYTHONPATH']}"
    )
    completed = subprocess.run(cmd, cwd=str(data_root()), env=env, check=False)
    raise click.exceptions.Exit(completed.returncode)


def script_command(
    script: str,
    *,
    name: str,
    help_text: str,
) -> click.Command:
    @click.command(name, context_settings=PASSTHROUGH, help=help_text, short_help=help_text)
    @click.argument("args", nargs=-1, type=click.UNPROCESSED)
    def _cmd(args: tuple[str, ...]) -> None:
        run_script(script, args)

    return _cmd


def module_command(
    module: str,
    *,
    name: str,
    help_text: str,
) -> click.Command:
    @click.command(name, context_settings=PASSTHROUGH, help=help_text, short_help=help_text)
    @click.argument("args", nargs=-1, type=click.UNPROCESSED)
    def _cmd(args: tuple[str, ...]) -> None:
        run_module(module, args)

    return _cmd


def simple_status(
    group_name: str,
    *,
    covered: list[str] | None = None,
    commands: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "group": group_name,
        "status": "available",
        "data_root": str(data_root()),
        "covered": covered or [],
        "commands": commands or [],
    }
