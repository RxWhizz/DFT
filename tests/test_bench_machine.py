"""Detección de máquina y planificación del barrido slots×cores."""
from __future__ import annotations

import json

import pytest

from buho.bench import calibration as cal
from buho.bench.machine import (
    Machine, Split, budgets_for, detect, ram_limit_gb, splits_for,
)


def _maquina(**kw) -> Machine:
    base = dict(hostname="prueba", cpu_model="CPU Falsa", physical_cores=44,
                logical_cores=88, sockets=2, numa_nodes=2, ram_total_gb=62.7)
    base.update(kw)
    return Machine(**base)


# ── Detección ────────────────────────────────────────────────────────────────

def test_detect_devuelve_valores_coherentes():
    m = detect()
    assert m.physical_cores >= 1
    assert m.logical_cores >= m.physical_cores
    assert m.ram_total_gb > 0
    assert m.sockets >= 1


def test_la_huella_identifica_el_hardware_no_la_sesion():
    """Renombrar la máquina no debe invalidar horas de medición."""
    assert _maquina(hostname="a").fingerprint == _maquina(hostname="b").fingerprint
    assert _maquina(physical_cores=44).fingerprint != _maquina(physical_cores=16).fingerprint


# ── Planificación ────────────────────────────────────────────────────────────

def test_los_presupuestos_salen_de_la_topologia():
    """Estaban escritos a mano como 44 y 88, para un Xeon concreto."""
    assert budgets_for(_maquina(physical_cores=44, logical_cores=88)) == [44, 88]
    # Sin hyperthreading solo hay un presupuesto que medir.
    assert budgets_for(_maquina(physical_cores=8, logical_cores=8)) == [8]


def test_los_repartos_usan_la_maquina_entera():
    for budget in (8, 16, 44, 64, 88, 128):
        for s in splits_for(budget):
            assert s.total_cores <= budget
            assert s.total_cores >= budget * 0.85, f"{s} desaprovecha {budget}"


def test_se_prefieren_los_divisores_exactos():
    """Un reparto exacto es el que uno escribiría a mano; los casi rellenan."""
    repartos = splits_for(44)
    exactos = [s for s in repartos if s.total_cores == 44]
    assert len(exactos) >= len(repartos) // 2
    for esperado in (Split(1, 44), Split(2, 22), Split(4, 11), Split(44, 1)):
        assert esperado in repartos


def test_no_se_repite_el_mismo_cores():
    """43x1 mide lo mismo que 44x1 con un slot menos: sobra."""
    for budget in (44, 88, 96):
        cores = [s.cores for s in splits_for(budget)]
        assert len(cores) == len(set(cores)), f"cores duplicados en {budget}"


def test_nunca_mas_repartos_de_los_pedidos():
    for budget in (44, 88, 720):
        assert len(splits_for(budget, max_splits=5)) <= 5


def test_presupuestos_degenerados():
    assert splits_for(0) == []
    assert splits_for(1) == [Split(1, 1)]


def test_el_techo_de_ram_deja_margen():
    """Estaba fijo en 52 GB para una máquina de 63; un OOM se lleva todo por delante."""
    m = _maquina(ram_total_gb=62.7)
    limite = ram_limit_gb(m)
    assert 0 < limite < m.ram_total_gb
    assert ram_limit_gb(_maquina(ram_total_gb=16.0)) < 16.0


# ── Calibración ──────────────────────────────────────────────────────────────

def test_guardar_y_recuperar(tmp_path):
    m = _maquina()
    resultados = [
        {"slots": 1, "cores": 44, "n_ok": 1, "throughput": 0.5, "peak_ram_gb": 12.0},
        {"slots": 4, "cores": 11, "n_ok": 4, "throughput": 1.8, "peak_ram_gb": 20.0},
    ]
    c = cal.build(m, 44, resultados)
    assert c is not None and c.best == Split(4, 11)

    cal.save(c, tmp_path)
    leida = cal.load(m, tmp_path)
    assert leida is not None
    assert leida.best == Split(4, 11)
    assert cal.recommended(m, tmp_path) == Split(4, 11)


def test_no_se_pisan_las_calibraciones_de_otras_maquinas(tmp_path):
    a, b = _maquina(physical_cores=44), _maquina(physical_cores=8, logical_cores=8)
    cal.save(cal.build(a, 44, [{"slots": 4, "cores": 11, "n_ok": 4, "throughput": 1.8}]), tmp_path)
    cal.save(cal.build(b, 8, [{"slots": 2, "cores": 4, "n_ok": 2, "throughput": 0.4}]), tmp_path)

    assert cal.recommended(a, tmp_path) == Split(4, 11)
    assert cal.recommended(b, tmp_path) == Split(2, 4)
    guardado = json.loads(cal.calibration_path(tmp_path).read_text())
    assert len(guardado) == 2


def test_un_reparto_que_perdio_jobs_no_puede_ganar(tmp_path):
    """Un split con slots muertos por OOM exhibe throughput alto y engañoso."""
    m = _maquina()
    c = cal.build(m, 44, [
        {"slots": 22, "cores": 2, "n_ok": 3, "throughput": 9.9},   # 19 murieron
        {"slots": 4, "cores": 11, "n_ok": 4, "throughput": 1.8},
    ])
    assert c is not None
    assert c.best == Split(4, 11)


def test_sin_resultados_validos_no_hay_calibracion():
    assert cal.build(_maquina(), 44, []) is None
    assert cal.build(_maquina(), 44, [{"slots": 4, "cores": 11, "n_ok": 0, "throughput": 0}]) is None


def test_sin_medir_no_se_inventa_nada(tmp_path):
    assert cal.load(_maquina(), tmp_path) is None
    assert cal.recommended(_maquina(), tmp_path) is None


def test_un_archivo_corrupto_no_revienta(tmp_path):
    ruta = cal.calibration_path(tmp_path)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text("{ esto no es json", encoding="utf-8")
    assert cal.load(_maquina(), tmp_path) is None


@pytest.mark.parametrize("n", [1, 2, 3, 9, 50])
def test_cualquier_max_splits_es_valido(n):
    """`max_splits=1` dividía por cero en el muestreo logarítmico."""
    repartos = splits_for(44, max_splits=n)
    assert 1 <= len(repartos) <= n
