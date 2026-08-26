"""Geometría de las estructuras ABX3 generadas.

Regresión de la avería que dejó sin enlaces a todas las estructuras del cribado:
`build_abx3` fijaba la red con `lattice_est`, que devuelve 2√2·(r_B+r_X) —la
relación A–X— cuando la red cúbica Pm-3m se fija por el enlace B–X, que vale
a/2. Las celdas salían √2 veces dilatadas (CsSnI3 a 9.56 Å en vez de 6.76), con
el armazón B–X a 4.78 Å en lugar de 3.15: sin enlaces que dibujar y, como
avisaba el propio código de `phase2_force`, «casi metálicas».
"""
from __future__ import annotations

import math

import pytest

from ml_surrogate.features import IONIC_RADII, lattice_est

# Cotas físicas de una perovskita de haluro: la red cúbica cae en este rango y
# el enlace B–X mide la mitad.
RED_MIN, RED_MAX = 5.5, 7.5
ENLACE_MIN, ENLACE_MAX = 2.7, 3.8


def a_geometrica(B: str, X: str) -> float:  # noqa: N803
    """La red que `build_abx3` debe usar para construir la celda."""
    return lattice_est(IONIC_RADII[B], IONIC_RADII[X]) / math.sqrt(2.0)


@pytest.mark.parametrize("B,X", [("Pb", "I"), ("Sn", "I"), ("Pb", "Br"), ("Sn", "Br")])
def test_la_red_cae_en_el_rango_fisico(B, X):  # noqa: N803
    a = a_geometrica(B, X)
    assert RED_MIN <= a <= RED_MAX, f"{B}{X}3 -> {a:.2f} Å"


# Solo cationes del sitio B: el cesio y compañía ocupan el sitio A y no forman
# el armazón octaédrico.
@pytest.mark.parametrize("B,X", [("Pb", "I"), ("Sn", "I"), ("Pb", "Br"), ("Sn", "Cl")])
def test_el_enlace_BX_es_fisico(B, X):  # noqa: N803
    """B–X vale a/2 en la cúbica; es la distancia que decide si hay enlace."""
    enlace = a_geometrica(B, X) / 2
    assert ENLACE_MIN <= enlace <= ENLACE_MAX, f"{B}–{X} -> {enlace:.2f} Å"


def test_sin_corregir_la_red_es_inservible():
    """Deja constancia del tamaño del error, para que no se reintroduzca."""
    crudo = lattice_est(IONIC_RADII["Sn"], IONIC_RADII["I"])
    assert crudo > RED_MAX                      # 9.56 Å: fuera de rango
    assert crudo / 2 > ENLACE_MAX               # 4.78 Å: ningún enlace la alcanza
    assert math.isclose(crudo / math.sqrt(2.0), 6.76, abs_tol=0.01)


def test_build_abx3_aplica_la_correccion():
    """La corrección va en el punto de uso, no en `lattice_est`.

    Ese valor es además la característica 11 del surrogate (`a_lat_est_A`), con
    la que se entrenó el modelo: cambiarlo invalidaría las predicciones.
    """
    from pathlib import Path

    fuente = (Path(__file__).resolve().parents[1]
              / "src" / "buho" / "structure" / "build_abx3.py").read_text(encoding="utf-8")
    assert "lattice_est(r_B_eff, r_X_eff) / math.sqrt(2.0)" in fuente

    features = (Path(__file__).resolve().parents[1]
                / "src" / "ml_surrogate" / "features.py").read_text(encoding="utf-8")
    assert "2.0 * _SQRT2 * (r_B + r_X)" in features, "lattice_est no debe cambiar"
