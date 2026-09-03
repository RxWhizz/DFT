"""CLI unificado `buho`."""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

import pytest
from click.testing import CliRunner

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from buho.cli import main

HEAVY = ("gpaw", "torch", "matgl")

GROUP_JSON_COMMANDS = [
    ("doctor", ["doctor", "--json"]),
    ("calc", ["calc", "steps", "--json"]),
    ("paw", ["paw", "list", "--json"]),
    ("generate", ["generate", "status", "--json"]),
    ("dft-jobs", ["dft-jobs", "status", "--json"]),
    ("active-learning", ["active-learning", "status", "--json"]),
    ("phase2-force", ["phase2-force", "status", "--json"]),
    ("monitor", ["monitor", "paths", "--json"]),
    ("activity", ["activity", "runners", "--json"]),
    ("screening", ["screening", "tiers", "--json"]),
    ("candidates", ["candidates", "list", "--json", "--limit", "1"]),
    ("batches", ["batches", "list", "--json"]),
    ("ml", ["ml", "status", "--json"]),
    ("mlip", ["mlip", "status", "--json"]),
    ("analysis", ["analysis", "list", "--json"]),
    ("validate", ["validate", "status", "--json"]),
    ("bench", ["bench", "plan", "--json"]),
    ("report", ["report", "list", "--json"]),
    ("top8", ["top8", "status", "--json"]),
    ("structures", ["structures", "list", "--json"]),
    ("data", ["data", "status", "--json"]),
    ("g0w0", ["g0w0", "status", "--json"]),
    ("u-scan", ["u-scan", "status", "--json"]),
    ("files", ["files", "reports", "--json"]),
    ("jobs", ["jobs", "list", "--json"]),
    ("agent", ["agent", "status", "--json"]),
    ("notify", ["notify", "status", "--json"]),
    ("watchdog", ["watchdog", "status", "--json"]),
]


def test_pyproject_declara_entry_point_buho() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["scripts"]["buho"] == "buho.cli:main"


def test_root_help_no_carga_dependencias_pesadas() -> None:
    runner = CliRunner()
    before = {name for name in HEAVY if name in sys.modules}
    result = runner.invoke(main, ["--help"])
    after = {name for name in HEAVY if name in sys.modules}

    assert result.exit_code == 0, result.output
    assert "calc" in result.output
    assert "paw" in result.output
    assert after == before


@pytest.mark.parametrize("group,args", GROUP_JSON_COMMANDS)
def test_grupo_existe_help_ligero_y_json_valido(group: str, args: list[str]) -> None:
    runner = CliRunner()
    before = {name for name in HEAVY if name in sys.modules}

    help_result = runner.invoke(main, [group, "--help"])
    after_help = {name for name in HEAVY if name in sys.modules}
    assert help_result.exit_code == 0, help_result.output
    assert after_help == before

    json_result = runner.invoke(main, args)
    assert json_result.exit_code == 0, json_result.output
    payload = json.loads(json_result.output)
    assert isinstance(payload, dict)


@pytest.mark.parametrize("alias", ["run", "status"])
def test_aliases_raiz_del_cli_anterior(alias: str) -> None:
    result = CliRunner().invoke(main, [alias, "--help"])
    assert result.exit_code == 0, result.output


def test_active_learning_expone_discovery_sin_dependencias_pesadas() -> None:
    runner = CliRunner()
    before = {name for name in HEAVY if name in sys.modules}

    result = runner.invoke(main, ["active-learning", "--help"])
    after = {name for name in HEAVY if name in sys.modules}

    assert result.exit_code == 0, result.output
    assert "discovery" in result.output
    assert after == before
