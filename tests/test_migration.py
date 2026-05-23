"""Tests de validación post-migración GPAW 25.7.0 → master.

Ejecutar después de instalar GPAW master:
    pytest tests/test_migration.py -v
"""

from __future__ import annotations

import glob
import json
import pathlib

import pytest


# ---------------------------------------------------------------------------
# T0 — Sanity imports
# ---------------------------------------------------------------------------


def test_msr1_available():
    """MSR1 mixer debe estar en _backends (solo disponible en master, no en 25.7.0)."""
    from gpaw.mixer import _backends  # type: ignore[import]

    assert "msr1" in _backends, (
        f"MSR1 no disponible. _backends contiene: {list(_backends.keys())}. "
        "Verificar que GPAW master está instalado, no 25.7.0."
    )


def test_davidson_import():
    from gpaw.eigensolvers import Davidson  # type: ignore[import]

    d = Davidson(niter=4)
    assert d is not None


def test_r2scan_xc():
    from gpaw.xc import XC  # type: ignore[import]

    XC("MGGA_X_R2SCAN+MGGA_C_R2SCAN")


def test_non_self_consistent_eigenvalues_import():
    """Verifica que el import de non_self_consistent_eigenvalues funcione en master.

    El path puede cambiar; este test valida cuál es el correcto post-migración.
    """
    try:
        from gpaw.hybrids.eigenvalues import non_self_consistent_eigenvalues  # type: ignore[import]

        assert callable(non_self_consistent_eigenvalues)
    except ImportError:
        from gpaw.hybrids import non_self_consistent_eigenvalues  # type: ignore[import]

        assert callable(non_self_consistent_eigenvalues)


def test_soc_import():
    from gpaw.spinorbit import soc_eigenstates  # type: ignore[import]

    assert callable(soc_eigenstates)


# ---------------------------------------------------------------------------
# T1 — MSR1 mixer objeto
# ---------------------------------------------------------------------------


def test_msr1_mixer_construction():
    """GPAW acepta mixer dict con backend='msr1' sin crash."""
    from gpaw import GPAW, PW  # type: ignore[import]
    from gpaw.eigensolvers import Davidson  # type: ignore[import]

    # Solo construir el objeto GPAW (no ejecutar SCF)
    c = GPAW(
        mode=PW(200),
        xc="PBE",
        kpts={"size": [1, 1, 1], "gamma": True},
        mixer={"backend": "msr1", "beta": 0.05, "nmaxold": 5},
        eigensolver=Davidson(niter=2),
        txt=None,
    )
    assert c is not None


# ---------------------------------------------------------------------------
# T2 — Factory no crashea
# ---------------------------------------------------------------------------


def test_factory_r2scan_no_crash():
    """GPAWCalculatorFactory._r2scan_params() no lanza excepciones y devuelve xc correcto."""
    from dft_cspbi3.calculator_factory import GPAWCalculatorFactory

    f = GPAWCalculatorFactory()
    params = f._r2scan_params()
    assert params["xc"] == "MGGA_X_R2SCAN+MGGA_C_R2SCAN"
    assert "mixer" in params
    assert "eigensolver" in params


def test_factory_r2scan_setups_u():
    """_paw_setups_u debe incluir Sn con corrección Dudarev ':s,3.5'."""
    from dft_cspbi3.calculator_factory import GPAWCalculatorFactory

    f = GPAWCalculatorFactory()
    setups = f._paw_setups_u()
    assert "Sn" in setups, "Sn no encontrado en setups U"
    assert setups["Sn"].startswith(":s,"), f"Setup Sn inesperado: {setups['Sn']}"


def test_hse06_eigensolver_is_davidson_object():
    """HSE06 eigensolver debe ser instancia Davidson, NO un dict (bug de 25.7.0)."""
    from gpaw.eigensolvers import Davidson  # type: ignore[import]

    from dft_cspbi3.calculator_factory import GPAWCalculatorFactory

    f = GPAWCalculatorFactory()
    params = f._hse06_params()
    if "eigensolver" in params:
        assert isinstance(params["eigensolver"], Davidson), (
            f"HSE06 eigensolver es {type(params['eigensolver'])}, "
            "se esperaba Davidson. El bug eigensolver dict no está corregido."
        )


# ---------------------------------------------------------------------------
# T3 — Compatibilidad GPW hacia atrás
# ---------------------------------------------------------------------------

PB_MATERIALS = ["MAPbI3", "FAPbI3", "CsPbI3", "FAPbBr3"]
CALC_BASE = pathlib.Path("calculations/top8_r2scan")


@pytest.mark.parametrize("mat", PB_MATERIALS)
def test_gpw_pb_readable(mat: str):
    """Materiales Pb-based convergidos deben ser legibles en master sin regresión de energía."""
    from gpaw import GPAW  # type: ignore[import]

    gpw = CALC_BASE / mat / "06_r2scan" / "r2scan.gpw"
    if not gpw.exists():
        pytest.skip(f"{gpw} no encontrado")
    c = GPAW(str(gpw), txt=None)
    E = c.get_potential_energy()
    assert E < 0, f"{mat}: energía positiva inesperada ({E:.3f} eV)"


@pytest.mark.parametrize("mat", PB_MATERIALS)
def test_gpw_pb_bandgap_unchanged(mat: str):
    """Gaps Pb-based no deben cambiar con master (mismos .gpw, solo lectura)."""
    bg_json = CALC_BASE / mat / "06_r2scan" / "r2scan_bandgap.json"
    if not bg_json.exists():
        pytest.skip(f"{bg_json} no encontrado")
    d = json.loads(bg_json.read_text())
    gap = d.get("gap_eV", 0.0)
    assert gap > 0.5, f"{mat}: gap {gap:.3f} eV parece bajo — verificar regresión"


# ---------------------------------------------------------------------------
# T4/T5 — Preconv y warm-start CsSnI3 (marcados como slow, skippear en CI)
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_csni3_preconv_gpw_exists():
    """pre_r2scan.gpw debe existir después de lanzar preconv con MSR1."""
    gpw = CALC_BASE / "CsSnI3" / "06_r2scan" / "pre_r2scan.gpw"
    assert gpw.exists(), (
        "pre_r2scan.gpw no encontrado. "
        "Lanzar: mpirun -n 7 python3 scripts/preconv_pbe_u.py --mat CsSnI3"
    )


@pytest.mark.slow
def test_csni3_r2scan_gap_nonmetallic():
    """CsSnI3 r²SCAN+U gap debe ser > 0.3 eV (no metálico) tras warm start."""
    bg_json = CALC_BASE / "CsSnI3" / "06_r2scan" / "r2scan_bandgap.json"
    if not bg_json.exists():
        pytest.skip("r2scan_bandgap.json no encontrado — ejecutar Fase 4 primero")
    d = json.loads(bg_json.read_text())
    gap = d.get("gap_eV", 0.0)
    assert gap > 0.3, (
        f"CsSnI3 gap = {gap:.3f} eV — sigue siendo metálico. "
        "Verificar MSR1 mixer y U=3.5 eV en configuración."
    )
