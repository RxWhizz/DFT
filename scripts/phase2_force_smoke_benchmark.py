#!/usr/bin/env python3
"""Smoke and startup benchmark for Phase 2A DFT force labeling."""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import py_compile
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from buho.phase2_force.common import OUT_DIR, REPORT_DIR, RUNS_DIR, label_plan_for_formula, read_csv
from buho.phase2_force.prepare import prepare_batch
from buho.phase2_force.runner import active_dft_processes, run_batch


CONDA = Path.home() / "miniforge3" / "bin" / "conda"
GPAW_PY = Path.home() / "miniforge3" / "envs" / "gpaw246" / "bin" / "python3"
EXTERNAL_VOLUME = Path("/media/luis-ochoa/Nuevo vol")
SMOKE_ROOT = RUNS_DIR.parent / "_phase2_force_smokes"
OUT_JSON = REPORT_DIR / "phase2_force_smoke_benchmark.json"
OUT_MD = REPORT_DIR / "phase2_force_smoke_benchmark.md"
OUT_FIG = REPORT_DIR / "phase2_force_smoke_benchmark"
DEFAULT_SMOKE_JOBS = 10


class SmokeError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def run_check(name: str, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    t0 = time.time()
    try:
        data = fn()
        status = "pass"
        error = None
    except Exception as exc:
        data = {}
        status = "fail"
        error = str(exc)
    return {
        "name": name,
        "status": status,
        "elapsed_s": round(time.time() - t0, 3),
        "error": error,
        **data,
    }


def check_py_compile() -> dict[str, Any]:
    paths = [
        ROOT / "src" / "buho" / "phase2_force" / "__init__.py",
        ROOT / "src" / "buho" / "phase2_force" / "common.py",
        ROOT / "src" / "buho" / "phase2_force" / "selection.py",
        ROOT / "src" / "buho" / "phase2_force" / "prepare.py",
        ROOT / "src" / "buho" / "phase2_force" / "runner.py",
        ROOT / "src" / "buho" / "phase2_force" / "collect.py",
        ROOT / "src" / "buho" / "phase2_force" / "__main__.py",
        ROOT / "scripts" / "phase2_force_select.py",
        ROOT / "scripts" / "phase2_force_prepare.py",
        ROOT / "scripts" / "phase2_force_runner.py",
        ROOT / "scripts" / "phase2_force_collect.py",
        ROOT / "scripts" / "generate_phase2_training_report.py",
        ROOT / "scripts" / "phase2_force_smoke_benchmark.py",
        ROOT / "tests" / "test_phase2_force.py",
    ]
    for path in paths:
        py_compile.compile(str(path), doraise=True)
    return {"n_files": len(paths), "files": [rel(p) for p in paths]}


def check_direct_tests() -> dict[str, Any]:
    test_path = ROOT / "tests" / "test_phase2_force.py"
    spec = importlib.util.spec_from_file_location("test_phase2_force_smoke", test_path)
    if spec is None or spec.loader is None:
        raise SmokeError(f"No pude cargar {test_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.test_label_plan_for_sn_uses_u_scan()
    module.test_label_plan_for_non_sn_uses_single_r2scan()
    module.test_assign_batches_round_robin_balances_ranks()
    with tempfile.TemporaryDirectory(prefix="phase2_collect_smoke_") as tmp:
        module.test_collect_labels_writes_extxyz_splits_and_metrics(Path(tmp))
    return {
        "n_tests": 4,
        "tests": [
            "label_plan_for_sn_uses_u_scan",
            "label_plan_for_non_sn_uses_single_r2scan",
            "assign_batches_round_robin_balances_ranks",
            "collect_labels_writes_extxyz_splits_and_metrics",
        ],
    }


def check_gpaw_env() -> dict[str, Any]:
    if not CONDA.exists():
        raise SmokeError(f"No existe conda en {CONDA}")
    if not GPAW_PY.exists():
        raise SmokeError(f"No existe python gpaw246 en {GPAW_PY}")
    code = (
        "import json, ase, gpaw, numpy, yaml; "
        "print(json.dumps({'ase': ase.__version__, 'gpaw': gpaw.__version__, "
        "'numpy': numpy.__version__, 'yaml': yaml.__version__}))"
    )
    proc = subprocess.run([str(GPAW_PY), "-c", code], capture_output=True, text=True, check=True)
    versions = json.loads(proc.stdout.strip())
    mpiexec = shutil.which("mpiexec") or shutil.which("mpirun")
    if not mpiexec:
        raise SmokeError("No encontre mpiexec/mpirun en PATH")
    return {"versions": versions, "mpiexec": mpiexec}


def check_selection() -> dict[str, Any]:
    candidates = OUT_DIR / "phase2_candidates_1000.csv"
    batches_json = OUT_DIR / "phase2_batches.json"
    batch_dir = OUT_DIR / "batches"
    if not candidates.exists():
        raise SmokeError(f"Falta {rel(candidates)}")
    if not batches_json.exists():
        raise SmokeError(f"Falta {rel(batches_json)}")
    rows = read_csv(candidates)
    if len(rows) != 1000:
        raise SmokeError(f"Esperaba 1000 candidatos, encontre {len(rows)}")
    unique = {row["candidate_id"] for row in rows}
    if len(unique) != len(rows):
        raise SmokeError("Hay candidate_id duplicados en phase2_candidates_1000.csv")
    batch_files = sorted(batch_dir.glob("batch_*.csv"))
    if len(batch_files) != 20:
        raise SmokeError(f"Esperaba 20 batches, encontre {len(batch_files)}")
    batch_sizes = []
    expected_labels = 0
    sn_counts = []
    for path in batch_files:
        batch_rows = read_csv(path)
        batch_sizes.append(len(batch_rows))
        expected_labels += sum(int(row["n_dft_labels_expected"]) for row in batch_rows)
        sn_counts.append(sum(1 for row in batch_rows if str(row.get("contains_sn")).lower() == "true"))
    if set(batch_sizes) != {50}:
        raise SmokeError(f"Los batch sizes no son todos 50: {sorted(set(batch_sizes))}")
    return {
        "n_candidates": len(rows),
        "n_unique": len(unique),
        "n_batches": len(batch_files),
        "batch_sizes": sorted(set(batch_sizes)),
        "expected_dft_labels": expected_labels,
        "sn_per_batch_min": min(sn_counts),
        "sn_per_batch_max": max(sn_counts),
        "generation_mode": dict(Counter(row.get("generation_mode", "") for row in rows)),
        "b_family": dict(Counter(row.get("b_family", "") for row in rows)),
        "dominant_halide": dict(Counter(row.get("dominant_halide", "") for row in rows)),
    }


def check_method_plan() -> dict[str, Any]:
    sn_labels = [item["label"] for item in label_plan_for_formula("CsSnI3")]
    no_sn = label_plan_for_formula("CsPbI3")
    required = ["U2p00", "U2p25", "U2p50", "U2p75"]
    if sn_labels != required:
        raise SmokeError(f"Plan Sn inesperado: {sn_labels}")
    if no_sn != [{"label": "r2scan", "method": "r2SCAN", "u_ev": None, "relative_dir": "r2scan"}]:
        raise SmokeError(f"Plan no-Sn inesperado: {no_sn}")
    batch0 = read_csv(OUT_DIR / "batches" / "batch_000.csv")
    has_sn = any("U2p00" in row.get("dft_plan", "") for row in batch0)
    has_r2 = any(row.get("dft_plan") == "r2scan" for row in batch0)
    if not (has_sn and has_r2):
        raise SmokeError("batch_000 no cubre simultaneamente Sn+U y r2SCAN no-Sn")
    return {
        "sn_plan": sn_labels,
        "non_sn_plan": [item["label"] for item in no_sn],
        "batch0_sn_jobs": sum(1 for row in batch0 if "U2p00" in row.get("dft_plan", "")),
        "batch0_non_sn_jobs": sum(1 for row in batch0 if row.get("dft_plan") == "r2scan"),
    }


def check_prepare_smoke(limit: int = DEFAULT_SMOKE_JOBS) -> dict[str, Any]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    runs_dir = SMOKE_ROOT / stamp
    manifest = prepare_batch(0, runs_dir=runs_dir, n_cores=8, limit=limit, dry_run=False)
    if manifest["n_prepared"] != limit:
        raise SmokeError(f"Smoke preparo {manifest['n_prepared']} jobs, esperaba {limit}")
    batch_dir = runs_dir / "batch_000"
    job_dirs = [p for p in sorted(batch_dir.iterdir()) if p.is_dir()]
    if len(job_dirs) != limit:
        raise SmokeError(f"Smoke tiene {len(job_dirs)} dirs de job, esperaba {limit}")
    labels_seen: set[str] = set()
    for job in job_dirs:
        status = json.loads((job / "status.json").read_text(encoding="utf-8"))
        for label in status["labels_expected"]:
            labels_seen.add(label["label"])
            if not (job / label["relative_dir"]).is_dir():
                raise SmokeError(f"Falta subdir {label['relative_dir']} en {rel(job)}")
        text = (job / "input.py").read_text(encoding="utf-8")
        for needle in ("FIRE(", "steps=2", "label.extxyz", "forces_max_eVA"):
            if needle not in text:
                raise SmokeError(f"input.py no contiene {needle}")
    required = {"r2scan", "U2p00", "U2p25", "U2p50", "U2p75"}
    if not required.issubset(labels_seen):
        raise SmokeError(f"Smoke no cubrio todos los metodos: {sorted(labels_seen)}")
    dry = run_batch(0, slots=5, cores=8, poll=1, dry_run=True, runs_dir=runs_dir)
    if dry.get("n_pending") != limit:
        raise SmokeError(f"Runner dry-run vio {dry.get('n_pending')} pending, esperaba {limit}")
    return {
        "smoke_runs_dir": rel(runs_dir),
        "n_prepared": manifest["n_prepared"],
        "n_benchmark_jobs": limit,
        "labels_seen": sorted(labels_seen),
        "runner_dry_run": dry,
    }


def check_active_processes() -> dict[str, Any]:
    active = active_dft_processes()
    if active:
        raise SmokeError("Hay procesos DFT/runner activos:\n" + "\n".join(active[:10]))
    return {"active_processes": []}


def check_storage(require_external: bool) -> dict[str, Any]:
    repo_usage = shutil.disk_usage(ROOT)
    external_exists = EXTERNAL_VOLUME.exists()
    external_mounted = os.path.ismount(EXTERNAL_VOLUME)
    external_usage = None
    if external_exists:
        try:
            usage = shutil.disk_usage(EXTERNAL_VOLUME)
            external_usage = {
                "total_gb": round(usage.total / 1024**3, 2),
                "free_gb": round(usage.free / 1024**3, 2),
            }
        except OSError:
            external_usage = None
    data = {
        "repo_free_gb": round(repo_usage.free / 1024**3, 2),
        "repo_total_gb": round(repo_usage.total / 1024**3, 2),
        "external_volume": str(EXTERNAL_VOLUME),
        "external_exists": external_exists,
        "external_mounted": external_mounted,
        "external_usage": external_usage,
        "default_runs_dir": rel(RUNS_DIR),
        "require_external": require_external,
    }
    if require_external and not external_mounted:
        raise SmokeError(f"El volumen externo requerido no esta montado: {EXTERNAL_VOLUME}")
    return data


def load_performance_reference() -> dict[str, Any]:
    path = ROOT / "reports" / "performance_benchmark.csv"
    if not path.exists():
        return {"source": rel(path), "available": False}
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    rec = next((row for row in rows if str(row.get("recommended")).lower() == "true"), None)
    if rec is None and rows:
        rec = max(rows, key=lambda r: float(r.get("throughput_iter_s") or 0))
    if rec is None:
        return {"source": rel(path), "available": False}
    return {
        "source": rel(path),
        "available": True,
        "recommended_split": rec.get("split"),
        "slots": int(float(rec.get("slots", 0))),
        "cores_per_slot": int(float(rec.get("cores_per_slot", 0))),
        "total_cores": int(float(rec.get("total_cores", 0))),
        "throughput_iter_s": float(rec.get("throughput_iter_s", 0)),
        "t_iter_s": float(rec.get("t_iter_s", 0)),
        "peak_ram_gb": float(rec.get("peak_ram_gb", 0)),
        "eta_482_h": float(rec.get("eta_482_h", 0)),
    }


def official_run_state() -> dict[str, Any]:
    statuses: Counter[str] = Counter()
    job_count = 0
    if RUNS_DIR.exists():
        for path in RUNS_DIR.glob("batch_*/**/status.json"):
            if path.parent.name.startswith("."):
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                statuses["unreadable"] += 1
                continue
            statuses[str(data.get("status", "unknown"))] += 1
            job_count += 1
    return {
        "runs_dir": rel(RUNS_DIR),
        "exists": RUNS_DIR.exists(),
        "n_jobs": job_count,
        "statuses": dict(statuses),
    }


def write_figure(report: dict[str, Any]) -> None:
    checks = report["checks"]
    names = [item["name"].replace("_", "\n") for item in checks]
    values = [1 if item["status"] == "pass" else 0 for item in checks]
    colors = ["#2E8B57" if value else "#B85750" for value in values]
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.8), gridspec_kw={"width_ratios": [1.25, 1.0]})

    ax = axes[0]
    ax.bar(names, values, color=colors)
    ax.set_ylim(0, 1.15)
    ax.set_ylabel("pass/fail")
    ax.set_title("Phase 2A smoke checks")
    ax.tick_params(axis="x", rotation=35, labelsize=8)
    ax.grid(axis="y", alpha=0.25)
    for i, item in enumerate(checks):
        ax.text(i, 0.5, item["status"].upper(), ha="center", va="center", rotation=90, color="white", weight="bold")

    ax = axes[1]
    perf = report["benchmark"]["performance_reference"]
    selected = report["benchmark"]["selection"]
    labels = ["slots", "cores/slot", "expected\nlabels", "repo free\nGB"]
    data = [
        perf.get("slots", 0),
        perf.get("cores_per_slot", 0),
        selected.get("expected_dft_labels", 0),
        report["benchmark"]["storage"].get("repo_free_gb", 0),
    ]
    ax.bar(labels, data, color=["#2F6F73", "#2F6F73", "#C58B19", "#8A8F98"])
    ax.set_title("Startup benchmark summary")
    ax.grid(axis="y", alpha=0.25)
    for patch, value in zip(ax.patches, data):
        ax.text(patch.get_x() + patch.get_width() / 2, patch.get_height(), f"{value:g}", ha="center", va="bottom")

    fig.suptitle("Fase 2A DFT E+F(+stress) startup gate", fontsize=14, weight="bold")
    for ext in ("png", "pdf"):
        fig.savefig(f"{OUT_FIG}.{ext}", dpi=180, bbox_inches="tight")
    plt.close(fig)


def write_markdown(report: dict[str, Any]) -> None:
    gate = report["startup_gate"]
    checks_rows = "\n".join(
        f"| `{item['name']}` | `{item['status']}` | {item['elapsed_s']:.3f} | {item.get('error') or ''} |"
        for item in report["checks"]
    )
    perf = report["benchmark"]["performance_reference"]
    storage = report["benchmark"]["storage"]
    selection = report["benchmark"]["selection"]
    run_state = report["benchmark"]["official_run_state"]
    text = f"""# Phase 2A Smoke Benchmark

Generated: `{report['generated_at']}`

Startup gate: **{gate['status'].upper()}**

Reason: {gate['reason']}

## Checks

| Check | Status | Seconds | Error |
|------|--------|---------|-------|
{checks_rows}

## Method Coverage

- Non-Sn path: `r2scan`.
- Sn path: `U2p00`, `U2p25`, `U2p50`, `U2p75` sequential inside one logical job.
- Logical jobs in smoke benchmark: `{report['benchmark']['prepare_smoke'].get('n_benchmark_jobs', 'n/a')}`.
- Smoke runs dir: `{report['benchmark']['prepare_smoke'].get('smoke_runs_dir', 'n/a')}`.

## Scheduling Benchmark

- Recommended split from previous benchmark: `{perf.get('recommended_split', 'n/a')}`.
- Slots: `{perf.get('slots', 'n/a')}`.
- Cores/slot: `{perf.get('cores_per_slot', 'n/a')}`.
- Total MPI cores: `{perf.get('total_cores', 'n/a')}`.
- Reference throughput: `{perf.get('throughput_iter_s', 'n/a')}` iter/s.
- Reference peak RAM: `{perf.get('peak_ram_gb', 'n/a')}` GB.
- Source: `{perf.get('source', 'n/a')}`.

## Phase 2A Workload

- Candidates: `{selection.get('n_candidates', 'n/a')}`.
- Batches: `{selection.get('n_batches', 'n/a')}`.
- Expected DFT labels: `{selection.get('expected_dft_labels', 'n/a')}`.
- Sn per batch min/max: `{selection.get('sn_per_batch_min', 'n/a')}` / `{selection.get('sn_per_batch_max', 'n/a')}`.

## Storage And Active Runner Gate

- Default runs dir: `{storage.get('default_runs_dir', 'n/a')}`.
- Repo free: `{storage.get('repo_free_gb', 'n/a')}` GB.
- External volume: `{storage.get('external_volume', 'n/a')}`.
- External mounted: `{storage.get('external_mounted', 'n/a')}`.
- Require external: `{storage.get('require_external', 'n/a')}`.
- Official runs dir exists: `{run_state.get('exists')}`.
- Official jobs visible: `{run_state.get('n_jobs')}`.
- Official statuses: `{run_state.get('statuses')}`.

## Artifacts

- JSON: [`phase2_force_smoke_benchmark.json`](phase2_force_smoke_benchmark.json)
- PNG: [`phase2_force_smoke_benchmark.png`](phase2_force_smoke_benchmark.png)
- PDF: [`phase2_force_smoke_benchmark.pdf`](phase2_force_smoke_benchmark.pdf)
"""
    OUT_MD.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke + benchmark gate for Fase 2A.")
    parser.add_argument("--allow-repo-storage", action="store_true",
                        help="Do not fail startup gate when the external volume is not mounted.")
    parser.add_argument("--limit", type=int, default=DEFAULT_SMOKE_JOBS,
                        help="Number of logical jobs to prepare in the smoke benchmark.")
    args = parser.parse_args()

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    require_external = not args.allow_repo_storage

    checks: list[dict[str, Any]] = []
    checks.append(run_check("py_compile", check_py_compile))
    checks.append(run_check("direct_tests", check_direct_tests))
    checks.append(run_check("gpaw_env", check_gpaw_env))
    checks.append(run_check("selection", check_selection))
    checks.append(run_check("method_plan", check_method_plan))
    checks.append(run_check("prepare_and_runner_dry_run", lambda: check_prepare_smoke(args.limit)))
    checks.append(run_check("active_processes", check_active_processes))
    checks.append(run_check("storage", lambda: check_storage(require_external=require_external)))

    by_name = {item["name"]: item for item in checks}
    storage_data = by_name.get("storage", {})
    selection_data = by_name.get("selection", {})
    prepare_data = by_name.get("prepare_and_runner_dry_run", {})
    failures = [item for item in checks if item["status"] != "pass"]
    gate_status = "pass" if not failures else "fail"
    if failures:
        reason = "; ".join(f"{item['name']}: {item.get('error')}" for item in failures)
    else:
        reason = "All smokes passed; it is safe to start the runner with the configured storage policy."

    report = {
        "generated_at": utc_now(),
        "startup_gate": {"status": gate_status, "reason": reason},
        "checks": checks,
        "benchmark": {
            "performance_reference": load_performance_reference(),
            "selection": selection_data,
            "prepare_smoke": prepare_data,
            "storage": storage_data,
            "official_run_state": official_run_state(),
        },
        "next_dry_run_command_if_pass": (
            "PYTHONPATH=src python3 scripts/phase2_force_runner.py --batch-id 0 "
            "--slots 5 --cores 8 --dry-run"
        ),
        "real_run_requires_explicit_command": (
            "PYTHONPATH=src python3 scripts/phase2_force_runner.py --batch-id 0 "
            "--slots 5 --cores 8 --resume --start-real"
        ),
    }
    OUT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_figure(report)
    write_markdown(report)
    print(json.dumps(report["startup_gate"], indent=2, ensure_ascii=False))
    print(f"Report: {rel(OUT_JSON)}")
    print(f"Report: {rel(OUT_MD)}")
    raise SystemExit(0 if gate_status == "pass" else 1)


if __name__ == "__main__":
    main()
