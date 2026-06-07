"""Seleccion diversificada de candidatos Fase 1 para etiquetas DFT E+F."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from buho.phase2_force import ROOT
from buho.phase2_force.common import (
    OUT_DIR,
    classify_formula,
    float_or_none,
    label_plan_for_formula,
    read_csv,
    summarize,
    write_csv,
    write_json,
)

TARGET_N = 1000
BATCH_SIZE = 50

CSV_FIELDS = [
    "selection_rank",
    "phase2_batch_id",
    "slot_in_batch",
    "candidate_id",
    "formula",
    "generation_mode",
    "source_type",
    "source_batch",
    "source_file",
    "selection_score",
    "score_raw",
    "total_score",
    "pre_dft_score",
    "is_organic_A",
    "contains_sn",
    "contains_pb",
    "contains_ge",
    "b_family",
    "dominant_halide",
    "n_dft_labels_expected",
    "dft_plan",
    "tolerance_t",
    "oct_factor",
    "vol_est_A3",
    "candidate_json_source",
]


def load_candidate_index(root: Path = ROOT) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    jsonl_paths = [root / "data" / "raw" / "generated_candidates.jsonl"]
    jsonl_paths.extend(sorted((root / "data" / "batches").glob("batch_*/candidates.jsonl")))
    for path in jsonl_paths:
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                data = json.loads(line)
                cid = data.get("candidate_id")
                if not cid:
                    continue
                data["_json_source"] = str(path.relative_to(root))
                index.setdefault(cid, data)
    return index


def _x_fractions(cand: dict[str, Any] | None) -> dict[str, float] | None:
    if not cand:
        return None
    fracs = cand.get("fractions", {}).get("X")
    if not isinstance(fracs, dict):
        return None
    return {str(k): float(v) for k, v in fracs.items()}


def _candidate_source_row(row: dict[str, str], source_file: Path, source_type: str, source_batch: str,
                          candidate_index: dict[str, dict[str, Any]]) -> dict[str, Any]:
    cid = row["candidate_id"]
    cand = candidate_index.get(cid)
    formula = row.get("formula") or (cand or {}).get("formula", "")
    cls = classify_formula(formula, _x_fractions(cand))
    score_raw = (
        float_or_none(row.get("total_score"))
        if source_type == "cascade"
        else float_or_none(row.get("pre_dft_score"))
    )
    if score_raw is None:
        score_raw = 0.0
    plan = label_plan_for_formula(formula)
    return {
        "candidate_id": cid,
        "formula": formula,
        "generation_mode": row.get("generation_mode") or (cand or {}).get("generation_mode", ""),
        "source_type": source_type,
        "source_batch": source_batch,
        "source_file": str(source_file.relative_to(ROOT)),
        "score_raw": score_raw,
        "total_score": row.get("total_score", ""),
        "pre_dft_score": row.get("pre_dft_score", ""),
        "is_organic_A": str(row.get("is_organic_A", (cand or {}).get("is_organic_A", ""))),
        "tolerance_t": row.get("tolerance_t", (cand or {}).get("tolerance_t", "")),
        "oct_factor": row.get("oct_factor", (cand or {}).get("oct_factor", "")),
        "vol_est_A3": row.get("vol_est_A3", (cand or {}).get("vol_est_A3", "")),
        "candidate_json_source": (cand or {}).get("_json_source", ""),
        "n_dft_labels_expected": len(plan),
        "dft_plan": "+".join(item["label"] for item in plan),
        **cls,
    }


def load_phase1_pool(root: Path = ROOT) -> list[dict[str, Any]]:
    candidate_index = load_candidate_index(root)
    rows: list[dict[str, Any]] = []

    top500 = root / "data" / "processed" / "top500_candidates.csv"
    if top500.exists():
        for row in read_csv(top500):
            rows.append(_candidate_source_row(row, top500, "bootstrap_top500", "bootstrap", candidate_index))

    for path in sorted((root / "data" / "batches").glob("batch_*/selected_for_dft.csv")):
        source_batch = path.parent.name
        for row in read_csv(path):
            rows.append(_candidate_source_row(row, path, "cascade", source_batch, candidate_index))

    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        cid = row["candidate_id"]
        previous = best.get(cid)
        # Prefer rows with a candidate JSON source and then higher normalized raw score.
        if previous is None:
            best[cid] = row
            continue
        prev_key = (bool(previous.get("candidate_json_source")), previous["score_raw"])
        new_key = (bool(row.get("candidate_json_source")), row["score_raw"])
        if new_key > prev_key:
            best[cid] = row
    return list(best.values())


def _normalize_scores(rows: list[dict[str, Any]]) -> None:
    by_source: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_source.setdefault(row["source_type"], []).append(row)
    for group in by_source.values():
        vals = [float(row["score_raw"]) for row in group]
        lo, hi = min(vals), max(vals)
        denom = hi - lo if hi > lo else 1.0
        for row in group:
            row["selection_score"] = round((float(row["score_raw"]) - lo) / denom, 6)


def _targets(rows: list[dict[str, Any]], n_target: int) -> dict[tuple[str, str], int]:
    features = ["generation_mode", "source_batch", "b_family", "dominant_halide", "is_organic_A"]
    targets: dict[tuple[str, str], int] = {}
    for feat in features:
        counts = Counter(str(row.get(feat, "")) for row in rows)
        for value, count in counts.items():
            if not value:
                continue
            proportional = round(n_target * count / max(1, len(rows)))
            minimum = 10 if feat in {"generation_mode", "b_family", "dominant_halide"} else 5
            targets[(feat, value)] = min(count, max(minimum, proportional))
    return targets


def diverse_select(rows: list[dict[str, Any]], n_target: int = TARGET_N) -> list[dict[str, Any]]:
    if len(rows) <= n_target:
        return sorted(rows, key=lambda row: (-float(row["selection_score"]), row["candidate_id"]))

    _normalize_scores(rows)
    targets = _targets(rows, n_target)
    counts: Counter[tuple[str, str]] = Counter()
    selected: list[dict[str, Any]] = []
    used: set[str] = set()
    features = ["generation_mode", "source_batch", "b_family", "dominant_halide", "is_organic_A"]

    def adjusted_score(row: dict[str, Any]) -> tuple[float, float, str]:
        score = float(row["selection_score"])
        diversity = 0.0
        for feat in features:
            key = (feat, str(row.get(feat, "")))
            target = targets.get(key)
            if not target:
                continue
            current = counts[key]
            if current < target:
                diversity += 0.018
            else:
                diversity -= 0.035 * ((current - target + 1) / target)
        # score remains primary; diversity breaks near ties and fills soft quotas.
        return (score + diversity, score, row["candidate_id"])

    while len(selected) < n_target:
        best_row = None
        best_key = None
        for row in rows:
            cid = row["candidate_id"]
            if cid in used:
                continue
            key = adjusted_score(row)
            if best_key is None or key > best_key:
                best_key = key
                best_row = row
        if best_row is None:
            break
        selected.append(best_row)
        used.add(best_row["candidate_id"])
        for feat in features:
            counts[(feat, str(best_row.get(feat, "")))] += 1
    return selected


def assign_batches(rows: list[dict[str, Any]], batch_size: int = BATCH_SIZE) -> list[dict[str, Any]]:
    n_batches = max(1, (len(rows) + batch_size - 1) // batch_size)
    slot_counts = [0 for _ in range(n_batches)]
    out: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        batch_id = idx % n_batches
        item = dict(row)
        item["selection_rank"] = idx + 1
        item["phase2_batch_id"] = batch_id
        item["slot_in_batch"] = slot_counts[batch_id]
        slot_counts[batch_id] += 1
        out.append(item)
    return out


def write_selection(rows: list[dict[str, Any]], out_dir: Path = OUT_DIR,
                    batch_size: int = BATCH_SIZE, dry_run: bool = False) -> dict[str, Any]:
    assigned = assign_batches(rows, batch_size=batch_size)
    batches = []
    for batch_id in sorted({int(row["phase2_batch_id"]) for row in assigned}):
        batch_rows = [row for row in assigned if int(row["phase2_batch_id"]) == batch_id]
        batch_file = out_dir / "batches" / f"batch_{batch_id:03d}.csv"
        batches.append({
            "batch_id": batch_id,
            "n_candidates": len(batch_rows),
            "csv": str(batch_file.relative_to(ROOT)),
            "n_expected_dft_labels": sum(int(row["n_dft_labels_expected"]) for row in batch_rows),
            "n_sn_candidates": sum(1 for row in batch_rows if row["contains_sn"]),
        })
        if not dry_run:
            write_csv(batch_file, batch_rows, CSV_FIELDS)

    manifest = {
        "phase": "2A",
        "selection": "top_diverse",
        "n_candidates": len(assigned),
        "batch_size": batch_size,
        "n_batches": len(batches),
        "n_expected_dft_labels": sum(int(row["n_dft_labels_expected"]) for row in assigned),
        "outputs": {
            "candidates_csv": "data/mace_finetune/phase2_candidates_1000.csv",
            "batches_json": "data/mace_finetune/phase2_batches.json",
            "batch_csv_dir": "data/mace_finetune/batches",
        },
        "distribution": summarize(
            assigned,
            ["generation_mode", "source_batch", "b_family", "dominant_halide", "is_organic_A"],
        ),
        "batches": batches,
    }
    if not dry_run:
        write_csv(out_dir / "phase2_candidates_1000.csv", assigned, CSV_FIELDS)
        write_json(out_dir / "phase2_batches.json", manifest)
    return manifest


def select_phase2_candidates(n_target: int = TARGET_N, batch_size: int = BATCH_SIZE,
                             dry_run: bool = False) -> dict[str, Any]:
    pool = load_phase1_pool(ROOT)
    selected = assign_batches(diverse_select(pool, n_target=n_target), batch_size=batch_size)
    manifest = write_selection(selected, OUT_DIR, batch_size=batch_size, dry_run=dry_run)
    manifest["pool_size"] = len(pool)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Selecciona candidatos diversos para Fase 2A.")
    parser.add_argument("--n", type=int, default=TARGET_N)
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    manifest = select_phase2_candidates(args.n, args.batch_size, dry_run=args.dry_run)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
