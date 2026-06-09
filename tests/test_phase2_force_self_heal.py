from __future__ import annotations

import json

from buho.phase2_force.collect import collect_labels
from buho.phase2_force.common import label_plan_for_formula
from buho.phase2_force.self_heal import (
    evaluate_u_oscillation_self_heal,
    parse_scf_points,
    status_update_for_u_decision,
)


def _write_status(job, labels):
    job.mkdir(parents=True, exist_ok=True)
    (job / "status.json").write_text(json.dumps({
        "status": "running",
        "candidate_id": job.name,
        "formula": "CsSnI3",
        "labels_expected": labels,
        "started_at": "2026-06-08T20:00:00Z",
    }))


def _write_scf(path, energies, dens=-1.0):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["maxiter: 2000"]
    for idx, energy in enumerate(energies, start=1):
        lines.append(f"iter: {idx:3d} 12:{idx % 60:02d}:00 {energy: .6f} -3.00 {dens: .2f}")
    path.write_text("\n".join(lines) + "\n")


def _write_converged_label(job, label):
    root = job / label["relative_dir"]
    root.mkdir(parents=True, exist_ok=True)
    (root / "label.extxyz").write_text(
        '1\nProperties=species:S:1:pos:R:3 energy=-1.0 candidate_id="abc"\nCs 0 0 0\n'
    )
    (root / "metrics.json").write_text(json.dumps({
        "status": "converged",
        "candidate_id": job.name,
        "formula": "CsSnI3",
        "label": label["label"],
        "method": label["method"],
        "u_ev": label["u_ev"],
        "forces_shape": [1, 3],
        "stress_available": False,
    }))


def test_parse_scf_points_ignores_maxiter(tmp_path):
    log = tmp_path / "u_scan" / "U2p50" / "r2scan.txt"
    _write_scf(log, [-1.0, -2.0])
    points = parse_scf_points(log)
    assert [point["iter"] for point in points] == [1, 2]
    assert points[-1]["energy"] == -2.0


def test_u_oscillation_accepts_previous_converged_u(tmp_path):
    job = tmp_path / "abc"
    labels = label_plan_for_formula("CsSnI3")
    _write_status(job, labels)
    _write_converged_label(job, labels[1])
    _write_scf(job / labels[2]["relative_dir"] / "r2scan.txt", [-70, -95, -60, -100, -65, -92, -61, -98, -64, -96])

    decision = evaluate_u_oscillation_self_heal(job, json.loads((job / "status.json").read_text()))

    assert decision is not None
    assert decision["active_label"] == "U2p50"
    assert decision["accepted_label"] == "U2p25"
    assert decision["self_heal_action"] == "accepted_previous_u_after_oscillation"
    update = status_update_for_u_decision(decision, [123])
    assert update["status"] == "partial"
    assert update["labels"][0]["status"] == "skipped_oscillating"


def test_u2p00_oscillation_fails_without_previous_u(tmp_path):
    job = tmp_path / "abc"
    labels = label_plan_for_formula("CsSnI3")
    _write_status(job, labels)
    _write_scf(job / labels[0]["relative_dir"] / "r2scan.txt", [-70, -95, -60, -100, -65, -92, -61, -98, -64, -96])

    decision = evaluate_u_oscillation_self_heal(job, json.loads((job / "status.json").read_text()))

    assert decision is not None
    assert decision["active_label"] == "U2p00"
    assert decision["accepted_label"] is None
    assert status_update_for_u_decision(decision)["status"] == "failed"


def test_pbe_and_mild_oscillation_do_not_trigger(tmp_path):
    pbe_job = tmp_path / "pbejob"
    pbe_labels = label_plan_for_formula("CsPbI3")
    _write_status(pbe_job, pbe_labels)
    _write_scf(pbe_job / "pbe" / "r2scan.txt", [-70, -95, -60, -100, -65, -92, -61, -98, -64, -96])
    assert evaluate_u_oscillation_self_heal(pbe_job, json.loads((pbe_job / "status.json").read_text())) is None

    mild_job = tmp_path / "mild"
    labels = label_plan_for_formula("CsSnI3")
    _write_status(mild_job, labels)
    _write_scf(mild_job / labels[0]["relative_dir"] / "r2scan.txt", [-70.0, -71.0] * 10)
    assert evaluate_u_oscillation_self_heal(mild_job, json.loads((mild_job / "status.json").read_text())) is None


def test_slow_limit_cycle_triggers(tmp_path):
    job = tmp_path / "slow"
    labels = label_plan_for_formula("CsSnI3")
    _write_status(job, labels)
    energies = [-53.0 if idx % 2 else -54.05 for idx in range(80)]
    _write_scf(job / labels[0]["relative_dir"] / "r2scan.txt", energies, dens=-2.55)

    decision = evaluate_u_oscillation_self_heal(job, json.loads((job / "status.json").read_text()))

    assert decision is not None
    assert decision["oscillation_kind"] == "slow_limit_cycle"


def test_collect_labels_uses_only_accepted_u_from_decision(tmp_path):
    runs = tmp_path / "runs" / "phase2_force"
    job = runs / "batch_000" / "abc"
    labels = label_plan_for_formula("CsSnI3")
    _write_converged_label(job, labels[1])
    _write_converged_label(job, labels[2])
    (job / "u_scan_decision.json").write_text(json.dumps({
        "candidate_id": "abc",
        "formula": "CsSnI3",
        "accepted_label": "U2p25",
        "accepted_u_ev": 2.25,
        "rejected_u_ev": 2.5,
        "reason": "test",
    }))

    out = tmp_path / "data" / "mace_finetune"
    report = tmp_path / "reports" / "training fase 2"
    summary = collect_labels(runs, out, report)

    assert summary["n_labels"] == 1
    assert summary["by_u_ev"] == {"2.25": 1}
    assert summary["n_u_oscillation_self_healed"] == 1
    assert summary["n_u_oscillation_accepted_previous"] == 1
