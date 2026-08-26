"""Endpoints de calibración de rendimiento."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from monitor_api.main import create_app


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    monkeypatch.setenv("DFT_MONITOR_CONFIG_DIR", str(tmp_path / "cfg"))
    app = create_app(config={"monitor": {
        "runs_dir": "local_runs/phase2_force/batch_000",
        "runner_slots": 2, "runner_cores": 8, "auto_advance": False,
    }})
    with TestClient(app) as c:
        yield c


def test_estado_inicial(cliente):
    d = cliente.get("/api/bench").json()
    assert d["status"] in ("idle", "done", "error", "interrupted", "cancelled")
    assert d["machine"]["available"] is True
    assert d["machine"]["physical_cores"] >= 1
    assert d["configured_slots"] == 2 and d["configured_cores"] == 8


def test_la_maquina_dice_cuanto_va_a_tardar(cliente):
    """La caja emergente necesita ofrecer la elección con datos, no a ciegas."""
    m = cliente.get("/api/bench").json()["machine"]
    assert m["n_splits_quick"] >= 1
    assert m["n_splits_full"] >= m["n_splits_quick"]
    assert m["budgets"]


def test_cancelar_sin_barrido_da_409(cliente):
    r = cliente.post("/api/bench/cancel")
    assert r.status_code == 409
    assert "marcha" in r.json()["detail"]


def test_modo_invalido_da_409_no_500(cliente):
    r = cliente.post("/api/bench/run", json={"mode": "turbo"})
    assert r.status_code == 422      # lo rechaza el propio esquema


def test_no_se_lanza_con_la_maquina_ocupada(cliente, monkeypatch):
    """Medir con cálculos en marcha recomendaría menos slots de los que aguanta."""
    from monitor_api.services import bench

    monkeypatch.setattr(bench, "busy_reasons", lambda: ["python input.py --config-index 0"])
    r = cliente.post("/api/bench/run", json={"mode": "quick"})
    assert r.status_code == 409
    assert "cálculo" in r.json()["detail"]


def test_un_barrido_muerto_no_bloquea_para_siempre(cliente, monkeypatch, tmp_path):
    """El archivo de progreso puede quedar en «running» si el proceso muere.

    Sin comprobar el PID, la interfaz mostraría un barrido fantasma eterno y
    jamás dejaría lanzar otro.
    """
    from monitor_api.services import bench

    progreso = tmp_path / "progress.json"
    progreso.write_text(json.dumps({"status": "running", "pid": 999999,
                                    "done": 2, "total": 6}))
    monkeypatch.setattr(bench, "_progress_file", lambda: progreso)

    d = cliente.get("/api/bench").json()
    assert d["running"] is False
    assert d["status"] == "interrupted"
