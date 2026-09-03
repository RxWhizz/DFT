"""Tests for DFT result collection fallbacks."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def test_collect_results_falls_back_when_gpw_is_not_readable(tmp_path, monkeypatch):
    from buho.dft_jobs.collect_results import ResultCollector

    job = tmp_path / "abc123"
    job.mkdir()
    (job / "metadata.json").write_text(
        json.dumps(
            {
                "candidate_id": "abc123",
                "formula": "CsSnI3",
                "generation_mode": "pure",
                "n_atoms": 5,
            }
        ),
        encoding="utf-8",
    )
    (job / "status.json").write_text(
        json.dumps(
            {
                "status": "converged",
                "final_energy_eV": -12.5,
                "energy_per_atom_eV": -2.5,
                "elapsed_s": 4.2,
            }
        ),
        encoding="utf-8",
    )
    (job / "r2scan.txt").write_text(
        "Extrapolated:   -12.500000\nGap: 1.234 eV\n",
        encoding="utf-8",
    )
    (job / "relaxed.gpw").write_bytes(b"placeholder")

    def fake_gpw_parse(_self, _gpw, row):
        row["error_message"] = "gpw_parse_error: No module named 'gpaw'"

    monkeypatch.setattr(ResultCollector, "_extract_from_gpw", fake_gpw_parse)

    df = ResultCollector(project_root=ROOT).collect_all(tmp_path)
    row = df.iloc[0]

    assert bool(row["converged"]) is True
    assert bool(row["trusted_label"]) is True
    assert row["final_energy_eV"] == -12.5
    assert row["energy_per_atom_eV"] == -2.5
    assert row["bandgap_preliminary_eV"] == 1.234
    assert row["error_message"] is None
