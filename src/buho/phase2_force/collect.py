"""Recolector de etiquetas DFT Fase 2A para dataset MACE."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from buho.phase2_force import ROOT
from buho.phase2_force.common import OUT_DIR, REPORT_DIR, RUNS_DIR, split_for_candidate, write_json


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _iter_metric_files(runs_dir: Path) -> list[Path]:
    return sorted(runs_dir.glob("batch_*/**/metrics.json"))


def _iter_u_scan_decisions(runs_dir: Path) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    for path in sorted(runs_dir.glob("batch_*/**/u_scan_decision.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        data["_decision_path"] = _rel(path)
        decisions.append(data)
    return decisions


def _read_metric(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if data.get("status") != "converged":
        return None
    label = path.parent / "label.extxyz"
    if not label.exists():
        return None
    data["_metrics_path"] = _rel(path)
    data["_label_extxyz"] = _rel(label)
    return data


def collect_labels(runs_dir: Path = RUNS_DIR, out_dir: Path = OUT_DIR,
                   report_dir: Path = REPORT_DIR) -> dict[str, Any]:
    decisions = _iter_u_scan_decisions(runs_dir)
    decision_by_candidate = {
        item["candidate_id"]: item
        for item in decisions
        if item.get("candidate_id")
    }
    raw_labels = [metric for path in _iter_metric_files(runs_dir) if (metric := _read_metric(path))]
    labels: list[dict[str, Any]] = []
    for metric in raw_labels:
        decision = decision_by_candidate.get(metric.get("candidate_id"))
        if decision and decision.get("accepted_label") is not None:
            if metric.get("label") != decision.get("accepted_label"):
                continue
            metric["_u_scan_decision"] = decision.get("_decision_path")
        labels.append(metric)
    out_dir.mkdir(parents=True, exist_ok=True)
    extxyz_path = out_dir / "phase2_seed.extxyz"

    with extxyz_path.open("w", encoding="utf-8") as out:
        for metric in labels:
            label_path = Path(metric["_label_extxyz"])
            if not label_path.is_absolute():
                label_path = ROOT / label_path
            text = label_path.read_text(encoding="utf-8").rstrip()
            if text:
                out.write(text + "\n")

    split_map: dict[str, list[str]] = {"train": [], "test": []}
    candidate_to_labels: dict[str, list[str]] = defaultdict(list)
    for metric in labels:
        cid = metric["candidate_id"]
        split = split_for_candidate(cid)
        candidate_to_labels[cid].append(metric["_label_extxyz"])
        if cid not in split_map[split]:
            split_map[split].append(cid)

    splits = {
        "policy": "sha1(candidate_id) % 100 < 15 -> test",
        "train": sorted(split_map["train"]),
        "test": sorted(split_map["test"]),
        "candidate_to_labels": {cid: sorted(paths) for cid, paths in sorted(candidate_to_labels.items())},
    }
    write_json(out_dir / "splits.json", splits)

    by_method = Counter(str(metric.get("method")) for metric in labels)
    by_u = Counter(str(metric.get("u_ev")) for metric in labels if metric.get("u_ev") is not None)
    with_stress = sum(1 for metric in labels if metric.get("stress_available"))
    with_forces = sum(1 for metric in labels if metric.get("forces_shape"))
    unique_candidates = sorted({metric["candidate_id"] for metric in labels})
    accepted_decisions = [item for item in decisions if item.get("accepted_label") is not None]

    dft_summary = {
        "status": "labels_available" if labels else "no_labels_yet",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_labels": len(labels),
        "n_unique_candidates": len(unique_candidates),
        "n_with_forces": with_forces,
        "n_with_stress": with_stress,
        "by_method": dict(by_method),
        "by_u_ev": dict(by_u),
        "n_u_oscillation_self_healed": len(decisions),
        "u_oscillation_self_healed": [
            {
                "candidate_id": item.get("candidate_id"),
                "formula": item.get("formula"),
                "accepted_u_ev": item.get("accepted_u_ev"),
                "rejected_u_ev": item.get("rejected_u_ev"),
                "reason": item.get("reason"),
                "decision_path": item.get("_decision_path"),
            }
            for item in decisions
        ],
        "n_u_oscillation_accepted_previous": len(accepted_decisions),
        "extxyz": _rel(extxyz_path),
        "splits": _rel(out_dir / "splits.json"),
        "labels": labels,
    }

    metrics_path = report_dir / "mace_phase2_metrics.json"
    existing = {}
    if metrics_path.exists():
        try:
            existing = json.loads(metrics_path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    existing.update({
        "status": existing.get("status", "not_trained"),
        "model": existing.get("model", "MACE-MP-0 foundation; phase2 fine-tune pending"),
        "real_mace_metrics_available": False,
        "reported_mace_metrics": existing.get("reported_mace_metrics", {}),
        "phase2_dft_labels": dft_summary,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    write_json(metrics_path, existing)
    return dft_summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Recolecta etiquetas DFT Fase 2A en extxyz.")
    parser.add_argument("--runs-dir", default=str(RUNS_DIR))
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    parser.add_argument("--report-dir", default=str(REPORT_DIR))
    args = parser.parse_args()
    result = collect_labels(Path(args.runs_dir), Path(args.out_dir), Path(args.report_dir))
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
