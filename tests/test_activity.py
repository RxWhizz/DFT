"""Actividad del sistema y tiempo estimado."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from monitor_api.main import create_app
from monitor_api.services.activity import duracion_tipica, formatear


# ── Formato ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("segundos,esperado", [
    (12, "12 s"),
    (100, "1 min 40 s"),      # decir «1 min» sería un 40 % de error
    (600, "10 min"),
    (4830, "1 h 20 min"),
    (90000, "1 d 1 h"),
])
def test_formato_legible(segundos, esperado):
    assert formatear(segundos) == esperado


def test_sin_dato_no_se_inventa():
    assert formatear(None) is None
    assert formatear(-5) is None


# ── Duración típica ──────────────────────────────────────────────────────────

def _job(base, nombre, **status):
    d = base / nombre
    d.mkdir(parents=True, exist_ok=True)
    (d / "status.json").write_text(json.dumps(status), encoding="utf-8")
    return d


def test_la_mediana_ignora_los_no_convergidos(tmp_path):
    b = tmp_path / "batch_001"
    for i, s in enumerate([100.0, 110.0, 120.0]):
        _job(b, f"ok{i}", status="converged", elapsed_s=s)
    _job(b, "malo", status="failed", elapsed_s=9999.0)
    _job(b, "corriendo", status="running", elapsed_s=5.0)

    mediana, n = duracion_tipica(b)
    assert mediana == 110.0
    assert n == 3


def test_acepta_elapsed_min_ademas_de_elapsed_s(tmp_path):
    """Las plantillas viejas guardaban minutos; las nuevas, segundos."""
    b = tmp_path / "batch_002"
    for i in range(3):
        _job(b, f"j{i}", status="converged", elapsed_min=2.0)
    mediana, _ = duracion_tipica(b)
    assert mediana == 120.0


def test_sin_muestras_suficientes_no_hay_estimacion(tmp_path):
    """Mejor decir que no se sabe que dar un número que alguien usará."""
    b = tmp_path / "batch_003"
    _job(b, "unico", status="converged", elapsed_s=100.0)
    mediana, n = duracion_tipica(b, minimo=3)
    assert mediana is None
    assert n == 1


def test_amplia_a_otros_lotes_si_el_activo_no_basta(tmp_path):
    activo = tmp_path / "batch_010"
    _job(activo, "j0", status="converged", elapsed_s=100.0)
    viejo = tmp_path / "batch_009"
    for i in range(4):
        _job(viejo, f"j{i}", status="converged", elapsed_s=200.0)

    mediana, n = duracion_tipica(activo, raiz=tmp_path)
    assert mediana is not None and n >= 3


# ── Endpoint ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def sin_procesos_reales(monkeypatch):
    """Aísla los tests del estado de la máquina.

    Dos vías de contagio: la detección de runners mira los procesos del
    sistema, y el poller ahora sigue al lote activo del disco. Con un lote real
    en marcha, un test que apunta al repositorio veía «dft» donde esperaba
    «reposo» — y tenía razón el código, no el test.
    """
    from monitor_api.poller import DFTPoller
    from monitor_api.services import activity as act

    monkeypatch.setattr(act, "runners_activos", lambda: [])
    monkeypatch.setattr(act, "n_calculos_vivos", lambda: 0)
    monkeypatch.setattr(act, "_estado_descubrimiento", lambda: None)
    monkeypatch.setattr(DFTPoller, "_seguir_lote_activo", lambda self: None)
    act._CACHE.update(t=0.0, clave=None, valor=None)


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    monkeypatch.setenv("DFT_MONITOR_CONFIG_DIR", str(tmp_path / "cfg"))

    def _hacer(runs_dir: str, slots: int = 2):
        app = create_app(config={"monitor": {
            "runs_dir": runs_dir, "runner_slots": slots, "auto_advance": False}})
        return TestClient(app)

    return _hacer


def test_lote_terminado_esta_en_reposo(cliente):
    with cliente("local_runs/phase2_force/batch_000") as c:
        d = c.get("/api/activity").json()
    assert d["activity"] == "idle"
    assert d["eta_seconds"] is None


def _lote_con_cola(tmp_path):
    b = tmp_path / "batch_991"
    for i, s in enumerate([100.0, 120.0, 140.0]):
        _job(b, f"conv{i}", status="converged", elapsed_s=s)
    for i in range(8):
        _job(b, f"pend{i}", status="pending")
    return b


def test_lote_en_cola_estima_el_tiempo(cliente, tmp_path):
    lote = _lote_con_cola(tmp_path)
    with cliente(str(lote)) as c:
        d = c.get("/api/activity").json()
    assert d["activity"] in ("queued", "dft")
    assert d["n_pending"] > 0
    if d["eta_seconds"] is not None:
        assert d["eta_text"]
        # La estimación debe decir de dónde sale: un número sin base no sirve.
        assert "mediana" in (d["eta_basis"] or "")


def test_la_concurrencia_divide_la_espera(cliente, tmp_path):
    """Con 8 slots la cola tarda menos que con 1: dividir por 1 daría 8× de más."""
    lote = _lote_con_cola(tmp_path)
    with cliente(str(lote), slots=1) as c:
        lento = c.get("/api/activity").json()
    with cliente(str(lote), slots=8) as c:
        rapido = c.get("/api/activity").json()

    if lento["eta_seconds"] and rapido["eta_seconds"]:
        assert rapido["eta_seconds"] < lento["eta_seconds"]


def test_descubrimiento_aparece_en_la_barra_global(cliente, monkeypatch):
    from monitor_api.services import activity as act

    payload = {
        "state": {
            "status": "dft_selected",
            "current_round": 2,
            "last_prepared": {"n_selected": 30},
        },
        "counts": {"dft_selected": 30},
        "coverage": {"total": 53676, "seen": 53676, "percent": 100.0},
        "queue": [{"candidate_id": "a"} for _ in range(30)],
        "background": {"running": False, "last_error": None},
    }
    monkeypatch.setattr(
        act,
        "_estado_descubrimiento",
        lambda: act._activity_from_discovery_payload(payload),
    )

    with cliente("local_runs/phase2_force/batch_000") as c:
        d = c.get("/api/activity").json()

    assert d["activity"] == "discovery"
    assert d["label"] == "Protocolo listo para DFT"
    assert d["busy"] is False
    assert d["n_done"] == 53676
    assert "30 en cola DFT" in d["detail"]


def test_descubrimiento_avisa_si_dft_no_se_lanzo(cliente, monkeypatch):
    from monitor_api.services import activity as act

    payload = {
        "state": {
            "status": "dft_running",
            "current_round": 0,
            "n_selected_active": 30,
        },
        "counts": {"dft_running": 30},
        "coverage": {"total": 53676, "seen": 53676, "percent": 100.0},
        "queue": [],
        "runner": {
            "stale": True,
            "error": "No se encuentran los datasets PAW de GPAW.",
        },
        "background": {"running": False, "last_error": None},
    }
    monkeypatch.setattr(
        act,
        "_estado_descubrimiento",
        lambda: act._activity_from_discovery_payload(payload),
    )

    with cliente("local_runs/phase2_force/batch_000") as c:
        d = c.get("/api/activity").json()

    assert d["activity"] == "discovery"
    assert d["label"] == "Protocolo DFT no lanzado"
    assert d["busy"] is False
    assert "datasets PAW" in d["detail"]


# ── El poller vigila un lote; el runner puede estar en otro ──────────────────

def test_un_runner_en_otro_lote_no_pasa_por_reposo(cliente, monkeypatch, tmp_path):
    """Regresión: el sistema decía «en reposo» con 20 procesos GPAW calculando.

    `runs_dir` se fija al arrancar y apuntaba a un lote terminado. En cuanto se
    lanza un batch nuevo, el runner trabaja sobre otro directorio y sus jobs no
    aparecen en los snapshots del poller.
    """
    from monitor_api.services import activity as act

    activo = tmp_path / "batch_765153"
    for i in range(3):
        _job(activo, f"conv{i}", status="converged", elapsed_s=100.0)
    for i in range(2):
        _job(activo, f"run{i}", status="running")
    for i in range(7):
        _job(activo, f"pend{i}", status="pending")

    monkeypatch.setattr(act, "runners_activos",
                        lambda: [{"pid": 1, "batch": activo}])
    monkeypatch.setattr(act, "n_calculos_vivos", lambda: 16)
    act._CACHE.update(t=0.0, clave=None, valor=None)

    # runs_dir apunta a un lote terminado, como en el caso real.
    with cliente("local_runs/phase2_force/batch_000") as c:
        d = c.get("/api/activity").json()

    assert d["activity"] == "dft"
    assert d["label"] == "DFT en curso"
    assert "batch_765153" in d["detail"]
    assert d["n_active"] == 2 and d["n_pending"] == 7
    assert d["total"] == 12


def test_el_detalle_cuenta_jobs_no_procesos(cliente, monkeypatch, tmp_path):
    """«20 procesos» junto a «2 en paralelo» se contradecía: son rangos MPI."""
    from monitor_api.services import activity as act

    activo = tmp_path / "batch_1"
    for i in range(2):
        _job(activo, f"run{i}", status="running")
    monkeypatch.setattr(act, "runners_activos", lambda: [{"pid": 1, "batch": activo}])
    monkeypatch.setattr(act, "n_calculos_vivos", lambda: 16)
    act._CACHE.update(t=0.0, clave=None, valor=None)

    with cliente("local_runs/phase2_force/batch_000") as c:
        d = c.get("/api/activity").json()

    assert "2 job(s) calculando" in d["detail"]
    assert "16 procesos MPI" in d["detail"]


def test_expone_los_trabajos_que_calculan(cliente, monkeypatch, tmp_path):
    """El panel de log necesita saber a qué trabajos pedir la cola.

    Antes se alimentaba de `/api/jobs`, que sale de los snapshots del poller y
    solo cubre el `runs_dir` fijado al arrancar: con el runner en otro lote, la
    lista salía vacía mientras la máquina calculaba.
    """
    from monitor_api.services import activity as act

    activo = tmp_path / "batch_986897"
    _job(activo, "vivo1", status="running", formula="CsPbI3")
    _job(activo, "vivo2", status="running", formula="MASnI3")
    _job(activo, "hecho", status="converged", elapsed_s=100.0)

    monkeypatch.setattr(act, "runners_activos", lambda: [{"pid": 1, "batch": activo}])
    monkeypatch.setattr(act, "n_calculos_vivos", lambda: 16)
    act._CACHE.update(t=0.0, clave=None, valor=None)

    with cliente("local_runs/phase2_force/batch_000") as c:
        d = c.get("/api/activity").json()

    ids = {j["job_id"] for j in d["running_jobs"]}
    assert ids == {"vivo1", "vivo2"}
    assert all(j["batch"] == "batch_986897" for j in d["running_jobs"])
    assert {j["formula"] for j in d["running_jobs"]} == {"CsPbI3", "MASnI3"}


def test_en_reposo_no_hay_trabajos_que_seguir(cliente):
    with cliente("local_runs/phase2_force/batch_000") as c:
        d = c.get("/api/activity").json()
    assert d["running_jobs"] == []
