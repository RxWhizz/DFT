from __future__ import annotations

import json

from buho.phase2_force.collect import collect_labels
from buho.phase2_force.common import classify_formula, label_plan_for_formula, split_for_candidate
from buho.phase2_force.selection import assign_batches


def test_label_plan_for_sn_uses_u_scan():
    labels = label_plan_for_formula("CsSnI3")
    assert [item["label"] for item in labels] == ["U2p00", "U2p25", "U2p50", "U2p75"]
    assert all(item["method"] == "r2SCAN+U" for item in labels)


def test_label_plan_for_non_sn_uses_single_r2scan():
    labels = label_plan_for_formula("CsPbI3")
    assert labels == [{"label": "r2scan", "method": "r2SCAN", "u_ev": None, "relative_dir": "r2scan"}]
    cls = classify_formula("CsGeCl3", {"Cl": 1.0})
    assert cls["b_family"] == "Ge"
    assert cls["dominant_halide"] == "Cl"


def test_assign_batches_round_robin_balances_ranks():
    rows = [{"candidate_id": f"c{i}", "n_dft_labels_expected": 1} for i in range(100)]
    assigned = assign_batches(rows, batch_size=10)
    counts = {}
    for row in assigned:
        counts[row["phase2_batch_id"]] = counts.get(row["phase2_batch_id"], 0) + 1
    assert len(counts) == 10
    assert set(counts.values()) == {10}
    assert assigned[0]["phase2_batch_id"] == 0
    assert assigned[10]["phase2_batch_id"] == 0


def test_collect_labels_writes_extxyz_splits_and_metrics(tmp_path):
    runs = tmp_path / "runs" / "phase2_force"
    label_dir = runs / "batch_000" / "abc123" / "r2scan"
    label_dir.mkdir(parents=True)
    (label_dir / "label.extxyz").write_text(
        '1\nProperties=species:S:1:pos:R:3 energy=-1.0 candidate_id="abc123"\nCs 0 0 0\n'
    )
    (label_dir / "metrics.json").write_text(json.dumps({
        "status": "converged",
        "candidate_id": "abc123",
        "formula": "CsPbI3",
        "method": "r2SCAN",
        "u_ev": None,
        "forces_shape": [1, 3],
        "stress_available": False,
    }))

    out = tmp_path / "data" / "mace_finetune"
    report = tmp_path / "reports" / "training fase 2"
    summary = collect_labels(runs, out, report)

    assert summary["n_labels"] == 1
    assert summary["n_with_forces"] == 1
    assert (out / "phase2_seed.extxyz").read_text().startswith("1\n")
    splits = json.loads((out / "splits.json").read_text())
    split = split_for_candidate("abc123")
    assert "abc123" in splits[split]
    metrics = json.loads((report / "mace_phase2_metrics.json").read_text())
    assert metrics["real_mace_metrics_available"] is False
    assert metrics["phase2_dft_labels"]["n_labels"] == 1

