"""SCF self-healing helpers for Phase 2A U scans."""

from __future__ import annotations

import json
import math
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCF_ROW_RE = re.compile(
    r"^iter:\s*(?P<iter>\d+)\s+"
    r"(?P<clock>\d{1,2}:\d{2}:\d{2})\s+"
    r"(?P<energy>[-+0-9.eE]+)"
    r"(?:\s+(?P<eigst>[-+0-9.eEc]+)\s+(?P<dens>[-+0-9.eEc]+))?",
    re.MULTILINE,
)

DEFAULT_U_OSCILLATION_CONFIG = {
    "phase2_u_oscillation_self_heal": True,
    "phase2_u_hard_min_iter": 10,
    "phase2_u_hard_window": 6,
    "phase2_u_hard_energy_std_ev": 5.0,
    "phase2_u_hard_energy_range_ev": 15.0,
    "phase2_u_soft_min_iter": 80,
    "phase2_u_soft_window": 40,
    "phase2_u_soft_energy_range_ev": 0.75,
    "phase2_u_density_target_log10": -3.0,
}


def _cfg(cfg: dict[str, Any] | None, key: str) -> Any:
    if cfg is not None and key in cfg:
        return cfg[key]
    return DEFAULT_U_OSCILLATION_CONFIG[key]


def _as_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value.rstrip("c"))
    except ValueError:
        return None


def parse_scf_points(path: Path) -> list[dict[str, Any]]:
    """Parse GPAW SCF rows, ignoring config text such as maxiter=2000."""
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    points: list[dict[str, Any]] = []
    for match in SCF_ROW_RE.finditer(text):
        energy = _as_float(match.group("energy"))
        if energy is None or not math.isfinite(energy):
            continue
        points.append({
            "iter": int(match.group("iter")),
            "clock": match.group("clock"),
            "energy": energy,
            "eigst": _as_float(match.group("eigst")),
            "dens": _as_float(match.group("dens")),
        })
    return points


def _label_entries(job_dir: Path, status: dict[str, Any]) -> list[dict[str, Any]]:
    labels = [dict(item) for item in status.get("labels_expected") or [] if item.get("relative_dir")]
    if labels:
        return labels
    inferred: list[dict[str, Any]] = []
    for path in sorted(job_dir.glob("u_scan/U*/r2scan.txt")):
        label = path.parent.name
        try:
            u_ev = float(label.removeprefix("U").replace("p", "."))
        except ValueError:
            u_ev = None
        inferred.append({
            "label": label,
            "method": "PBE+U",
            "u_ev": u_ev,
            "relative_dir": str(path.parent.relative_to(job_dir)),
        })
    if (job_dir / "pbe" / "r2scan.txt").exists():
        inferred.append({"label": "pbe", "method": "PBE", "u_ev": None, "relative_dir": "pbe"})
    return inferred


def phase2_label_logs(job_dir: Path, status: dict[str, Any],
                      started_epoch: float | None = None) -> list[dict[str, Any]]:
    logs: list[dict[str, Any]] = []
    for label in _label_entries(job_dir, status):
        path = job_dir / str(label["relative_dir"]) / "r2scan.txt"
        if not path.exists():
            continue
        stat = path.stat()
        if started_epoch is not None and stat.st_mtime < started_epoch - 120:
            continue
        points = parse_scf_points(path)
        logs.append({
            "label": label,
            "path": path,
            "relative_path": str(path.relative_to(job_dir)),
            "mtime": stat.st_mtime,
            "size": stat.st_size,
            "points": points,
            "last_iter": points[-1]["iter"] if points else 0,
        })
    return logs


def _range(values: list[float]) -> float:
    return max(values) - min(values) if values else 0.0


def _window_values(points: list[dict[str, Any]], window: int, key: str) -> list[float]:
    values: list[float] = []
    for point in points[-window:]:
        value = point.get(key)
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            values.append(float(value))
    return values


def detect_u_oscillation(points: list[dict[str, Any]],
                         cfg: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if not points:
        return None
    last_iter = int(points[-1]["iter"])
    hard_min = int(_cfg(cfg, "phase2_u_hard_min_iter"))
    hard_window = int(_cfg(cfg, "phase2_u_hard_window"))
    hard_std = float(_cfg(cfg, "phase2_u_hard_energy_std_ev"))
    hard_range = float(_cfg(cfg, "phase2_u_hard_energy_range_ev"))

    if last_iter >= hard_min and len(points) >= hard_window:
        energies = _window_values(points, hard_window, "energy")
        if len(energies) >= hard_window:
            energy_std = statistics.pstdev(energies)
            energy_range = _range(energies)
            if energy_std >= hard_std or energy_range >= hard_range:
                return {
                    "kind": "hard_oscillation",
                    "reason": (
                        f"hard_u_oscillation_iter>={hard_min}; "
                        f"energy_std={energy_std:.3f}eV; energy_range={energy_range:.3f}eV"
                    ),
                    "window": hard_window,
                    "last_iter": last_iter,
                    "energy_std_ev": round(energy_std, 6),
                    "energy_range_ev": round(energy_range, 6),
                    "energy_window": [round(value, 8) for value in energies],
                    "density_window": _window_values(points, hard_window, "dens"),
                }

    soft_min = int(_cfg(cfg, "phase2_u_soft_min_iter"))
    soft_window = int(_cfg(cfg, "phase2_u_soft_window"))
    soft_range = float(_cfg(cfg, "phase2_u_soft_energy_range_ev"))
    density_target = float(_cfg(cfg, "phase2_u_density_target_log10"))
    if last_iter >= soft_min and len(points) >= soft_window:
        energies = _window_values(points, soft_window, "energy")
        densities = _window_values(points, soft_window, "dens")
        if len(energies) >= soft_window and len(densities) >= max(4, soft_window // 2):
            energy_range = _range(energies)
            density_stuck = min(densities) > density_target
            density_improvement = densities[0] - densities[-1]
            if energy_range >= soft_range and density_stuck and density_improvement < 0.3:
                return {
                    "kind": "slow_limit_cycle",
                    "reason": (
                        f"slow_u_limit_cycle_iter>={soft_min}; "
                        f"energy_range={energy_range:.3f}eV; "
                        f"density_min={min(densities):.3f}; density_improvement={density_improvement:.3f}"
                    ),
                    "window": soft_window,
                    "last_iter": last_iter,
                    "energy_std_ev": round(statistics.pstdev(energies), 6),
                    "energy_range_ev": round(energy_range, 6),
                    "energy_window": [round(value, 8) for value in energies],
                    "density_window": [round(value, 8) for value in densities],
                }
    return None


def _previous_label(labels: list[dict[str, Any]], active_label: str) -> dict[str, Any] | None:
    for idx, label in enumerate(labels):
        if label.get("label") == active_label:
            return labels[idx - 1] if idx > 0 else None
    return None


def _converged_metric_for_label(job_dir: Path, label: dict[str, Any] | None) -> dict[str, Any] | None:
    if not label:
        return None
    metrics_path = job_dir / str(label["relative_dir"]) / "metrics.json"
    extxyz_path = job_dir / str(label["relative_dir"]) / "label.extxyz"
    if not metrics_path.exists() or not extxyz_path.exists():
        return None
    try:
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return metrics if metrics.get("status") == "converged" else None


def evaluate_u_oscillation_self_heal(job_dir: Path, status: dict[str, Any],
                                     cfg: dict[str, Any] | None = None,
                                     started_epoch: float | None = None) -> dict[str, Any] | None:
    if not bool(_cfg(cfg, "phase2_u_oscillation_self_heal")):
        return None
    labels = _label_entries(job_dir, status)
    if not labels:
        return None
    logs = [item for item in phase2_label_logs(job_dir, status, started_epoch) if item["points"]]
    if not logs:
        return None
    active = max(logs, key=lambda item: item["mtime"])
    active_label = dict(active["label"])
    if active_label.get("u_ev") is None or not str(active_label.get("relative_dir", "")).startswith("u_scan/"):
        return None

    detection = detect_u_oscillation(active["points"], cfg)
    if detection is None:
        return None

    previous = _previous_label(labels, str(active_label["label"]))
    previous_metrics = _converged_metric_for_label(job_dir, previous)
    accepted_label = previous if previous_metrics else None
    now = datetime.now(timezone.utc).isoformat()
    formula = status.get("formula")
    if not formula and (job_dir / "metadata.json").exists():
        try:
            formula = json.loads((job_dir / "metadata.json").read_text(encoding="utf-8")).get("formula")
        except Exception:
            formula = None

    action = (
        "accepted_previous_u_after_oscillation"
        if accepted_label is not None
        else "failed_oscillating_no_previous_u"
    )
    return {
        "candidate_id": status.get("candidate_id", job_dir.name),
        "formula": formula or job_dir.name,
        "active_label": active_label.get("label"),
        "active_relative_dir": active_label.get("relative_dir"),
        "active_u_ev": active_label.get("u_ev"),
        "accepted_label": accepted_label.get("label") if accepted_label else None,
        "accepted_relative_dir": accepted_label.get("relative_dir") if accepted_label else None,
        "accepted_u_ev": accepted_label.get("u_ev") if accepted_label else None,
        "rejected_label": active_label.get("label"),
        "rejected_u_ev": active_label.get("u_ev"),
        "reason": detection["reason"],
        "oscillation_kind": detection["kind"],
        "last_iter": detection["last_iter"],
        "energy_std_ev": detection["energy_std_ev"],
        "energy_range_ev": detection["energy_range_ev"],
        "energy_window": detection["energy_window"],
        "density_window": detection["density_window"],
        "active_log": active["relative_path"],
        "self_heal_action": action,
        "decided_at": now,
    }


def skipped_label_record(decision: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "skipped_oscillating",
        "candidate_id": decision["candidate_id"],
        "formula": decision["formula"],
        "method": "PBE+U",
        "label": decision["active_label"],
        "relative_dir": decision["active_relative_dir"],
        "u_ev": decision["active_u_ev"],
        "error_message": decision["reason"],
        "oscillation_kind": decision["oscillation_kind"],
        "last_iter": decision["last_iter"],
        "energy_std_ev": decision["energy_std_ev"],
        "energy_range_ev": decision["energy_range_ev"],
        "finished_at": decision["decided_at"],
    }


def status_update_for_u_decision(decision: dict[str, Any], killed_pids: list[int] | None = None) -> dict[str, Any]:
    accepted = decision.get("accepted_label") is not None
    return {
        "status": "partial" if accepted else "failed",
        "self_healed": True,
        "self_heal_action": decision["self_heal_action"],
        "self_heal_reason": decision["reason"],
        "accepted_u_ev": decision.get("accepted_u_ev"),
        "rejected_u_ev": decision.get("rejected_u_ev"),
        "u_scan_decision": decision,
        "labels": [skipped_label_record(decision)],
        "finished_at": decision["decided_at"],
        "updated_at": decision["decided_at"],
        "self_heal_pids": killed_pids or [],
    }


def write_u_scan_decision(job_dir: Path, decision: dict[str, Any], killed_pids: list[int] | None = None) -> None:
    payload = dict(decision)
    payload["killed_pids"] = killed_pids or []
    path = job_dir / "u_scan_decision.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)
