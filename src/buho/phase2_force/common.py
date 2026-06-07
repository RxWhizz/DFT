"""Utilidades compartidas para Fase 2A."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from buho.phase2_force import ROOT, U_SCAN


OUT_DIR = ROOT / "data" / "mace_finetune"
RUNS_DIR = ROOT / "runs" / "phase2_force"
REPORT_DIR = ROOT / "reports" / "training fase 2"


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        keys: list[str] = []
        seen: set[str] = set()
        for row in rows:
            for key in row:
                if key not in seen:
                    seen.add(key)
                    keys.append(key)
        fieldnames = keys
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "si", "sí"}


def float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def u_stem(u_ev: float) -> str:
    return f"U{u_ev:.2f}".replace(".", "p")


def label_plan_for_formula(formula: str) -> list[dict[str, Any]]:
    if "Sn" in formula:
        return [
            {
                "label": u_stem(u_ev),
                "method": "r2SCAN+U",
                "u_ev": u_ev,
                "relative_dir": f"u_scan/{u_stem(u_ev)}",
            }
            for u_ev in U_SCAN
        ]
    return [{"label": "r2scan", "method": "r2SCAN", "u_ev": None, "relative_dir": "r2scan"}]


def classify_formula(formula: str, x_fractions: dict[str, float] | None = None) -> dict[str, Any]:
    contains_sn = "Sn" in formula
    contains_pb = "Pb" in formula
    contains_ge = "Ge" in formula
    if contains_sn and contains_pb:
        b_family = "SnPb"
    elif contains_sn and contains_ge:
        b_family = "SnGe"
    elif contains_pb and contains_ge:
        b_family = "PbGe"
    elif contains_sn:
        b_family = "Sn"
    elif contains_pb:
        b_family = "Pb"
    elif contains_ge:
        b_family = "Ge"
    else:
        b_family = "other"

    if x_fractions:
        dominant_halide = max(x_fractions, key=lambda key: float(x_fractions[key]))
    else:
        present = [x for x in ("I", "Br", "Cl") if x in formula]
        dominant_halide = "mixed" if len(present) != 1 else present[0]

    return {
        "contains_sn": contains_sn,
        "contains_pb": contains_pb,
        "contains_ge": contains_ge,
        "b_family": b_family,
        "dominant_halide": dominant_halide,
    }


def split_for_candidate(candidate_id: str) -> str:
    digest = int(hashlib.sha1(candidate_id.encode()).hexdigest()[:8], 16)
    return "test" if digest % 100 < 15 else "train"


def summarize(rows: Iterable[dict[str, Any]], keys: Iterable[str]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    materialized = list(rows)
    for key in keys:
        out[key] = dict(Counter(str(row.get(key, "")) for row in materialized))
    return out

