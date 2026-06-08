#!/usr/bin/env python3
"""Benchmark seguro de concurrencia para Fase 2A DFT E+F.

Este script no usa ni modifica el runner productivo. Copia una estructura pesada
representativa a un directorio temporal y ejecuta splits de concurrencia con un
watchdog embebido para evitar overflow a swap.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import signal
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from string import Template
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from buho.phase2_force.common import OUT_DIR, REPORT_DIR, RUNS_DIR, display_path, read_csv


CONDA = str(Path.home() / "miniforge3" / "bin" / "conda")
GPAW_ENV = "gpaw246"
GPAW_SETUP_PATH = str(ROOT / ".venv" / "lib" / "python3.12" / "site-packages" / "gpaw_data" / "setups")
BENCH_ROOT = RUNS_DIR.parent / "_phase2_force_benchmark"

RAM_LIMIT_GB = 60.0
MIN_AVAIL_GB = 4.0
SWAP_LIMIT_GB = 10.0
DEFAULT_MAXITER = 2
DEFAULT_TIMEOUT_S = 1800
CONVERGENCE_ITER_ESTIMATE = 15

REPORT_STEM = "phase2_force_benchmark"
CSV_PATH = REPORT_DIR / f"{REPORT_STEM}.csv"
JSON_PATH = REPORT_DIR / f"{REPORT_STEM}.json"
MD_PATH = REPORT_DIR / f"{REPORT_STEM}.md"
DASHBOARD_STEM = REPORT_DIR / f"{REPORT_STEM}_dashboard"


MATRIX: list[dict[str, Any]] = [
    # Matriz vieja fisica.
    {"mode": "physical", "split": "1x44", "slots": 1, "cores": 44},
    {"mode": "physical", "split": "2x22", "slots": 2, "cores": 22},
    {"mode": "physical", "split": "3x14", "slots": 3, "cores": 14},
    {"mode": "physical", "split": "4x11", "slots": 4, "cores": 11},
    {"mode": "physical", "split": "5x8", "slots": 5, "cores": 8},
    {"mode": "physical", "split": "8x5", "slots": 8, "cores": 5},
    {"mode": "physical", "split": "11x4", "slots": 11, "cores": 4},
    {"mode": "physical", "split": "22x2", "slots": 22, "cores": 2},
    {"mode": "physical", "split": "44x1", "slots": 44, "cores": 1},
    # Agregados especificos de Fase 2A.
    {"mode": "phase2_8core", "split": "1x8", "slots": 1, "cores": 8},
    {"mode": "phase2_8core", "split": "2x8", "slots": 2, "cores": 8},
    {"mode": "phase2_8core", "split": "3x8", "slots": 3, "cores": 8},
    {"mode": "phase2_8core", "split": "4x8", "slots": 4, "cores": 8},
    # Agregado solicitado.
    {"mode": "added_1core", "split": "22x1", "slots": 22, "cores": 1},
    # HT / extendida.
    {"mode": "ht", "split": "2x44", "slots": 2, "cores": 44},
    {"mode": "ht", "split": "4x22", "slots": 4, "cores": 22},
    {"mode": "ht", "split": "8x11", "slots": 8, "cores": 11},
    {"mode": "ht", "split": "11x8", "slots": 11, "cores": 8},
    {"mode": "ht", "split": "22x4", "slots": 22, "cores": 4},
    {"mode": "ht", "split": "44x2", "slots": 44, "cores": 2},
    {"mode": "ht", "split": "88x1", "slots": 88, "cores": 1},
]


CSV_FIELDS = [
    "mode",
    "split",
    "slots",
    "cores_per_slot",
    "total_cores",
    "status",
    "reason",
    "jobs_launched",
    "jobs_ok",
    "maxiter",
    "avg_t_iter_s",
    "throughput_iter_s",
    "wall_s",
    "peak_split_rss_gb",
    "peak_ram_used_gb",
    "peak_swap_gb",
    "min_mem_available_gb",
    "candidate_id",
    "formula",
    "method",
    "u_ev",
    "occupation_mode",
    "parallel",
    "benchmark_dir",
]


INPUT_TEMPLATE = Template(
    r'''#!/usr/bin/env python3
from __future__ import annotations

import json
import time
import traceback
from pathlib import Path

from ase.io import read
from gpaw import GPAW, PW
from gpaw.eigensolvers import Davidson
from gpaw.mixer import Mixer
from gpaw.mpi import world


ROOT = Path(__file__).resolve().parent
MAXITER = $maxiter
PARALLEL = $parallel_json
U_EV = $u_ev_json
FORMULA = $formula_json
CANDIDATE_ID = $candidate_id_json
OCCUPATION_MODE = $occupation_mode_json


def write_result(data):
    if world.rank == 0:
        (ROOT / "bench_result.json").write_text(json.dumps(data, indent=2))


t0 = time.time()
atoms = read("structure.cif")
has_sn = U_EV is not None
setups = {"Sn": f":s,{U_EV}"} if has_sn else {}
if OCCUPATION_MODE == "fixed-uniform":
    occupations = {"name": "fixed-uniform"}
else:
    occupations = {"name": "fermi-dirac", "width": 0.2 if has_sn else 0.05}
calc = GPAW(
    mode=PW(450),
    xc="MGGA_X_R2SCAN+MGGA_C_R2SCAN",
    kpts={"size": [2, 2, 2], "gamma": True},
    occupations=occupations,
    eigensolver=Davidson(niter=3),
    parallel=PARALLEL,
    convergence={"density": 1e-4, "eigenstates": 1e-6, "energy": 1e-5},
    mixer=Mixer(0.002, 15, 100) if has_sn else Mixer(0.05, 8, 50),
    maxiter=MAXITER,
    setups=setups,
    txt="r2scan.txt",
)
atoms.calc = calc
try:
    energy = float(atoms.get_potential_energy())
    write_result({
        "status": "converged",
        "energy_eV": energy,
        "elapsed_s": round(time.time() - t0, 1),
        "candidate_id": CANDIDATE_ID,
        "formula": FORMULA,
        "u_ev": U_EV,
        "occupation_mode": OCCUPATION_MODE,
        "parallel": PARALLEL,
    })
except Exception as exc:
    # Para benchmark, no converger en MAXITER=2 es esperado. El proceso debe
    # terminar limpio para que el parser mida iteraciones y memoria.
    write_result({
        "status": "exception",
        "error": repr(exc),
        "traceback": traceback.format_exc()[-3000:],
        "elapsed_s": round(time.time() - t0, 1),
        "candidate_id": CANDIDATE_ID,
        "formula": FORMULA,
        "u_ev": U_EV,
        "occupation_mode": OCCUPATION_MODE,
        "parallel": PARALLEL,
    })
'''
)


@dataclass
class MemSample:
    used_gb: float
    available_gb: float
    swap_gb: float
    split_rss_gb: float


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_split(text: str) -> tuple[int, int]:
    left, right = text.lower().split("x", 1)
    return int(left), int(right)


def matrix_by_name() -> dict[str, dict[str, Any]]:
    return {row["split"]: row for row in MATRIX}


def selected_matrix(selection: str) -> list[dict[str, Any]]:
    if selection == "all":
        return [dict(row) for row in MATRIX]
    known = matrix_by_name()
    rows = []
    for item in selection.split(","):
        split = item.strip()
        if not split:
            continue
        if split in known:
            rows.append(dict(known[split]))
            continue
        slots, cores = parse_split(split)
        rows.append({"mode": "custom", "split": f"{slots}x{cores}", "slots": slots, "cores": cores})
    return rows


def parallel_layout(cores: int, nkpts: int = 4) -> dict[str, int]:
    for kpt in range(min(cores, nkpts), 0, -1):
        if cores % kpt == 0 and nkpts % kpt == 0:
            return {"kpt": kpt, "domain": max(1, cores // kpt), "band": 1}
    return {"kpt": 1, "domain": max(1, cores), "band": 1}


def meminfo() -> tuple[float, float, float]:
    info = Path("/proc/meminfo").read_text()
    total = int(re.search(r"MemTotal:\s+(\d+)", info).group(1))
    avail = int(re.search(r"MemAvailable:\s+(\d+)", info).group(1))
    swap_total = int(re.search(r"SwapTotal:\s+(\d+)", info).group(1))
    swap_free = int(re.search(r"SwapFree:\s+(\d+)", info).group(1))
    used_gb = (total - avail) / 1024 / 1024
    avail_gb = avail / 1024 / 1024
    swap_gb = (swap_total - swap_free) / 1024 / 1024
    return used_gb, avail_gb, swap_gb


def process_status(pid: int) -> dict[str, Any]:
    status_path = Path(f"/proc/{pid}/status")
    out: dict[str, Any] = {}
    try:
        for line in status_path.read_text(errors="replace").splitlines():
            if line.startswith("VmRSS:"):
                out["rss_kb"] = int(line.split()[1])
            elif line.startswith("State:"):
                out["state"] = line.split(":", 1)[1].strip()
    except Exception:
        pass
    return out


def processes_under(path: Path) -> list[int]:
    root = str(path.resolve())
    pids: list[int] = []
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        pid = int(proc.name)
        try:
            cwd = os.readlink(proc / "cwd")
        except Exception:
            continue
        if cwd == root or cwd.startswith(root + os.sep):
            pids.append(pid)
    return pids


def split_rss_gb(path: Path) -> float:
    rss_kb = 0
    for pid in processes_under(path):
        rss_kb += int(process_status(pid).get("rss_kb", 0))
    return rss_kb / 1024 / 1024


def sample_memory(split_dir: Path) -> MemSample:
    used, avail, swap = meminfo()
    return MemSample(used_gb=used, available_gb=avail, swap_gb=swap, split_rss_gb=split_rss_gb(split_dir))


def watchdog_reason(sample: MemSample, ram_limit: float, min_avail: float, swap_limit: float) -> str | None:
    if sample.used_gb >= ram_limit:
        return f"ram_used_gb={sample.used_gb:.2f} >= {ram_limit:.2f}"
    if sample.available_gb < min_avail:
        return f"mem_available_gb={sample.available_gb:.2f} < {min_avail:.2f}"
    if sample.swap_gb > swap_limit:
        return f"swap_gb={sample.swap_gb:.2f} > {swap_limit:.2f}"
    return None


def active_dft_processes() -> list[str]:
    pattern = r"[p]hase2_force_runner|[m]piexec|[m]pirun|[c]onda run|[i]nput.py"
    proc = subprocess.run(["pgrep", "-af", pattern], capture_output=True, text=True)
    return [line for line in proc.stdout.splitlines() if line.strip()]


def wait_memory_safe(ram_limit: float, min_avail: float, swap_limit: float, timeout_s: int = 600) -> bool:
    start = time.time()
    while time.time() - start < timeout_s:
        used, avail, swap = meminfo()
        if used < ram_limit and avail >= min_avail and swap <= swap_limit:
            return True
        time.sleep(5)
    return False


def kill_split(split_dir: Path, procs: list[subprocess.Popen], log) -> None:
    pids = set(processes_under(split_dir))
    for proc in procs:
        if proc.poll() is None:
            pids.add(proc.pid)

    pgids: set[int] = set()
    for pid in pids:
        try:
            pgids.add(os.getpgid(pid))
        except ProcessLookupError:
            pass

    for pgid in sorted(pgids):
        try:
            os.killpg(pgid, signal.SIGTERM)
            log(f"SIGTERM pgid={pgid}")
        except ProcessLookupError:
            pass
    for pid in sorted(pids):
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    time.sleep(3)
    for pgid in sorted(pgids):
        try:
            os.killpg(pgid, signal.SIGKILL)
            log(f"SIGKILL pgid={pgid}")
        except ProcessLookupError:
            pass
    for pid in sorted(pids):
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def parse_r2scan(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"iters": 0, "t_iter_s": None}
    text = path.read_text(errors="replace")
    its = re.findall(r"iter:\s*(\d+)\s*\|?\s*(\d{1,2}):(\d{2}):(\d{2})", text)
    t_iter = None
    if len(its) >= 2:
        times = [int(h) * 3600 + int(m) * 60 + int(s) for _, h, m, s in its]
        deltas = [(times[i] - times[i - 1]) % 86400 for i in range(1, len(times))]
        if deltas:
            t_iter = round(sum(deltas) / len(deltas), 2)

    def grab_float(pattern: str) -> float | None:
        m = re.search(pattern, text)
        return float(m.group(1)) if m else None

    coeffs = re.search(r"Number of coefficients \(min, max\):\s+([0-9]+),\s+([0-9]+)", text)
    kpts = re.search(r"([0-9]+) k-points:", text)
    return {
        "iters": len(its),
        "t_iter_s": t_iter,
        "process_memory_mib": grab_float(r"Process memory now:\s+([0-9.]+) MiB"),
        "calculator_mib": grab_float(r"Calculator:\s+([0-9.]+) MiB"),
        "wavefunctions_mib": grab_float(r"Wavefunctions:\s+([0-9.]+) MiB"),
        "density_mib": grab_float(r"Density:\s+([0-9.]+) MiB"),
        "bands": grab_float(r"Number of bands in calculation:\s+([0-9.]+)"),
        "atoms": grab_float(r"Number of atoms:\s+([0-9.]+)"),
        "coeff_min": int(coeffs.group(1)) if coeffs else None,
        "coeff_max": int(coeffs.group(2)) if coeffs else None,
        "kpoints": int(kpts.group(1)) if kpts else None,
    }


def split_reached_iterations(split_dir: Path, slots: int, maxiter: int) -> bool:
    for idx in range(slots):
        parsed = parse_r2scan(split_dir / f"slot_{idx:03d}" / "r2scan.txt")
        if int(parsed.get("iters") or 0) < maxiter:
            return False
    return True


def slot_results(split_dir: Path, slots: int) -> list[dict[str, Any]] | None:
    results: list[dict[str, Any]] = []
    for idx in range(slots):
        path = split_dir / f"slot_{idx:03d}" / "bench_result.json"
        if not path.exists():
            return None
        try:
            results.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception as exc:
            results.append({"status": "exception", "error": f"invalid_result_json: {exc!r}"})
    return results


def choose_candidate(candidate_id: str | None, batch_id: int) -> dict[str, str]:
    batch_csv = OUT_DIR / "batches" / f"batch_{batch_id:03d}.csv"
    rows = read_csv(batch_csv)
    if candidate_id:
        for row in rows:
            if row["candidate_id"] == candidate_id:
                return row
        raise SystemExit(f"No encontre candidate_id={candidate_id} en {batch_csv}")
    for row in rows:
        if row.get("contains_sn", "").lower() == "true":
            return row
    raise SystemExit(f"No encontre candidato Sn en {batch_csv}")


def source_structure(candidate: dict[str, str], batch_id: int) -> Path:
    path = RUNS_DIR / f"batch_{batch_id:03d}" / candidate["candidate_id"] / "structure.cif"
    if path.exists():
        return path
    raise SystemExit(f"Falta structure.cif preparado para benchmark: {path}")


def write_bench_input(job_dir: Path, candidate: dict[str, str], parallel: dict[str, int], maxiter: int) -> None:
    script = INPUT_TEMPLATE.substitute(
        maxiter=int(maxiter),
        parallel_json=json.dumps(parallel),
        u_ev_json=json.dumps(2.0),
        formula_json=json.dumps(candidate["formula"]),
        candidate_id_json=json.dumps(candidate["candidate_id"]),
        occupation_mode_json=json.dumps("fixed-uniform"),
    )
    path = job_dir / "input.py"
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)


def prepare_split_dir(run_dir: Path, row: dict[str, Any], candidate: dict[str, str],
                      structure_path: Path, maxiter: int) -> Path:
    split_dir = run_dir / row["split"]
    shutil.rmtree(split_dir, ignore_errors=True)
    split_dir.mkdir(parents=True, exist_ok=True)
    parallel = parallel_layout(int(row["cores"]))
    for idx in range(int(row["slots"])):
        job = split_dir / f"slot_{idx:03d}"
        job.mkdir(parents=True, exist_ok=True)
        shutil.copy2(structure_path, job / "structure.cif")
        (job / "metadata.json").write_text(json.dumps({
            "benchmark": "phase2_force",
            "split": row["split"],
            "slot": idx,
            "candidate_id": candidate["candidate_id"],
            "formula": candidate["formula"],
            "method": "r2SCAN+U",
            "u_ev": 2.0,
            "occupation_mode": "fixed-uniform",
            "maxiter": maxiter,
            "parallel": parallel,
        }, indent=2) + "\n", encoding="utf-8")
        write_bench_input(job, candidate, parallel, maxiter)
    (split_dir / "split_metadata.json").write_text(json.dumps({
        **row,
        "candidate_id": candidate["candidate_id"],
        "formula": candidate["formula"],
        "method": "r2SCAN+U",
        "u_ev": 2.0,
        "occupation_mode": "fixed-uniform",
        "maxiter": maxiter,
        "parallel": parallel,
    }, indent=2) + "\n", encoding="utf-8")
    return split_dir


def popen_job(job_dir: Path, cores: int) -> subprocess.Popen:
    env = os.environ.copy()
    env["OMP_NUM_THREADS"] = "1"
    env["OPENBLAS_NUM_THREADS"] = "1"
    env["MKL_NUM_THREADS"] = "1"
    cmd = [
        CONDA,
        "run",
        "-n",
        GPAW_ENV,
        "bash",
        "-c",
        f"export GPAW_SETUP_PATH={GPAW_SETUP_PATH}; exec mpiexec -n {cores} python input.py",
    ]
    log = open(job_dir / "run.log", "w")
    return subprocess.Popen(cmd, cwd=str(job_dir), env=env, stdout=log, stderr=log, preexec_fn=os.setsid)


def run_split(run_dir: Path, row: dict[str, Any], candidate: dict[str, str], structure_path: Path,
              args: argparse.Namespace, log) -> dict[str, Any]:
    split_dir = prepare_split_dir(run_dir, row, candidate, structure_path, args.maxiter)
    parallel = parallel_layout(int(row["cores"]))
    base = {
        "mode": row["mode"],
        "split": row["split"],
        "slots": int(row["slots"]),
        "cores_per_slot": int(row["cores"]),
        "total_cores": int(row["slots"]) * int(row["cores"]),
        "maxiter": args.maxiter,
        "candidate_id": candidate["candidate_id"],
        "formula": candidate["formula"],
        "method": "r2SCAN+U",
        "u_ev": 2.0,
        "occupation_mode": "fixed-uniform",
        "parallel": json.dumps(parallel, sort_keys=True),
        "benchmark_dir": display_path(split_dir),
    }
    if args.dry_run:
        return {
            **base,
            "status": "planned",
            "reason": "dry_run",
            "jobs_launched": 0,
            "jobs_ok": 0,
            "avg_t_iter_s": None,
            "throughput_iter_s": 0.0,
            "wall_s": 0.0,
            "peak_split_rss_gb": 0.0,
            "peak_ram_used_gb": 0.0,
            "peak_swap_gb": 0.0,
            "min_mem_available_gb": None,
        }

    if not wait_memory_safe(args.ram_limit_gb, args.min_available_gb, args.swap_limit_gb):
        return {
            **base,
            "status": "skipped_preflight",
            "reason": "memory_not_safe_before_split",
            "jobs_launched": 0,
            "jobs_ok": 0,
            "avg_t_iter_s": None,
            "throughput_iter_s": 0.0,
            "wall_s": 0.0,
            "peak_split_rss_gb": 0.0,
            "peak_ram_used_gb": meminfo()[0],
            "peak_swap_gb": meminfo()[2],
            "min_mem_available_gb": meminfo()[1],
        }

    log(f"START split={row['split']} slots={row['slots']} cores={row['cores']} parallel={parallel}")
    t0 = time.time()
    procs = [popen_job(split_dir / f"slot_{idx:03d}", int(row["cores"])) for idx in range(int(row["slots"]))]
    status = "ok"
    reason = ""
    peak_split_rss = 0.0
    peak_used = 0.0
    peak_swap = 0.0
    min_avail = 10**9

    while True:
        sample = sample_memory(split_dir)
        peak_split_rss = max(peak_split_rss, sample.split_rss_gb)
        peak_used = max(peak_used, sample.used_gb)
        peak_swap = max(peak_swap, sample.swap_gb)
        min_avail = min(min_avail, sample.available_gb)
        reason = watchdog_reason(sample, args.ram_limit_gb, args.min_available_gb, args.swap_limit_gb) or ""
        if reason:
            status = "aborted_by_watchdog"
            log(f"WATCHDOG split={row['split']} {reason}")
            kill_split(split_dir, procs, log)
            break
        if split_reached_iterations(split_dir, int(row["slots"]), args.maxiter):
            status = "ok"
            reason = "maxiter_reached_split_stopped"
            log(f"MAXITER split={row['split']} reached {args.maxiter} iterations; stopping split")
            kill_split(split_dir, procs, log)
            break
        results = slot_results(split_dir, int(row["slots"]))
        if results is not None:
            bad = [item for item in results if item.get("status") != "converged"]
            if bad:
                status = "failed"
                reason = f"slot_result_{bad[0].get('status', 'unknown')}"
            else:
                status = "ok"
                reason = "slot_results_written"
            log(f"RESULTS split={row['split']} status={status}; stopping split")
            kill_split(split_dir, procs, log)
            break
        if all(proc.poll() is not None for proc in procs):
            break
        if time.time() - t0 > args.timeout_s:
            status = "failed"
            reason = f"timeout_s={args.timeout_s}"
            log(f"TIMEOUT split={row['split']} timeout={args.timeout_s}s")
            kill_split(split_dir, procs, log)
            break
        time.sleep(args.poll)

    for proc in procs:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
    wall = round(time.time() - t0, 1)

    tpis: list[float] = []
    parsed = []
    for idx in range(int(row["slots"])):
        job = split_dir / f"slot_{idx:03d}"
        parsed_item = parse_r2scan(job / "r2scan.txt")
        parsed_item["slot"] = idx
        parsed.append(parsed_item)
        if parsed_item["iters"] >= args.maxiter and parsed_item["t_iter_s"]:
            tpis.append(float(parsed_item["t_iter_s"]))

    jobs_ok = len(tpis)
    if status == "ok" and jobs_ok == 0:
        status = "failed"
        reason = "no_job_reached_required_iterations"

    avg_t_iter = round(sum(tpis) / len(tpis), 2) if tpis else None
    throughput = round(sum(1.0 / value for value in tpis), 5) if tpis else 0.0
    (split_dir / "parsed_metrics.json").write_text(json.dumps(parsed, indent=2) + "\n", encoding="utf-8")
    result = {
        **base,
        "status": status,
        "reason": reason,
        "jobs_launched": int(row["slots"]),
        "jobs_ok": jobs_ok,
        "avg_t_iter_s": avg_t_iter,
        "throughput_iter_s": throughput,
        "wall_s": wall,
        "peak_split_rss_gb": round(peak_split_rss, 2),
        "peak_ram_used_gb": round(peak_used, 2),
        "peak_swap_gb": round(peak_swap, 3),
        "min_mem_available_gb": round(min_avail, 2) if min_avail < 10**8 else None,
    }
    log(f"DONE split={row['split']} status={status} throughput={throughput} ram={result['peak_ram_used_gb']} swap={result['peak_swap_gb']}")
    return result


def best_ok(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    valid = [row for row in rows if row.get("status") == "ok" and float(row.get("throughput_iter_s") or 0) > 0]
    if not valid:
        return None
    return max(valid, key=lambda row: float(row["throughput_iter_s"]))


def best_ok_8core(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    valid = [
        row
        for row in rows
        if row.get("status") == "ok"
        and int(row.get("cores_per_slot") or 0) == 8
        and float(row.get("throughput_iter_s") or 0) > 0
    ]
    if not valid:
        return None
    return max(valid, key=lambda row: float(row["throughput_iter_s"]))


def rows_for_dashboard(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("status") == "ok"]


def benchmark_time_h(
    row: dict[str, Any],
    metadata: dict[str, Any],
    n_candidates: int = 50,
    n_iter: int | None = None,
) -> float | None:
    throughput = float(row.get("throughput_iter_s") or 0)
    if throughput <= 0:
        return None
    maxiter = int(n_iter if n_iter is not None else (metadata.get("maxiter") or DEFAULT_MAXITER))
    return (n_candidates * maxiter) / throughput / 3600


def phase2_batch_label_count(batch_id: int = 0, default: int = 143) -> int:
    path = ROOT / "data" / "mace_finetune" / "phase2_batches.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        for row in data.get("batches", []):
            if int(row.get("batch_id", -1)) == batch_id:
                return int(row.get("n_expected_dft_labels") or default)
    except Exception:
        pass
    return default


def write_csv_report(rows: list[dict[str, Any]]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    with CSV_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json_report(rows: list[dict[str, Any]], metadata: dict[str, Any]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps({"metadata": metadata, "rows": rows}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_markdown_report(rows: list[dict[str, Any]], metadata: dict[str, Any]) -> None:
    best = best_ok(rows)
    best_8core = best_ok_8core(rows)
    n_ok = sum(1 for row in rows if row.get("status") == "ok")
    n_aborted = sum(1 for row in rows if row.get("status") == "aborted_by_watchdog")
    n_failed = sum(1 for row in rows if row.get("status") == "failed")
    n_skipped = sum(1 for row in rows if row.get("status") == "skipped")
    eliminated = [row for row in rows if row.get("status") != "ok"]
    lines = [
        "# Benchmark Fase 2A DFT E+F",
        "",
        f"Generado: `{metadata['generated_at']}`",
        "",
        "## Resumen Ejecutivo",
        "",
    ]
    if best:
        best_time_h = benchmark_time_h(best, metadata, n_iter=CONVERGENCE_ITER_ESTIMATE)
        batch0_labels = phase2_batch_label_count(0)
        best_batch0_h = benchmark_time_h(
            best,
            metadata,
            n_candidates=batch0_labels,
            n_iter=CONVERGENCE_ITER_ESTIMATE,
        )
        lines.extend([
            f"- Split recomendado: **{best['split']}** = **{best['slots']} slots x {best['cores_per_slot']} cores**.",
            f"- Throughput agregado: **{float(best['throughput_iter_s']):.5f} iter/s**.",
            f"- t/iter promedio: **{float(best['avg_t_iter_s']):.2f} s**.",
            f"- Tiempo aproximado para 50 labels a `{CONVERGENCE_ITER_ESTIMATE}` iter: "
            f"**{best_time_h:.2f} h**." if best_time_h is not None else
            f"- Tiempo aproximado para 50 labels a `{CONVERGENCE_ITER_ESTIMATE}` iter: **n/d**.",
            f"- Tiempo aproximado para batch 0 completo (`{batch0_labels}` labels) a `{CONVERGENCE_ITER_ESTIMATE}` iter: "
            f"**{best_batch0_h:.2f} h**." if best_batch0_h is not None else
            f"- Tiempo aproximado para batch 0 completo (`{batch0_labels}` labels) a `{CONVERGENCE_ITER_ESTIMATE}` iter: **n/d**.",
            f"- RAM pico: **{float(best['peak_ram_used_gb']):.2f} GiB**; swap pico: **{float(best['peak_swap_gb']):.3f} GiB**.",
            f"- Memoria minima disponible: **{float(best['min_mem_available_gb']):.2f} GiB**.",
        ])
    else:
        lines.append("- Split recomendado: **no disponible**; ningun split termino `ok` con iteraciones medibles.")
    if best_8core:
        lines.extend([
            f"- Recomendacion conservadora para produccion Fase 2A: **{best_8core['split']}** = "
            f"**{best_8core['slots']} slots x {best_8core['cores_per_slot']} cores**.",
            f"- Motivo: mantiene el contrato operativo de jobs de 8 cores y uso bajo de swap "
            f"(**{float(best_8core['peak_swap_gb']):.3f} GiB**) con "
            f"**{float(best_8core['min_mem_available_gb']):.2f} GiB** disponibles en el peor punto.",
        ])
    lines.extend([
        f"- Splits ok: `{n_ok}`; abortados por watchdog: `{n_aborted}`; fallidos: `{n_failed}`; omitidos: `{n_skipped}`.",
        f"- Watchdog: RAM usada >= `{metadata['ram_limit_gb']} GiB`, swap > `{metadata['swap_limit_gb']} GiB`, memoria disponible < `{metadata['min_available_gb']} GiB`.",
        "- Las infografias del dashboard excluyen splits eliminados; solo grafican configuraciones `ok`.",
        "",
        "## Conclusion Operativa",
        "",
    ])
    if best_8core:
        lines.extend([
            f"- Usar **{best_8core['split']}** como configuracion inicial de produccion para Fase 2A.",
            "- No relanzar el benchmark completo desde VSCode; si se necesita otro barrido, correrlo fuera de la sesion grafica.",
        ])
    if best and (not best_8core or best["split"] != best_8core["split"]):
        lines.append(
            f"- **{best['split']}** queda como techo de throughput medido, util para corridas manuales controladas "
            "si se acepta salir del esquema estricto de 8 cores por job."
        )
    lines.extend([
        "- No usar configuraciones con muchos jobs de 1-2 cores: duplican memoria, procesos y presion de swap sin mejorar estabilidad.",
        "",
        "## Tabla Maestra",
        "",
        "| split | mode | slots | cores/slot | status | jobs ok | t/iter s | throughput | RAM pico GiB | swap pico GiB | motivo |",
        "|---|---|---:|---:|---|---:|---:|---:|---:|---:|---|",
    ])
    for row in rows:
        lines.append(
            f"| `{row['split']}` | `{row['mode']}` | {row['slots']} | {row['cores_per_slot']} | `{row['status']}` | "
            f"{row['jobs_ok']} | {row.get('avg_t_iter_s') if row.get('avg_t_iter_s') is not None else ''} | "
            f"{row.get('throughput_iter_s', 0)} | {row.get('peak_ram_used_gb', '')} | {row.get('peak_swap_gb', '')} | "
            f"{row.get('reason', '')} |"
        )
    lines.extend([
        "",
        "## Splits Eliminados",
        "",
        "Estos splits no se incluyen en las infografias. Se conservan aqui solo como auditoria y para evitar relanzarlos.",
        "",
        "| split | status | motivo | RAM pico GiB | swap pico GiB | memoria minima disponible GiB |",
        "|---|---|---|---:|---:|---:|",
    ])
    for row in eliminated:
        lines.append(
            f"| `{row['split']}` | `{row.get('status', '')}` | {row.get('reason', '')} | "
            f"{row.get('peak_ram_used_gb', '')} | {row.get('peak_swap_gb', '')} | {row.get('min_mem_available_gb', '')} |"
        )
    lines.extend([
        "",
        "## Dashboard",
        "",
        "- [Dashboard PNG](phase2_force_benchmark_dashboard.png)",
        "- [Dashboard PDF](phase2_force_benchmark_dashboard.pdf)",
        "",
        "Nota: el dashboard muestra solo splits `ok`; los eliminados estan documentados en la seccion anterior.",
        "",
        "## Datos",
        "",
        "- [CSV](phase2_force_benchmark.csv)",
        "- [JSON](phase2_force_benchmark.json)",
        "",
        "## Nota",
        "",
        "Este benchmark decide concurrencia segura. No produce etiquetas MACE ni modifica estados oficiales de Fase 2A.",
        "",
    ])
    MD_PATH.write_text("\n".join(lines), encoding="utf-8")


def color_for(row: dict[str, Any], best_split: str | None = None) -> str:
    if best_split and row["split"] == best_split:
        return "#2E8B57"
    if row.get("status") == "ok":
        return "#2F6F73"
    if row.get("status") == "aborted_by_watchdog":
        return "#B85750"
    if row.get("status") == "skipped":
        return "#6F7785"
    if row.get("status") == "planned":
        return "#8A8F98"
    return "#C58B19"


def write_dashboard(rows: list[dict[str, Any]], metadata: dict[str, Any]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    rows = rows_for_dashboard(rows)
    best = best_ok(rows)
    best_8core = best_ok_8core(rows)
    best_split = best["split"] if best else None
    labels = [row["split"] for row in rows]
    colors = [color_for(row, best_split) for row in rows]
    throughput = [float(row.get("throughput_iter_s") or 0) for row in rows]
    ram = [float(row.get("peak_ram_used_gb") or 0) for row in rows]
    swap = [float(row.get("peak_swap_gb") or 0) for row in rows]
    time_h = [
        benchmark_time_h(row, metadata, n_iter=CONVERGENCE_ITER_ESTIMATE) or 0
        for row in rows
    ]
    batch0_labels = phase2_batch_label_count(0)
    batch0_time_h = [
        benchmark_time_h(
            row,
            metadata,
            n_candidates=batch0_labels,
            n_iter=CONVERGENCE_ITER_ESTIMATE,
        )
        or 0
        for row in rows
    ]

    fig, axes = plt.subplots(2, 2, figsize=(14, 9))

    ax = axes[0, 0]
    ax.bar(labels, throughput, color=colors)
    ax.set_title("Throughput Fase 2A")
    ax.set_ylabel("iter/s")
    ax.tick_params(axis="x", rotation=45, labelsize=8)
    ax.grid(axis="y", alpha=0.25)

    ax = axes[0, 1]
    best_time = min((value for value in time_h if value > 0), default=None)
    time_colors = ["#2E8B57" if best_time is not None and value == best_time else "#C58B19" for value in time_h]
    ax.bar(labels, time_h, color=time_colors)
    ax.set_title(f"Tiempo conv. aprox. ({CONVERGENCE_ITER_ESTIMATE} iter)")
    ax.set_ylabel("tiempo (h)")
    ax.tick_params(axis="x", rotation=45, labelsize=8)
    ax.grid(axis="y", alpha=0.25)
    for i, value in enumerate(time_h):
        ax.annotate(
            f"{value:.2f}",
            (i, value),
            ha="center",
            va="bottom",
            xytext=(0, 3),
            textcoords="offset points",
            fontsize=8,
        )

    ax = axes[1, 0]
    for row in rows:
        ax.scatter(
            float(row.get("peak_ram_used_gb") or 0),
            float(row.get("throughput_iter_s") or 0),
            s=80,
            color=color_for(row, best_split),
            marker="x" if row.get("status") == "aborted_by_watchdog" else "o",
        )
        ax.annotate(row["split"], (float(row.get("peak_ram_used_gb") or 0), float(row.get("throughput_iter_s") or 0)),
                    xytext=(5, 3), textcoords="offset points", fontsize=8)
    ax.axvline(float(metadata["ram_limit_gb"]), color="#B85750", ls="--", lw=1.4)
    ax.set_title("Tradeoff RAM vs throughput")
    ax.set_xlabel("RAM usada pico (GiB)")
    ax.set_ylabel("iter/s")
    ax.grid(alpha=0.25)

    ax = axes[1, 1]
    best_batch0_time = min((value for value in batch0_time_h if value > 0), default=None)
    batch0_colors = [
        "#2E8B57" if best_batch0_time is not None and value == best_batch0_time else "#C58B19"
        for value in batch0_time_h
    ]
    ax.bar(labels, batch0_time_h, color=batch0_colors)
    ax.set_title(f"ETA {batch0_labels} labels ({CONVERGENCE_ITER_ESTIMATE} iter)")
    ax.set_ylabel("ETA (h)")
    ax.tick_params(axis="x", rotation=45, labelsize=8)
    ax.grid(axis="y", alpha=0.25)
    for i, value in enumerate(batch0_time_h):
        ax.annotate(
            f"{value:.1f}",
            (i, value),
            ha="center",
            va="bottom",
            xytext=(0, 3),
            textcoords="offset points",
            fontsize=8,
        )

    fig.suptitle("Benchmark Fase 2A - Concurrencia segura DFT E+F", fontsize=16, y=0.995)
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(f"{DASHBOARD_STEM}.{ext}", dpi=180, bbox_inches="tight")
    plt.close(fig)


def write_reports(rows: list[dict[str, Any]], metadata: dict[str, Any]) -> None:
    write_csv_report(rows)
    write_json_report(rows, metadata)
    write_markdown_report(rows, metadata)
    write_dashboard(rows, metadata)


def append_resume_safe(path: Path, line: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def run(args: argparse.Namespace) -> dict[str, Any]:
    rows = selected_matrix(args.splits)
    candidate = choose_candidate(args.candidate_id, args.batch_id)
    structure = source_structure(candidate, args.batch_id)
    resumed_rows: dict[str, dict[str, Any]] = {}
    if args.resume and JSON_PATH.exists():
        previous = json.loads(JSON_PATH.read_text(encoding="utf-8"))
        for previous_row in previous.get("rows", []):
            if previous_row.get("status") in {"ok", "aborted_by_watchdog", "skipped"} and previous_row.get("split"):
                resumed_rows[str(previous_row["split"])] = dict(previous_row)

    run_dir = args.bench_root / now_stamp()
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "watchdog.log"

    def log(message: str) -> None:
        line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}"
        print(line, flush=True)
        append_resume_safe(log_path, line)

    used, avail, swap = meminfo()
    if not args.dry_run:
        active = active_dft_processes()
        if active:
            raise SystemExit("Hay procesos DFT activos; no arranco benchmark:\n" + "\n".join(active[:20]))
        if swap > args.swap_limit_gb:
            raise SystemExit(f"Swap inicial {swap:.2f} GiB > {args.swap_limit_gb:.2f} GiB; limpia swap antes de correr benchmark real.")

    results: list[dict[str, Any]] = []
    metadata = {
        "generated_at": utc_now(),
        "dry_run": args.dry_run,
        "run_dir": display_path(run_dir),
        "candidate_id": candidate["candidate_id"],
        "formula": candidate["formula"],
        "source_structure": display_path(structure),
        "maxiter": args.maxiter,
        "occupation_mode": "fixed-uniform",
        "ram_limit_gb": args.ram_limit_gb,
        "min_available_gb": args.min_available_gb,
        "swap_limit_gb": args.swap_limit_gb,
        "initial_ram_used_gb": round(used, 2),
        "initial_mem_available_gb": round(avail, 2),
        "initial_swap_gb": round(swap, 3),
        "matrix": [row["split"] for row in rows],
        "resume": args.resume,
        "resumed_splits": sorted(resumed_rows),
    }
    (run_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    for row in rows:
        if row["split"] in resumed_rows:
            result = resumed_rows[row["split"]]
            results.append(result)
            log(f"RESUME skip split={row['split']} status={result.get('status')}")
            write_reports(results, metadata)
            continue
        result = run_split(run_dir, row, candidate, structure, args, log)
        results.append(result)
        write_reports(results, metadata)
    return {"metadata": metadata, "rows": results}


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark Fase 2A con watchdog anti-swap.")
    parser.add_argument("--splits", default="all", help='Lista coma-separada, e.g. "1x8,2x8,3x8"; default=all.')
    parser.add_argument("--batch-id", type=int, default=0)
    parser.add_argument("--candidate-id", default=None)
    parser.add_argument("--maxiter", type=int, default=DEFAULT_MAXITER)
    parser.add_argument("--poll", type=float, default=2.0)
    parser.add_argument("--timeout-s", type=int, default=DEFAULT_TIMEOUT_S)
    parser.add_argument("--ram-limit-gb", type=float, default=RAM_LIMIT_GB)
    parser.add_argument("--min-available-gb", type=float, default=MIN_AVAIL_GB)
    parser.add_argument("--swap-limit-gb", type=float, default=SWAP_LIMIT_GB)
    parser.add_argument("--bench-root", type=Path, default=BENCH_ROOT)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true", help="Conserva splits ok del reporte existente y recalcula el resto.")
    args = parser.parse_args()
    result = run(args)
    print(json.dumps({
        "dry_run": args.dry_run,
        "n_splits": len(result["rows"]),
        "reports": {
            "csv": display_path(CSV_PATH),
            "json": display_path(JSON_PATH),
            "markdown": display_path(MD_PATH),
            "dashboard_png": display_path(Path(f"{DASHBOARD_STEM}.png")),
            "dashboard_pdf": display_path(Path(f"{DASHBOARD_STEM}.pdf")),
        },
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
