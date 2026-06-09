#!/usr/bin/env python3
"""Actualiza ETA vivo para Fase 2A sin tocar los calculos en marcha."""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from buho.phase2_force.common import OUT_DIR, REPORT_DIR, RUNS_DIR, label_plan_for_formula


REPORT_STEM = "phase2_force_live_eta"
ITER_RE = re.compile(r"iter:\s*(\d+)\s+(\d{1,2}):(\d{2}):(\d{2})")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def parse_iso_epoch(value: str | None) -> float | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def is_fresh(path: Path, started_epoch: float | None, tolerance_s: float = 120.0) -> bool:
    if not path.exists():
        return False
    if started_epoch is None:
        return True
    return path.stat().st_mtime >= started_epoch - tolerance_s


def parse_r2scan(path: Path, started_epoch: float | None) -> dict[str, Any]:
    if not is_fresh(path, started_epoch):
        return {
            "exists": path.exists(),
            "fresh": False,
            "iterations": 0,
            "last_iter": None,
            "avg_t_iter_s": None,
            "last_iter_clock": None,
            "mtime_epoch": path.stat().st_mtime if path.exists() else None,
        }
    text = path.read_text(errors="replace")
    matches = ITER_RE.findall(text)
    clocks: list[int] = []
    iterations: list[int] = []
    for it, hh, mm, ss in matches:
        iterations.append(int(it))
        clocks.append(int(hh) * 3600 + int(mm) * 60 + int(ss))

    avg_t_iter = None
    if len(clocks) >= 2:
        deltas = [(clocks[i] - clocks[i - 1]) % 86400 for i in range(1, len(clocks))]
        if deltas:
            avg_t_iter = sum(deltas) / len(deltas)

    mtime = path.stat().st_mtime
    return {
        "exists": True,
        "fresh": True,
        "iterations": iterations[-1] if iterations else 0,
        "last_iter": iterations[-1] if iterations else None,
        "avg_t_iter_s": round(avg_t_iter, 2) if avg_t_iter is not None else None,
        "last_iter_clock": (
            f"{clocks[-1] // 3600:02d}:{(clocks[-1] % 3600) // 60:02d}:{clocks[-1] % 60:02d}"
            if clocks
            else None
        ),
        "mtime_epoch": mtime,
        "mtime_age_min": round((time.time() - mtime) / 60, 1),
    }


def batch_expected_labels(batch_id: int, fallback: int) -> int:
    data = read_json(OUT_DIR / "phase2_batches.json", {})
    for row in data.get("batches", []):
        try:
            if int(row.get("batch_id")) == batch_id:
                return int(row.get("n_expected_dft_labels") or fallback)
        except Exception:
            continue
    return fallback


def memory_snapshot() -> dict[str, float]:
    text = Path("/proc/meminfo").read_text(encoding="utf-8")

    def grab(name: str) -> int:
        m = re.search(rf"^{name}:\s+(\d+)", text, re.M)
        return int(m.group(1)) if m else 0

    total = grab("MemTotal")
    available = grab("MemAvailable")
    swap_total = grab("SwapTotal")
    swap_free = grab("SwapFree")
    return {
        "ram_used_gb": round((total - available) / 1024 / 1024, 2),
        "ram_available_gb": round(available / 1024 / 1024, 2),
        "swap_used_gb": round((swap_total - swap_free) / 1024 / 1024, 4),
    }


def job_formula(job_dir: Path, status: dict[str, Any]) -> str:
    formula = status.get("formula")
    if formula:
        return str(formula)
    metadata = read_json(job_dir / "metadata.json", {})
    return str(metadata.get("formula") or job_dir.name)


def analyze_job(job_dir: Path, target_iters: int) -> dict[str, Any]:
    status = read_json(job_dir / "status.json", {"status": "unknown", "candidate_id": job_dir.name})
    raw_status = str(status.get("status", "unknown"))
    formula = job_formula(job_dir, status)
    started_epoch = parse_iso_epoch(status.get("started_at") or status.get("start_time"))
    elapsed_min = round((time.time() - started_epoch) / 60, 1) if started_epoch else None
    plan = label_plan_for_formula(formula)

    label_rows: list[dict[str, Any]] = []
    active_assigned = False
    for label in plan:
        label_dir = job_dir / label["relative_dir"]
        metrics_path = label_dir / "metrics.json"
        label_path = label_dir / "label.extxyz"
        metrics_are_current = (
            raw_status not in {"pending", "unknown", "skipped"}
            and is_fresh(metrics_path, started_epoch)
        )
        metrics = read_json(metrics_path, {}) if metrics_are_current else {}
        r2scan = parse_r2scan(label_dir / "r2scan.txt", started_epoch)

        state = "pending"
        if metrics.get("status") == "converged" and label_path.exists():
            state = "converged"
        elif metrics.get("status") == "failed":
            state = "failed"
        elif raw_status == "running" and not active_assigned:
            state = "running"
            active_assigned = True
        elif raw_status in {"converged", "partial", "failed"} and metrics.get("status"):
            state = str(metrics.get("status"))

        remaining_iters = 0
        if state == "converged":
            remaining_iters = 0
        elif state == "failed":
            remaining_iters = target_iters
        elif state == "running":
            remaining_iters = max(0, target_iters - int(r2scan["iterations"] or 0))
        else:
            remaining_iters = target_iters

        label_rows.append({
            "candidate_id": job_dir.name,
            "formula": formula,
            "candidate_status": raw_status,
            "label": label["label"],
            "relative_dir": label["relative_dir"],
            "method": label["method"],
            "u_ev": label["u_ev"],
            "state": state,
            "iterations": int(r2scan["iterations"] or 0),
            "target_iters": target_iters,
            "remaining_iters": remaining_iters,
            "avg_t_iter_s": r2scan["avg_t_iter_s"],
            "last_iter_clock": r2scan["last_iter_clock"],
            "log_age_min": r2scan.get("mtime_age_min"),
            "elapsed_min": elapsed_min,
            "metrics_status": metrics.get("status"),
            "metrics_path": str(metrics_path) if metrics_path.exists() else None,
        })

    return {
        "candidate_id": job_dir.name,
        "formula": formula,
        "status": raw_status,
        "pid": status.get("pid"),
        "started_at": status.get("started_at") or status.get("start_time"),
        "labels": label_rows,
    }


def analyze_batch(batch_dir: Path, batch_id: int, target_iters: int,
                  no_scf_stall_minutes: float) -> dict[str, Any]:
    jobs = [analyze_job(job, target_iters) for job in sorted(batch_dir.iterdir()) if job.is_dir()]
    labels = [label for job in jobs for label in job["labels"]]
    derived_expected = len(labels)
    expected_labels = batch_expected_labels(batch_id, derived_expected)
    completed = sum(1 for label in labels if label["state"] == "converged")
    failed = sum(1 for label in labels if label["state"] == "failed")
    running = [label for label in labels if label["state"] == "running"]
    productive = [
        label
        for label in running
        if label.get("avg_t_iter_s") and float(label["avg_t_iter_s"]) > 0 and int(label.get("iterations") or 0) > 0
    ]
    unproductive = [label for label in running if label not in productive]
    warming_up = [
        label
        for label in unproductive
        if float(label.get("elapsed_min") or 0) < no_scf_stall_minutes
        or (
            label.get("log_age_min") is not None
            and float(label["log_age_min"]) < no_scf_stall_minutes
        )
    ]
    blocked = [label for label in unproductive if label not in warming_up]
    active_progress_iters = sum(int(label.get("iterations") or 0) for label in running)
    active_progress_iter_credit = sum(min(target_iters, int(label.get("iterations") or 0)) for label in running)
    completed_iter_credit = completed * target_iters
    total_target_iters = expected_labels * target_iters
    remaining_iters = max(0, total_target_iters - completed_iter_credit - active_progress_iter_credit)
    throughput_iter_s = sum(1.0 / float(label["avg_t_iter_s"]) for label in productive)
    eta_h = remaining_iters / throughput_iter_s / 3600 if throughput_iter_s > 0 else None

    return {
        "generated_at": utc_now(),
        "batch_id": batch_id,
        "batch_dir": str(batch_dir),
        "target_iters_per_label": target_iters,
        "expected_labels": expected_labels,
        "derived_expected_labels": derived_expected,
        "completed_labels": completed,
        "failed_labels": failed,
        "running_labels": len(running),
        "productive_running_labels": len(productive),
        "warming_up_running_labels": len(warming_up),
        "blocked_running_labels": len(blocked),
        "no_scf_stall_minutes": no_scf_stall_minutes,
        "active_progress_iters": active_progress_iters,
        "active_progress_iter_credit": active_progress_iter_credit,
        "total_target_iters": total_target_iters,
        "remaining_iters_nominal": remaining_iters,
        "throughput_iter_s_live": round(throughput_iter_s, 6),
        "eta_h_live": round(eta_h, 2) if eta_h is not None and math.isfinite(eta_h) else None,
        "memory": memory_snapshot(),
        "jobs": jobs,
        "running_label_rows": running,
        "blocked_label_rows": blocked,
        "warming_up_label_rows": warming_up,
        "productive_label_rows": productive,
    }


def fmt_num(value: Any, digits: int = 2, suffix: str = "") -> str:
    if value is None:
        return "n/d"
    try:
        return f"{float(value):.{digits}f}{suffix}"
    except Exception:
        return f"{value}{suffix}"


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# ETA vivo Fase 2A",
        "",
        f"Generado: `{report['generated_at']}`",
        f"Lote: `batch_{int(report['batch_id']):03d}`",
        "",
        "## Resumen ejecutivo",
        "",
        f"- ETA vivo para `{report['expected_labels']}` labels a `{report['target_iters_per_label']}` iter/label: "
        f"**{fmt_num(report['eta_h_live'], 2, ' h')}**.",
        f"- Throughput vivo productivo: **{fmt_num(report['throughput_iter_s_live'], 6, ' iter/s')}**.",
        f"- Labels: `{report['completed_labels']}` completos, `{report['failed_labels']}` fallidos, "
        f"`{report['running_labels']}` corriendo.",
        f"- Slots productivos: `{report['productive_running_labels']}`; slots sin iteraciones medibles: "
        f"`{report['blocked_running_labels']}` bloqueados, `{report['warming_up_running_labels']}` calentando.",
        f"- Progreso SCF activo: `{report['active_progress_iters']}` / `{report['total_target_iters']}` iter nominales.",
        f"- RAM usada: **{report['memory']['ram_used_gb']} GiB**; RAM disponible: "
        f"**{report['memory']['ram_available_gb']} GiB**; swap usado: **{report['memory']['swap_used_gb']} GiB**.",
        "",
        "## Jobs activos",
        "",
        "| candidato | formula | label | estado | iter | t/iter min | ultima iter | log age min |",
        "|---|---|---|---|---:|---:|---|---:|",
    ]
    for label in report["running_label_rows"]:
        t_iter_min = float(label["avg_t_iter_s"]) / 60 if label.get("avg_t_iter_s") else None
        lines.append(
            f"| `{label['candidate_id']}` | `{label['formula']}` | `{label['label']}` | `{label['state']}` | "
            f"{label['iterations']}/{label['target_iters']} | {fmt_num(t_iter_min, 1)} | "
            f"{label.get('last_iter_clock') or ''} | {label.get('log_age_min') or ''} |"
        )

    if report["warming_up_label_rows"]:
        lines.extend([
            "",
            "## Jobs calentando",
            "",
        ])
        for label in report["warming_up_label_rows"]:
            lines.append(
                f"- `{label['candidate_id']}` `{label['formula']}` esta en `{label['label']}` "
                f"sin iteraciones aun, pero dentro del umbral de self-heal "
                f"({report['no_scf_stall_minutes']:.0f} min)."
            )

    if report["blocked_label_rows"]:
        lines.extend([
            "",
            "## Incidentes que afectan ETA",
            "",
        ])
        for label in report["blocked_label_rows"]:
            lines.append(
                f"- `{label['candidate_id']}` `{label['formula']}` esta en `{label['label']}` "
                "sin iteraciones medibles en el log actual; el ETA vivo queda penalizado por ese slot."
            )

    lines.extend([
        "",
        "## Notas",
        "",
        "- Este ETA usa solo labels en ejecucion con iteraciones SCF medibles.",
        "- Los labels fallidos no se cuentan como completados; quedan como trabajo nominal pendiente para reintento.",
        "- El ETA es operativo, no una metrica MACE ni una etiqueta DFT.",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def write_dashboard(report: dict[str, Any], stem: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    running = report["running_label_rows"]
    labels = [row["candidate_id"][:8] for row in running]
    iters = [int(row.get("iterations") or 0) for row in running]
    target = int(report["target_iters_per_label"])
    tmins = [
        (float(row["avg_t_iter_s"]) / 60 if row.get("avg_t_iter_s") else 0.0)
        for row in running
    ]
    colors = ["#2E8B57" if value > 0 else "#B85750" for value in iters]

    fig, axes = plt.subplots(2, 2, figsize=(14, 9))

    ax = axes[0, 0]
    ax.bar(labels, iters, color=colors)
    ax.axhline(target, color="#6F7785", linestyle="--", linewidth=1.2)
    ax.set_title("Iteraciones SCF activas")
    ax.set_ylabel("iter")
    ax.tick_params(axis="x", rotation=30, labelsize=8)
    ax.grid(axis="y", alpha=0.25)

    ax = axes[0, 1]
    ax.bar(labels, tmins, color=colors)
    ax.set_title("Tiempo por iteracion activo")
    ax.set_ylabel("tiempo (min/iter)")
    ax.tick_params(axis="x", rotation=30, labelsize=8)
    ax.grid(axis="y", alpha=0.25)

    ax = axes[1, 0]
    counts = [
        report["completed_labels"],
        report["failed_labels"],
        report["running_labels"],
        max(
            0,
            report["expected_labels"]
            - report["completed_labels"]
            - report["failed_labels"]
            - report["running_labels"],
        ),
    ]
    count_labels = ["completos", "fallidos", "running", "pendientes"]
    ax.bar(count_labels, counts, color=["#2E8B57", "#B85750", "#C58B19", "#6F7785"])
    ax.set_title("Labels batch 0")
    ax.set_ylabel("labels")
    ax.grid(axis="y", alpha=0.25)

    ax = axes[1, 1]
    ax.axis("off")
    eta = fmt_num(report["eta_h_live"], 2, " h")
    text = (
        f"ETA vivo\\n{eta}\\n\\n"
        f"labels esperados: {report['expected_labels']}\\n"
        f"target: {report['target_iters_per_label']} iter/label\\n"
        f"throughput: {fmt_num(report['throughput_iter_s_live'], 6, ' iter/s')}\\n"
        f"slots productivos: {report['productive_running_labels']}\\n"
        f"slots calentando: {report['warming_up_running_labels']}\\n"
        f"slots sin iter: {report['blocked_running_labels']}\\n"
        f"RAM disp.: {report['memory']['ram_available_gb']} GiB"
    )
    ax.text(0.03, 0.95, text, va="top", ha="left", fontsize=15, family="monospace")

    fig.suptitle("Fase 2A - ETA vivo DFT E+F", fontsize=16, y=0.995)
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(f"{stem}.{ext}", dpi=180, bbox_inches="tight")
    plt.close(fig)


def update_manifest(report: dict[str, Any]) -> None:
    path = REPORT_DIR / "training_phase2_manifest.json"
    manifest = read_json(path, {})
    if not isinstance(manifest, dict):
        return
    manifest["updated_at"] = report["generated_at"]
    manifest["phase2a_live_eta"] = {
        "batch_id": report["batch_id"],
        "target_iters_per_label": report["target_iters_per_label"],
        "expected_labels": report["expected_labels"],
        "eta_h_live": report["eta_h_live"],
        "throughput_iter_s_live": report["throughput_iter_s_live"],
        "productive_running_labels": report["productive_running_labels"],
        "warming_up_running_labels": report["warming_up_running_labels"],
        "blocked_running_labels": report["blocked_running_labels"],
        "source": f"{REPORT_STEM}.json",
    }
    figures = manifest.setdefault("figures", [])
    figures = [fig for fig in figures if fig.get("stem") != REPORT_STEM]
    figures.append({
        "stem": REPORT_STEM,
        "title": "ETA vivo Fase 2A DFT E+F",
        "status": "phase2a_live_eta",
        "png": f"{REPORT_STEM}.png",
        "pdf": f"{REPORT_STEM}.pdf",
        "markdown": f"{REPORT_STEM}.md",
        "json": f"{REPORT_STEM}.json",
        "real_mace_data": False,
        "target_iters_per_label": report["target_iters_per_label"],
        "phase2_batch0_expected_labels": report["expected_labels"],
    })
    manifest["figures"] = figures
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_reports(report: dict[str, Any]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORT_DIR / f"{REPORT_STEM}.json"
    md_path = REPORT_DIR / f"{REPORT_STEM}.md"
    stem = REPORT_DIR / REPORT_STEM
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_markdown(report, md_path)
    write_dashboard(report, stem)
    update_manifest(report)


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera ETA vivo Fase 2A desde logs productivos.")
    parser.add_argument("--batch-id", type=int, default=0)
    parser.add_argument("--target-iters", type=int, default=15)
    parser.add_argument("--no-scf-stall-minutes", type=float, default=60.0)
    parser.add_argument("--runs-dir", type=Path, default=RUNS_DIR)
    args = parser.parse_args()

    batch_dir = args.runs_dir / f"batch_{args.batch_id:03d}"
    if not batch_dir.exists():
        raise SystemExit(f"No existe {batch_dir}")
    report = analyze_batch(batch_dir, args.batch_id, args.target_iters, args.no_scf_stall_minutes)
    write_reports(report)
    print(json.dumps({
        "eta_h_live": report["eta_h_live"],
        "throughput_iter_s_live": report["throughput_iter_s_live"],
        "productive_running_labels": report["productive_running_labels"],
        "warming_up_running_labels": report["warming_up_running_labels"],
        "blocked_running_labels": report["blocked_running_labels"],
        "report": str(REPORT_DIR / f"{REPORT_STEM}.md"),
    }, indent=2))


if __name__ == "__main__":
    main()
