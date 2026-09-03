"""Localización de los datasets PAW.

Regresión de la avería que consumió lotes enteros: la ruta estaba escrita a mano
en siete archivos, dejó de existir, y cada job moría con
`Could not find required PAW dataset file "Cs.PBE"` sin que el runner se
enterara. 48/48 en batch_248771, 48/48 en batch_836602, 23/55 en batch_181544.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from buho import gpaw_setup

ROOT = Path(__file__).resolve().parents[1]


def _setups_falsos(base: Path) -> Path:
    d = base / "setups"
    d.mkdir(parents=True, exist_ok=True)
    (d / gpaw_setup.MARCADOR).write_bytes(b"")
    return d


def test_no_basta_con_que_el_directorio_exista(tmp_path, monkeypatch):
    """El bug: la ruta apuntaba a un directorio ausente y nadie lo comprobaba.

    Comprobar solo `is_dir()` tampoco habría bastado: un directorio vacío pasa
    la prueba y los jobs siguen muriendo. Se exige el dataset.
    """
    vacio = tmp_path / "vacio"
    vacio.mkdir()
    monkeypatch.setenv("GPAW_SETUP_PATH", str(vacio))
    monkeypatch.delenv("BUHO_GPAW_SETUP_PATH", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "sin-home"))
    monkeypatch.delenv("CONDA_PREFIX", raising=False)
    monkeypatch.setattr(gpaw_setup, "_site_package_dirs", lambda: [])
    assert gpaw_setup.find(tmp_path / "repo") is None


def test_encuentra_por_la_variable_de_entorno(tmp_path, monkeypatch):
    d = _setups_falsos(tmp_path / "propio")
    monkeypatch.setenv("GPAW_SETUP_PATH", str(d))
    assert gpaw_setup.find() == str(d)


def test_prefiere_variable_buho_sobre_gpaw_setup_path(tmp_path, monkeypatch):
    viejo = _setups_falsos(tmp_path / "viejo")
    nuevo = _setups_falsos(tmp_path / "nuevo")
    monkeypatch.setenv("GPAW_SETUP_PATH", str(viejo))
    monkeypatch.setenv("BUHO_GPAW_SETUP_PATH", str(nuevo))
    assert gpaw_setup.find() == str(nuevo)


def test_cae_al_home_cuando_el_venv_no_los_tiene(tmp_path, monkeypatch):
    """Exactamente el caso real: el venv perdió gpaw_data, ~/.gpaw sí los tiene."""
    home = tmp_path / "home"
    d = home / ".gpaw" / "gpaw-setups-24.11.0"
    d.mkdir(parents=True)
    (d / gpaw_setup.MARCADOR).write_bytes(b"")

    monkeypatch.delenv("GPAW_SETUP_PATH", raising=False)
    monkeypatch.delenv("BUHO_GPAW_SETUP_PATH", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(gpaw_setup, "_site_package_dirs", lambda: [])
    assert gpaw_setup.find(tmp_path / "repo-sin-datasets") == str(d)


def test_prefiere_la_version_mas_reciente(tmp_path, monkeypatch):
    home = tmp_path / "home"
    for v in ("24.1.0", "24.11.0", "23.9.1"):
        d = home / ".gpaw" / f"gpaw-setups-{v}"
        d.mkdir(parents=True)
        (d / gpaw_setup.MARCADOR).write_bytes(b"")
    monkeypatch.delenv("GPAW_SETUP_PATH", raising=False)
    monkeypatch.delenv("BUHO_GPAW_SETUP_PATH", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(gpaw_setup, "_site_package_dirs", lambda: [])
    assert gpaw_setup.find().endswith("24.11.0")


def test_sin_datasets_aborta_con_instrucciones(tmp_path, monkeypatch):
    """Fallar aquí cuesta un mensaje; no fallar costaba un lote entero."""
    monkeypatch.delenv("GPAW_SETUP_PATH", raising=False)
    monkeypatch.delenv("BUHO_GPAW_SETUP_PATH", raising=False)
    monkeypatch.delenv("CONDA_PREFIX", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "vacio"))
    monkeypatch.setattr(gpaw_setup, "_site_package_dirs", lambda: [])
    with pytest.raises(SystemExit) as exc:
        gpaw_setup.resolve(tmp_path / "repo")
    mensaje = str(exc.value)
    assert "TODOS los jobs fallan" in mensaje
    assert "gpaw install-data" in mensaje


def test_ningun_runner_conserva_la_ruta_escrita_a_mano():
    """Estaba duplicada en siete archivos; los de producción deben usar el módulo."""
    for rel in ("scripts/buho_relax_runner.py", "src/buho/phase2_force/runner.py"):
        fuente = (ROOT / rel).read_text(encoding="utf-8")
        cuerpo = "\n".join(l for l in fuente.splitlines()
                           if not l.lstrip().startswith("#"))
        assert "gpaw_data" not in cuerpo, f"{rel} sigue con la ruta a mano"
        assert (
            "gpaw_setup.resolve" in cuerpo or "dft_runtime.build_runtime" in cuerpo
        ), f"{rel} no usa el resolutor comun"
