"""Pruebas de candidatos ABX3, Goldschmidt y scoring."""

from __future__ import annotations

import pytest

from dft_cspbi3.candidates import generate_abx3_candidates, validate_abx3


def test_goldschmidt_cspbi3_reference() -> None:
    from dft_cspbi3.candidates import goldschmidt_tolerance_factor

    value = goldschmidt_tolerance_factor(r_A=1.67, r_B=1.19, r_X=2.20)
    assert value == pytest.approx(0.807, abs=0.01)


def test_goldschmidt_rejects_non_positive_radius() -> None:
    from dft_cspbi3.candidates import goldschmidt_tolerance_factor

    with pytest.raises(ValueError, match="radios ionicos"):
        goldschmidt_tolerance_factor(r_A=0.0, r_B=1.19, r_X=2.20)


def test_validate_abx3_accepts_standard_halide() -> None:
    candidate = validate_abx3("Cs", "Pb", "I")
    assert candidate.formula == "CsPbI3"


def test_validate_abx3_rejects_missing_site() -> None:
    with pytest.raises(ValueError, match="Sitio A vacio"):
        validate_abx3("", "Pb", "I")


def test_validate_abx3_rejects_unsupported_halide() -> None:
    with pytest.raises(ValueError, match="Haluro X no soportado"):
        validate_abx3("Cs", "Pb", "F")


def test_generate_abx3_candidates_cartesian_product() -> None:
    candidates = generate_abx3_candidates(a_site=("Cs", "FA"), b_site=("Pb",), x_site=("I", "Br"))
    assert [candidate.formula for candidate in candidates] == ["CsPbI3", "CsPbBr3", "FAPbI3", "FAPbBr3"]


def test_solar_score_good_direct_gap_not_disqualified() -> None:
    from dft_cspbi3.analysis.scoring import compute_solar_score

    score = compute_solar_score(
        bandgap_eV=1.34,
        gap_type="direct",
        delta_Hf_eV=-0.1,
        m_e=0.2,
        m_h=0.25,
        eps_r=20.0,
        in_gap_dos=0.0,
        phonon_stable=True,
    )
    assert score.disqualified is False
    assert score.total > 80.0


def test_solar_score_tiny_gap_is_disqualified() -> None:
    from dft_cspbi3.analysis.scoring import compute_solar_score

    score = compute_solar_score(bandgap_eV=0.1, gap_type="direct")
    assert score.disqualified is True
    assert "GAP_TOO_SMALL:0.10eV" in score.flags
