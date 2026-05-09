"""Tests for the PBE Top 8 comparison scaffolding."""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dft_cspbi3.top8 import (
    TOP8_CANDIDATES,
    build_initial_structure,
    candidate_by_formula,
    prepare_top8_pbe_workspace,
)


def test_top8_candidate_list_has_expected_order():
    assert [c.formula for c in TOP8_CANDIDATES] == [
        "MAPbI3",
        "MASnI3",
        "FAPbI3",
        "FASnI3",
        "CsSnI3",
        "CsPbI3",
        "FAPbBr3",
        "FASnBr3",
    ]


def test_hybrid_initial_structures_have_full_molecular_a_site():
    ma = build_initial_structure(candidate_by_formula("MAPbI3"))
    fa = build_initial_structure(candidate_by_formula("FAPbBr3"))

    ma_symbols = ma.get_chemical_symbols()
    assert ma_symbols.count("C") == 1
    assert ma_symbols.count("N") == 1
    assert ma_symbols.count("H") == 6
    assert ma_symbols.count("Pb") == 1
    assert ma_symbols.count("I") == 3

    fa_symbols = fa.get_chemical_symbols()
    assert fa_symbols.count("C") == 1
    assert fa_symbols.count("N") == 2
    assert fa_symbols.count("H") == 5
    assert fa_symbols.count("Pb") == 1
    assert fa_symbols.count("Br") == 3


def test_prepare_workspace_writes_structures_csv_and_runner(tmp_path):
    work_dir = tmp_path / "calculations" / "top8_pbe"
    structures_dir = tmp_path / "structures" / "top8"

    paths = prepare_top8_pbe_workspace(
        work_dir=work_dir,
        structures_dir=structures_dir,
        comparison_csv=work_dir / "comparison.csv",
        overwrite_structures=True,
    )

    assert paths["comparison_csv"].exists()
    assert paths["run_script"].exists()
    assert (structures_dir / "MAPbI3.json").exists()
    assert (structures_dir / "FASnBr3.cif").exists()

    with paths["comparison_csv"].open() as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 8
    assert rows[0]["material_id"] == "MAPbI3"
    assert "relax,scf,bands,dos,soc,effective_masses,score" in rows[0]["pbe_run_command"]
