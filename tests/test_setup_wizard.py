"""Tests del runtime MLFF y del wizard de entorno.

Ninguno toca WSL ni instala nada: lo que se comprueba es que el plan que se
construye es el correcto y que la ausencia del entorno MLFF degrada la cascada
en vez de matarla.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


# ── mlff_runtime: resolucion ──────────────────────────────────────────────────


def _cfg(**mlff) -> dict:
    return {
        "discovery": {
            "wsl": {
                "distro": "Ubuntu",
                "project_root": "/mnt/c/repo",
                "python": "/opt/mm/envs/gpaw246/bin/python",
            },
            "mlff": mlff,
        }
    }


def test_resolve_usa_wsl_en_windows_por_defecto(monkeypatch):
    from buho import mlff_runtime

    monkeypatch.setattr(sys, "platform", "win32")
    rt = mlff_runtime.resolve(_cfg(wsl={"python": "/opt/mm/envs/perovowl-mlff/bin/python"}))

    assert rt.backend == "wsl"
    assert rt.python == "/opt/mm/envs/perovowl-mlff/bin/python"
    # La raiz del repo y la distro se heredan del bloque WSL del runner DFT:
    # configurarlas dos veces para la misma maquina seria pedir un error.
    assert rt.distro == "Ubuntu"
    assert rt.worker == "/mnt/c/repo/scripts/buho_mlff_worker.py"


def test_resolve_backend_off_no_ejecuta_nada():
    from buho import mlff_runtime

    rt = mlff_runtime.resolve(_cfg(backend="off"))
    assert rt.backend == "off"
    with pytest.raises(mlff_runtime.MLFFUnavailableError):
        rt.command(["--preflight-only"])


def test_env_var_gana_a_la_config(monkeypatch):
    from buho import mlff_runtime

    monkeypatch.setenv("BUHO_MLFF_BACKEND", "local")
    monkeypatch.setenv("BUHO_MLFF_PYTHON", "/usr/bin/python3")
    rt = mlff_runtime.resolve(_cfg(backend="wsl"))

    assert rt.backend == "local"
    assert rt.python == "/usr/bin/python3"


def test_backend_no_reconocido_es_error_explicito():
    from buho import mlff_runtime

    with pytest.raises(mlff_runtime.MLFFUnavailableError):
        mlff_runtime.resolve(_cfg(backend="quantum"))


def test_command_wsl_incluye_distro_y_cd():
    from buho import mlff_runtime

    rt = mlff_runtime.MLFFRuntime(
        backend="wsl", python="/opt/py", worker="/mnt/c/repo/w.py",
        distro="Ubuntu", project_root="/mnt/c/repo",
    )
    cmd = rt.command(["--preflight-only"])

    assert cmd[:4] == ["wsl.exe", "-d", "Ubuntu", "--"]
    assert cmd[4] == "bash"
    assert "cd /mnt/c/repo" in cmd[-1]
    assert "--preflight-only" in cmd[-1]


def test_command_local_es_argv_directo():
    from buho import mlff_runtime

    rt = mlff_runtime.MLFFRuntime(backend="local", python="/usr/bin/python3", worker="/w.py")
    assert rt.command(["--stdin"]) == ["/usr/bin/python3", "/w.py", "--stdin"]


# ── cascada: degradacion ──────────────────────────────────────────────────────


def _cascade_cfg() -> dict:
    return {
        "random_seed": 42,
        "chemical_space": {"A_sites": ["Cs", "Rb"], "B_sites": ["Pb", "Sn"],
                           "X_sites": ["I", "Br"]},
        "filters": {
            "goldschmidt": {"min": 0.0, "max": 10.0},
            "octahedral": {"min": 0.0, "max": 10.0},
            "volume_A3": {"min": 0.0, "max": 10000.0},
        },
        "structure": {
            "supercell_pure": [1, 1, 1],
            "supercell_mixed": [1, 1, 1],
            "organic_A_placeholder": "Cs",
        },
        "screening": {"tier1_surrogate": False, "tier2_mlff": True,
                      "tier1_gate": False, "tier2_gate": True},
        "acquisition": {"beta": 1.0, "pv_window": [1.1, 1.8]},
        "discovery": {"mlff": {"backend": "off"}},
    }


def _candidatos(n: int = 3):
    from buho.discovery.space import ChemicalSpaceEnumerator

    cfg = _cascade_cfg()
    cfg["generation"] = {
        "fractions": [0.5], "fraction_mode": "discrete",
        "modes": {"pure": True, "A_mixed": False, "B_mixed": False,
                  "X_mixed": False, "multi_mixed": False},
    }
    cfg["discovery"]["space"] = {"min_fraction": 0.5, "max_fraction": 0.5,
                                 "fraction_step": 0.5, "include_multi_mixed": False}
    candidatos, _ = ChemicalSpaceEnumerator(cfg).enumerate(physical_viable_only=True)
    assert len(candidatos) >= n, f"el espacio de prueba solo dio {len(candidatos)} candidatos"
    return candidatos[:n]


def test_tier2_sin_entorno_lanza_error_tipado():
    """Falta del entorno != fallo de un candidato: tiene que ser distinguible."""
    from buho.mlff_runtime import MLFFUnavailableError
    from buho.screening.cascade import ScreeningCascade

    cascade = ScreeningCascade(_cascade_cfg(), project_root=ROOT)
    with pytest.raises(MLFFUnavailableError):
        cascade.screen(_candidatos(), run_mlff=True)


def test_tier2_desactivado_no_impide_tier0(monkeypatch):
    from buho.screening.cascade import ScreeningCascade

    cascade = ScreeningCascade(_cascade_cfg(), project_root=ROOT)
    df = cascade.screen(_candidatos(), run_mlff=False)

    assert not df.empty
    assert set(df["tier_reached"]) <= {0, 1}


class _FakeRuntime:
    """Runtime MLFF que responde sin lanzar procesos."""

    backend = "wsl"

    def __init__(self, respuestas):
        self._respuestas = respuestas
        self.llamadas = []

    def predict(self, candidates, config, timeout=None):
        self.llamadas.append(list(candidates))
        return self._respuestas


def test_tier2_remoto_manda_un_solo_lote_y_mapea_por_id():
    """Cargar MEGNet cuesta mas que predecir: un proceso por lote, no por candidato."""
    from buho.screening.cascade import ScreeningCascade

    candidatos = _candidatos(3)
    respuestas = [
        {"candidate_id": c.candidate_id, "Eg_gnn_eV": 1.4,
         "Eform_megnet_eV_atom": -0.5, "Eform_m3gnet_eV_atom": -0.3,
         "structure_source": "cubic", "error": None}
        for c in candidatos
    ]
    fake = _FakeRuntime(respuestas)
    cascade = ScreeningCascade(_cascade_cfg(), project_root=ROOT, mlff_runtime=fake)

    df = cascade.screen(candidatos, run_mlff=True)

    assert len(fake.llamadas) == 1
    assert len(fake.llamadas[0]) == len(candidatos)
    evaluados = df[df["tier_reached"] == 2]
    assert len(evaluados) == len(candidatos)
    # Eform combinado = media de los dos modelos; std = mitad de la discrepancia.
    assert evaluados["Eform_eV_atom"].iloc[0] == pytest.approx(-0.4)
    assert evaluados["Eform_std_eV_atom"].iloc[0] == pytest.approx(0.1)


def test_tier2_remoto_error_por_candidato_no_tumba_el_lote():
    from buho.screening.cascade import ScreeningCascade

    candidatos = _candidatos(2)
    respuestas = [
        {"candidate_id": candidatos[0].candidate_id, "Eg_gnn_eV": 1.4,
         "Eform_megnet_eV_atom": -0.5, "Eform_m3gnet_eV_atom": -0.5,
         "structure_source": "cubic", "error": None},
        {"candidate_id": candidatos[1].candidate_id,
         "error": "no se pudo construir la estructura: boom"},
    ]
    cascade = ScreeningCascade(_cascade_cfg(), project_root=ROOT,
                               mlff_runtime=_FakeRuntime(respuestas))
    df = cascade.screen(candidatos, run_mlff=True)

    caido = df[df["candidate_id"] == candidatos[1].candidate_id].iloc[0]
    assert caido["dropped_at_tier"] == 2
    assert "boom" in caido["drop_reason"]
    # El otro sobrevive con su Eform: un fallo aislado no invalida el lote.
    vivo = df[df["candidate_id"] == candidatos[0].candidate_id].iloc[0]
    assert vivo["Eform_eV_atom"] == pytest.approx(-0.5)


# ── engine: no dejar el estado atascado ───────────────────────────────────────


def _engine_config(tmp_path: Path) -> Path:
    cfg = {
        "version": "test",
        "random_seed": 42,
        "chemical_space": {"A_sites": ["Cs", "MA"], "B_sites": ["Pb", "Sn"],
                           "X_sites": ["I", "Br"]},
        "generation": {
            "fractions": [0.5], "fraction_mode": "continuous",
            "n_samples_per_combo": 1, "batch_size": 20,
            "modes": {"pure": True, "A_mixed": True, "B_mixed": True,
                      "X_mixed": True, "multi_mixed": False},
        },
        "filters": {
            "goldschmidt": {"min": 0.0, "max": 10.0},
            "octahedral": {"min": 0.0, "max": 10.0},
            "volume_A3": {"min": 0.0, "max": 10000.0},
        },
        "screening": {"tier1_surrogate": False, "tier2_mlff": True,
                      "tier1_gate": False, "tier2_gate": False, "n_dft_per_batch": 0},
        "acquisition": {"beta": 1.0, "pv_window": [1.1, 1.8]},
        "discovery": {
            "output_dir": "data/discovery", "dft_per_round": 3, "min_pv_score": 0.0,
            "frontier_size": 20, "pareto_input_size": 20, "mlff_pool_size": 10,
            "require_mlff_for_dft": True,
            # Sin entorno MLFF: es justo el caso que reventaba la ronda.
            "mlff": {"backend": "off"},
            "space": {"fraction_step": 0.5, "min_fraction": 0.5,
                      "max_fraction": 0.5, "include_multi_mixed": False},
        },
        "paths": {"runs_batches_dir": "runs/batches"},
    }
    path = tmp_path / "generator.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def test_score_space_degrada_a_tier01_sin_entorno_mlff(tmp_path):
    """El bug original: sin torch, la ronda moria y el estado quedaba en 'screening'."""
    from buho.discovery import DiscoveryLoop

    loop = DiscoveryLoop(config_path=_engine_config(tmp_path), project_root=ROOT,
                         data_root=tmp_path, models_root=tmp_path)
    loop.init_space(reset=True)

    screen = loop.score_space()

    assert screen["mlff_warning"] is not None
    assert screen["n_mlff"] == 0
    # Hay frontera pese a no tener Tier 2: require_mlff_for_dft cede cuando el
    # entorno no existe, en vez de dejar 0 elegibles y declarar "done".
    assert screen["n_frontier"] > 0

    estado = loop._load_state()
    assert estado["status"] == "idle"
    assert estado.get("mlff_warning")


def test_score_space_marca_error_en_vez_de_quedarse_en_screening(tmp_path, monkeypatch):
    """Cualquier fallo inesperado debe dejar el estado diagnosticable, no colgado."""
    from buho.discovery import DiscoveryLoop

    loop = DiscoveryLoop(config_path=_engine_config(tmp_path), project_root=ROOT,
                         data_root=tmp_path, models_root=tmp_path)
    loop.init_space(reset=True)

    def _boom(*args, **kwargs):
        raise ValueError("fallo inesperado")

    monkeypatch.setattr(loop, "_load_candidates", _boom)

    with pytest.raises(ValueError):
        loop.score_space()

    estado = loop._load_state()
    assert estado["status"] == "error"
    assert "fallo inesperado" in estado["last_error"]


# ── wizard ────────────────────────────────────────────────────────────────────


def test_plan_mlff_crea_entorno_separado_de_gpaw():
    """Compartir env con gpaw246 romperia GPAW: numpy 1.26 contra numpy>=2."""
    from buho import setup_wizard

    plan = setup_wizard.plan_mlff(_cfg(wsl={
        "env_name": "perovowl-mlff",
        "micromamba": "/opt/mm/bin/micromamba",
        "distro": "Ubuntu",
        "project_root": "/mnt/c/repo",
    }))

    comandos = " ".join(s.shell() for s in plan.steps)
    assert "perovowl-mlff" in comandos
    assert "gpaw246" not in comandos
    assert [s.name for s in plan.steps] == [
        "crear-entorno", "instalar-torch", "instalar-mlff", "verificar",
    ]


def test_plan_mlff_usa_la_rueda_cpu_salvo_que_pidas_cuda():
    from buho import setup_wizard

    base = _cfg(wsl={"micromamba": "/opt/mm/bin/micromamba", "project_root": "/mnt/c/repo"})

    cpu = " ".join(s.shell() for s in setup_wizard.plan_mlff(base).steps)
    assert setup_wizard.TORCH_CPU_INDEX in cpu

    cuda = " ".join(s.shell() for s in setup_wizard.plan_mlff(base, cuda=True).steps)
    assert setup_wizard.TORCH_CPU_INDEX not in cuda


def test_plan_mlff_recrear_borra_antes_y_es_opcional():
    from buho import setup_wizard

    plan = setup_wizard.plan_mlff(
        _cfg(wsl={"micromamba": "/opt/mm/bin/micromamba", "project_root": "/mnt/c/repo"}),
        recrear=True,
    )
    assert plan.steps[0].name == "limpiar"
    # Que no exista todavia no puede abortar la creacion.
    assert plan.steps[0].opcional


def test_plan_deduce_micromamba_del_runtime_gpaw():
    """La raiz de micromamba sale de donde ya vive el python de GPAW."""
    from buho import setup_wizard

    plan = setup_wizard.plan_mlff({"discovery": {
        "wsl": {"python": "/home/u/mm/envs/gpaw246/bin/python", "project_root": "/mnt/c/repo"},
    }})
    assert "/home/u/mm/bin/micromamba" in plan.steps[0].shell()


def test_plan_pip_se_niega_en_binario_congelado(monkeypatch):
    from buho import setup_wizard

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    plan = setup_wizard.plan_pip("web")

    assert plan.steps == []
    assert any("congelado" in n for n in plan.notas)


def test_plan_objetivo_desconocido():
    from buho import setup_wizard

    with pytest.raises(ValueError):
        setup_wizard.plan("no-existe")


def test_check_devuelve_matriz_de_capacidades():
    from buho import setup_wizard

    data = setup_wizard.check({}, project_root=ROOT, incluir_mlff=False)

    assert data["status"] in {"ok", "degradado", "error"}
    ids = {c["id"] for c in data["capacidades"]}
    assert {"core", "web", "dft", "paw"} <= ids
    for cap in data["capacidades"]:
        assert {"id", "titulo", "ok", "requerido", "remediacion"} <= set(cap)


# ── API ───────────────────────────────────────────────────────────────────────


def test_endpoints_setup_responden(monkeypatch):
    pytest.importorskip("fastapi", reason="requiere el extra [web]")
    from fastapi.testclient import TestClient

    from monitor_api.main import create_app
    from monitor_api.services import setup as service

    estado = {
        "status": "degradado", "ok": True, "plataforma": "win32",
        "python": "3.12.10", "executable": "py.exe", "frozen": False,
        "capacidades": [{"id": "mlff", "titulo": "MLFF", "ok": False,
                         "requerido": False, "detalle": {}, "error": "falta",
                         "remediacion": "instala", "comando": "buho setup install mlff"}],
        "job": {"running": False, "log": []},
    }
    llamadas: dict = {}

    monkeypatch.setattr(service, "status", lambda fast=False: {**estado, "fast": fast})
    monkeypatch.setattr(service, "job", lambda: {"running": False, "log": []})
    monkeypatch.setattr(service, "plan", lambda target, **kw: {"target": target, "steps": [], "notas": []})
    def _install(target, **kw):
        llamadas["install"] = (target, kw)
        return {"running": True, "log": []}

    monkeypatch.setattr(service, "start_install", _install)

    client = TestClient(create_app())

    assert client.get("/api/setup/status").json()["status"] == "degradado"
    # El flag `fast` tiene que llegar al servicio: es lo que evita sondear WSL.
    assert client.get("/api/setup/status", params={"fast": True}).json()["fast"] is True
    assert client.get("/api/setup/job").json()["running"] is False
    assert client.post("/api/setup/plan", json={"target": "mlff"}).json()["target"] == "mlff"

    r = client.post("/api/setup/install", json={"target": "mlff", "recreate": True})
    assert r.status_code == 200
    target, kw = llamadas["install"]
    assert target == "mlff"
    assert kw["recrear"] is True


def test_install_en_curso_responde_409(monkeypatch):
    pytest.importorskip("fastapi", reason="requiere el extra [web]")
    from fastapi.testclient import TestClient

    from monitor_api.main import create_app
    from monitor_api.services import setup as service

    def _ocupado(target, **kw):
        raise RuntimeError("Ya hay una instalación en curso.")

    monkeypatch.setattr(service, "start_install", _ocupado)
    r = TestClient(create_app()).post("/api/setup/install", json={"target": "mlff"})

    # 409, no 500: es una colisión de estado, no un fallo del servidor.
    assert r.status_code == 409
    assert "en curso" in r.json()["detail"]


def test_opciones_solo_se_pasan_a_mlff():
    from monitor_api.router import SetupInstallRequest, _setup_opciones

    assert _setup_opciones(SetupInstallRequest(target="web", cuda=True)) == {}
    opts = _setup_opciones(SetupInstallRequest(target="mlff", cuda=True))
    assert opts["cuda"] is True


# ── Troceado del lote ─────────────────────────────────────────────────────────


def test_predict_trocea_el_lote(monkeypatch):
    """5000 candidatos en una llamada son 5 MB de stdin y 7 min sin señales."""
    from buho import mlff_runtime

    rt = mlff_runtime.MLFFRuntime(backend="local", python="/py", worker="/w.py",
                                  chunk_size=2)
    trozos: list[int] = []

    # MLFFRuntime es un dataclass frozen: se parchea la clase, no la instancia.
    def _run(self, args, stdin=None, timeout=None):
        import json as _json
        enviados = _json.loads(stdin)["candidates"]
        trozos.append(len(enviados))
        return {"results": [{"candidate_id": c["candidate_id"]} for c in enviados]}

    monkeypatch.setattr(mlff_runtime.MLFFRuntime, "_run", _run)
    cands = [{"candidate_id": str(i)} for i in range(5)]
    out = rt.predict(cands, {})

    assert trozos == [2, 2, 1]
    # Trocear no puede perder ni reordenar resultados.
    assert [r["candidate_id"] for r in out] == ["0", "1", "2", "3", "4"]


def test_predict_lote_vacio_no_lanza_proceso(monkeypatch):
    from buho import mlff_runtime

    rt = mlff_runtime.MLFFRuntime(backend="local", python="/py", worker="/w.py")
    monkeypatch.setattr(mlff_runtime.MLFFRuntime, "_run",
                        lambda *a, **k: pytest.fail("no debía ejecutarse"))

    assert rt.predict([], {}) == []


def test_chunk_size_sale_de_la_config():
    from buho import mlff_runtime

    rt = mlff_runtime.resolve(_cfg(backend="local", chunk_size=250))
    assert rt.chunk_size == 250
    assert mlff_runtime.resolve(_cfg(backend="local")).chunk_size == mlff_runtime.DEFAULT_CHUNK


def test_estado_atascado_en_screening_se_recupera_solo(tmp_path):
    """El caso real: la ronda murió por falta de torch y dejó el estado colgado.

    `advance()` no trata "screening" como un estado en curso, así que vuelve a
    cribar; lo que importa es que ahora esa criba termina en vez de repetir el
    mismo fallo, y que el estado deja de estar colgado sin tocar nada a mano.
    """
    from buho.discovery import DiscoveryLoop

    loop = DiscoveryLoop(config_path=_engine_config(tmp_path), project_root=ROOT,
                         data_root=tmp_path, models_root=tmp_path)
    loop.init_space(reset=True)

    # Se reproduce el estado que dejó el fallo del 2026-09-03.
    estado = loop._load_state()
    estado["status"] = "screening"
    estado["current_round"] = 1
    loop._save_state(estado)

    loop.score_space()

    recuperado = loop._load_state()
    assert recuperado["status"] == "idle"
    assert recuperado.get("mlff_warning")


def test_versiones_siempre_es_un_mapa(monkeypatch):
    """La GUI itera `versiones`; un string se pintaría como un chip por letra."""
    from buho import setup_wizard

    class _Proc:
        returncode = 0
        stdout = "24.6.0 3.29.0\n"
        stderr = ""

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(setup_wizard, "_wsl_disponible", lambda: True)
    monkeypatch.setattr(setup_wizard, "_run_wsl", lambda *a, **k: _Proc())

    cap = setup_wizard._check_dft(_cfg())

    assert cap["ok"]
    assert cap["detalle"]["versiones"] == {"gpaw": "24.6.0", "ase": "3.29.0"}


def test_versiones_vacio_si_wsl_no_responde(monkeypatch):
    from buho import setup_wizard

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(setup_wizard, "_wsl_disponible", lambda: True)
    monkeypatch.setattr(setup_wizard, "_run_wsl", lambda *a, **k: None)

    cap = setup_wizard._check_dft(_cfg())

    assert not cap["ok"]
    assert cap["detalle"]["versiones"] == {}
