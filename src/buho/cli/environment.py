"""Diagnostico de entorno y pseudopotenciales PAW."""

from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Any

import click

from ._common import HELP_OPTS, data_root, echo_result, import_available, json_option


def _paw_data(elements: str = "Cs,Pb,I") -> dict[str, Any]:
    from buho import gpaw_setup

    root = data_root()
    candidates = []
    for item in gpaw_setup.candidatos(root):
        path = Path(item)
        candidates.append(
            {
                "path": str(path),
                "exists": path.is_dir(),
                "has_marker": (path / gpaw_setup.MARCADOR).is_file(),
            }
        )

    found = gpaw_setup.find(root)
    element_list = [e.strip() for e in elements.split(",") if e.strip()]
    missing: list[str] = []
    present: dict[str, list[str]] = {}
    if found:
        base = Path(found)
        for element in element_list:
            matches = sorted(p.name for p in base.glob(f"{element}.PBE*"))
            present[element] = matches
            if not matches:
                missing.append(element)
    else:
        missing = element_list

    return {
        "found": found,
        "marker": gpaw_setup.MARCADOR,
        "elements": element_list,
        "present": present,
        "missing": missing,
        "candidates": candidates,
        "ok": bool(found) and not missing,
    }


def _paw_human(data: dict[str, Any]) -> str:
    lines = ["PAW GPAW:"]
    if data["found"]:
        lines.append(f"  ruta activa: {data['found']}")
    else:
        lines.append("  ruta activa: no encontrada")
    if data["missing"]:
        lines.append("  faltan: " + ", ".join(data["missing"]))
    else:
        lines.append("  elementos requeridos: OK")
    lines.append("  candidatos:")
    for item in data["candidates"]:
        mark = "OK" if item["has_marker"] else "--"
        lines.append(f"    [{mark}] {item['path']}")
    return "\n".join(lines)


@click.group("paw", context_settings=HELP_OPTS)
def paw() -> None:
    """Inspecciona datasets PAW de GPAW."""


@paw.command("list", context_settings=HELP_OPTS)
@json_option
def paw_list(as_json: bool) -> None:
    """Lista rutas candidatas para GPAW_SETUP_PATH."""
    data = _paw_data()
    echo_result(data, as_json=as_json, human=_paw_human)


@paw.command("check", context_settings=HELP_OPTS)
@click.option("--elements", default="Cs,Pb,I", show_default=True, help="Elementos requeridos.")
@json_option
def paw_check(elements: str, as_json: bool) -> None:
    """Comprueba que los PAW requeridos existan antes de lanzar calculos."""
    data = _paw_data(elements)
    echo_result(data, as_json=as_json, human=_paw_human)
    if not data["ok"]:
        raise click.exceptions.Exit(1)


def _doctor_data() -> dict[str, Any]:
    root = data_root()
    paw_status = _paw_data()
    paths = {
        "data_root": str(root),
        "calculations": str(root / "calculations"),
        "runs": str(root / "runs"),
        "local_runs": str(root / "local_runs"),
        "models": str(root / "models"),
        "config": str(root / "config"),
        "configs": str(root / "configs"),
    }
    checks = {
        "python": platform.python_version(),
        "executable": os.sys.executable,
        "platform": platform.platform(),
        "gpaw_importable": import_available("gpaw"),
        "ase_importable": import_available("ase"),
        "sklearn_importable": import_available("sklearn"),
        "torch_importable": import_available("torch"),
        "matgl_importable": import_available("matgl"),
        "psutil_importable": import_available("psutil"),
        "click_importable": import_available("click"),
    }
    files = {
        key: {"path": value, "exists": Path(value).exists()}
        for key, value in paths.items()
    }
    ok = (
        bool(paw_status["ok"])
        and checks["click_importable"]
        and checks["gpaw_importable"]
        and checks["ase_importable"]
    )
    return {
        "status": "ok" if ok else "warning",
        "ok": ok,
        "environment": checks,
        "paths": files,
        "paw": paw_status,
    }


def _doctor_human(data: dict[str, Any]) -> str:
    env = data["environment"]
    lines = [
        f"BUHO doctor: {data['status']}",
        f"  Python: {env['python']} ({env['executable']})",
        f"  Plataforma: {env['platform']}",
        "  Dependencias:",
    ]
    for key in (
        "gpaw_importable",
        "ase_importable",
        "sklearn_importable",
        "torch_importable",
        "matgl_importable",
        "psutil_importable",
    ):
        lines.append(f"    {key}: {env[key]}")
    lines.append("")
    lines.append(_paw_human(data["paw"]))
    lines.append("")
    lines.append("Rutas:")
    for key, item in data["paths"].items():
        status = "existe" if item["exists"] else "no existe"
        lines.append(f"  {key}: {item['path']} ({status})")
    return "\n".join(lines)


@click.command("doctor", context_settings=HELP_OPTS)
@click.option("--strict", is_flag=True, help="Sale con codigo 1 si hay avisos.")
@json_option
def doctor(strict: bool, as_json: bool) -> None:
    """Diagnostica entorno, PAW, datos y modelos."""
    data = _doctor_data()
    echo_result(data, as_json=as_json, human=_doctor_human)
    if strict and not data["ok"]:
        raise click.exceptions.Exit(1)
