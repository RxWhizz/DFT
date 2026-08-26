"""El monitor debe seguir al lote que de verdad tiene trabajo.

`runs_dir` se fijaba al arrancar y la lógica que debía moverlo tenía cuatro
fallos que se acumulaban:

1. corría una sola vez, antes del bucle de sondeo;
2. buscaba en `runs/batches`, que en esta instalación no existe —los lotes
   viven en `local_runs/phase2_force/`—;
3. exigía un centinela `.runner_launched` que ningún lote preparado desde el
   cribado escribe;
4. iba envuelta en `except Exception: pass`.

El síntoma era el mismo de siempre: la franja decía «en reposo» con veinte
procesos GPAW calculando, los candidatos eran los del mismo lote de hace días,
y el panel de logs no encontraba nada.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from monitor_api.poller import DFTPoller


@pytest.fixture(autouse=True)
def raiz_de_datos_limpia():
    """Devuelve la raíz de datos a su sitio al terminar cada test.

    `set_data_root` es global: un test que la mueve y no la restaura filtra su
    tmp_path a todos los siguientes. Aquí lo detectó `test_bench_api`, que
    buscaba el script del barrido en un directorio temporal vacío.
    """
    from monitor_api import paths

    yield
    paths.reset_data_root()


def _lote(raiz: Path, nombre: str, estados: list[str]) -> Path:
    d = raiz / nombre
    for i, estado in enumerate(estados):
        job = d / f"job{i}"
        job.mkdir(parents=True)
        (job / "status.json").write_text(json.dumps({"status": estado}))
    return d


def _poller(runs_dir: Path, cfg: dict | None = None) -> DFTPoller:
    p = DFTPoller.__new__(DFTPoller)
    p.runs_dir = runs_dir
    p.cfg = cfg or {}
    p._snapshots = {}
    p._batch_done_notified = True
    return p


def test_se_mueve_al_lote_con_trabajo(tmp_path):
    raiz = tmp_path / "phase2_force"
    viejo = _lote(raiz, "batch_000", ["converged"] * 3)
    nuevo = _lote(raiz, "batch_999", ["pending", "running"])

    p = _poller(viejo)
    p._seguir_lote_activo()
    assert p.runs_dir.resolve() == nuevo.resolve()
    assert p._batch_done_notified is False    # se reevalúa el aviso de fin


def test_no_se_mueve_si_el_vigilado_sigue_vivo(tmp_path):
    raiz = tmp_path / "phase2_force"
    vigilado = _lote(raiz, "batch_000", ["running"])
    _lote(raiz, "batch_999", ["pending"])

    p = _poller(vigilado)
    p._seguir_lote_activo()
    assert p.runs_dir.resolve() == vigilado.resolve()


def test_no_exige_el_centinela(tmp_path):
    """Ningún lote preparado desde el cribado escribe `.runner_launched`.

    Exigirlo descartaba justamente los lotes que interesaba encontrar.
    """
    raiz = tmp_path / "phase2_force"
    _lote(raiz, "batch_000", ["converged"])
    activo = _lote(raiz, "batch_777", ["pending"])
    assert not (activo / ".runner_launched").exists()

    p = _poller(raiz / "batch_000")
    p._seguir_lote_activo()
    assert p.runs_dir.resolve() == activo.resolve()


def test_una_config_que_no_existe_no_ciega_la_busqueda(tmp_path):
    """El default era `runs/batches`, inexistente aquí: devolvía None siempre."""
    raiz = tmp_path / "phase2_force"
    _lote(raiz, "batch_000", ["converged"])
    activo = _lote(raiz, "batch_555", ["pending"])

    p = _poller(raiz / "batch_000", cfg={"batches_dir": "runs/batches"})
    p._seguir_lote_activo()
    assert p.runs_dir.resolve() == activo.resolve()


def test_una_config_valida_manda(tmp_path):
    """Si `batches_dir` existe, se respeta: es una decisión del usuario."""
    from monitor_api import paths

    paths.set_data_root(tmp_path)
    otra = tmp_path / "otra_raiz"
    _lote(otra, "batch_111", ["pending"])
    raiz = tmp_path / "phase2_force"
    _lote(raiz, "batch_000", ["converged"])

    p = _poller(raiz / "batch_000", cfg={"batches_dir": "otra_raiz"})
    p._seguir_lote_activo()
    assert p.runs_dir.resolve() == (otra / "batch_111").resolve()


def test_prefiere_el_mas_reciente(tmp_path):
    import os
    import time

    raiz = tmp_path / "phase2_force"
    _lote(raiz, "batch_000", ["converged"])
    antiguo = _lote(raiz, "batch_100", ["pending"])
    reciente = _lote(raiz, "batch_200", ["pending"])
    os.utime(antiguo, (time.time() - 9000, time.time() - 9000))

    p = _poller(raiz / "batch_000")
    p._seguir_lote_activo()
    assert p.runs_dir.resolve() == reciente.resolve()


def test_sin_ningun_lote_activo_se_queda_donde_esta(tmp_path):
    raiz = tmp_path / "phase2_force"
    vigilado = _lote(raiz, "batch_000", ["converged"])
    _lote(raiz, "batch_001", ["failed"])

    p = _poller(vigilado)
    p._seguir_lote_activo()
    assert p.runs_dir.resolve() == vigilado.resolve()


@pytest.mark.parametrize("estado", ["pending", "running", "stalled", "oscillating"])
def test_cuenta_todos_los_estados_que_consumen_tiempo(tmp_path, estado):
    """`stalled` y `oscillating` siguen ocupando la máquina: no son «terminado»."""
    raiz = tmp_path / "phase2_force"
    assert DFTPoller._tiene_activos(_lote(raiz, f"b_{estado}", [estado]))


def test_el_seguimiento_corre_en_cada_ciclo():
    """Antes se evaluaba solo antes del bucle: un lote lanzado después nunca entraba."""
    fuente = Path(__file__).resolve().parents[1] / "src" / "monitor_api" / "poller.py"
    texto = fuente.read_text(encoding="utf-8")
    cuerpo = texto.split("while True:")[1][:400]
    assert "_seguir_lote_activo()" in cuerpo
