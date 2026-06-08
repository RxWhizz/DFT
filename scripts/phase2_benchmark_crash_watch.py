#!/usr/bin/env python3
"""Flight recorder externo para el benchmark Fase 2A.

El benchmark puede desaparecer junto con VSCode o con el compositor grafico.
Este wrapper queda fuera del runner productivo, lanza el benchmark y muestrea
estado del sistema/procesos para dejar evidencia posterior al crash.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports" / "training fase 2"
BENCH_SCRIPT = ROOT / "scripts" / "phase2_force_benchmark.py"
GPAW_PYTHON = Path.home() / "miniforge3" / "envs" / "gpaw246" / "bin" / "python3"
EXTERNAL_RUNS_ROOT = Path("/media/luis-ochoa/Nuevo vol/dft/runs")
PHASE2_FORCE_RUNS_DIR = EXTERNAL_RUNS_ROOT / "phase2_force"

DFT_PATTERN = r"[p]hase2_force_benchmark|[m]piexec|[m]pirun|[c]onda run|[i]nput.py"
UI_PATTERN = r"[c]ode|[g]nome-shell|[X]wayland|[m]utter|[c]rashpad|[p]ylance"
SUSPECT_JOURNAL = r"oom|killed process|out of memory|amdgpu|drm|gpu|ring|reset|segfault|gnome-shell|code|crash|xwayland|mutter"


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_cmd(cmd: list[str], timeout: int = 8) -> str:
    try:
        proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=timeout)
    except Exception as exc:
        return f"<command failed: {' '.join(cmd)}: {exc!r}>"
    out = (proc.stdout or "") + (proc.stderr or "")
    return out.strip()


def meminfo() -> dict[str, float]:
    text = Path("/proc/meminfo").read_text()
    values: dict[str, int] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].endswith(":"):
            values[parts[0][:-1]] = int(parts[1])
    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable", 0)
    swap_total = values.get("SwapTotal", 0)
    swap_free = values.get("SwapFree", 0)
    return {
        "ram_total_gb": total / 1024 / 1024,
        "ram_used_gb": (total - available) / 1024 / 1024,
        "ram_available_gb": available / 1024 / 1024,
        "swap_total_gb": swap_total / 1024 / 1024,
        "swap_used_gb": (swap_total - swap_free) / 1024 / 1024,
    }


def pgrep(pattern: str) -> list[tuple[int, str]]:
    proc = subprocess.run(["pgrep", "-af", pattern], text=True, capture_output=True)
    rows: list[tuple[int, str]] = []
    for line in proc.stdout.splitlines():
        parts = line.split(maxsplit=1)
        if not parts or not parts[0].isdigit():
            continue
        rows.append((int(parts[0]), parts[1] if len(parts) > 1 else ""))
    return rows


def process_rss_mb(pid: int) -> float:
    try:
        for line in Path(f"/proc/{pid}/status").read_text(errors="replace").splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024
    except Exception:
        pass
    return 0.0


def process_summary(pattern: str) -> dict[str, Any]:
    rows = pgrep(pattern)
    rss = sum(process_rss_mb(pid) for pid, _ in rows)
    return {
        "count": len(rows),
        "rss_mb": round(rss, 1),
        "sample": [f"{pid} {cmd}" for pid, cmd in rows[:12]],
    }


def load_benchmark_rows() -> dict[str, Any]:
    path = REPORT_DIR / "phase2_force_benchmark.json"
    if not path.exists():
        return {"rows": 0, "last": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"rows": 0, "error": repr(exc), "last": []}
    rows = data.get("rows", [])
    return {
        "rows": len(rows),
        "last": [
            {
                "split": row.get("split"),
                "status": row.get("status"),
                "reason": row.get("reason"),
                "ram": row.get("peak_ram_used_gb"),
                "swap": row.get("peak_swap_gb"),
            }
            for row in rows[-8:]
        ],
    }


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + ("\n" if text and not text.endswith("\n") else ""), encoding="utf-8")


def append_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(text + ("\n" if text and not text.endswith("\n") else ""))


def sample_once() -> dict[str, Any]:
    load1, load5, load15 = os.getloadavg()
    dft = process_summary(DFT_PATTERN)
    ui = process_summary(UI_PATTERN)
    mem = meminfo()
    bench = load_benchmark_rows()
    return {
        "timestamp": iso_now(),
        "load1": round(load1, 2),
        "load5": round(load5, 2),
        "load15": round(load15, 2),
        **mem,
        "dft_process_count": dft["count"],
        "dft_rss_mb": dft["rss_mb"],
        "ui_process_count": ui["count"],
        "ui_rss_mb": ui["rss_mb"],
        "benchmark_rows": bench["rows"],
        "benchmark_last_split": bench["last"][-1]["split"] if bench["last"] else "",
        "benchmark_last_status": bench["last"][-1]["status"] if bench["last"] else "",
    }


def write_snapshot(log_dir: Path, label: str, start_local: str) -> None:
    chunks = [
        f"===== {label} {iso_now()} =====",
        "",
        "### free -h",
        run_cmd(["free", "-h"]),
        "",
        "### uptime",
        run_cmd(["uptime"]),
        "",
        "### benchmark rows",
        json.dumps(load_benchmark_rows(), indent=2, ensure_ascii=False),
        "",
        "### DFT processes",
        run_cmd(["pgrep", "-af", DFT_PATTERN]),
        "",
        "### UI processes",
        run_cmd(["pgrep", "-af", UI_PATTERN]),
        "",
        "### top memory",
        run_cmd(["bash", "-lc", "ps -eo pid,ppid,stat,etime,%cpu,%mem,rss,cmd --sort=-%mem | head -40"]),
        "",
        "### top cpu",
        run_cmd(["bash", "-lc", "ps -eo pid,ppid,stat,etime,%cpu,%mem,rss,cmd --sort=-%cpu | head -40"]),
        "",
        "### kernel suspects since start",
        run_cmd(["bash", "-lc", f"journalctl -k --since '{start_local}' --no-pager 2>/dev/null | grep -Ei '{SUSPECT_JOURNAL}' | tail -160 || true"], timeout=12),
        "",
        "### user/session suspects since start",
        run_cmd(["bash", "-lc", f"journalctl --since '{start_local}' --no-pager 2>/dev/null | grep -Ei '{SUSPECT_JOURNAL}' | tail -220 || true"], timeout=12),
        "",
        "### crashpad recent",
        run_cmd(["bash", "-lc", "find ~/.config/Code/Crashpad -maxdepth 3 -type f -mmin -60 -printf '%TY-%Tm-%Td %TH:%TM %p %s\\n' 2>/dev/null | sort | tail -80 || true"]),
        "",
    ]
    append_text(log_dir / "phase2_force_benchmark_crash_watch.log", "\n".join(chunks))


def kill_process_group(proc: subprocess.Popen[Any]) -> None:
    try:
        pgid = os.getpgid(proc.pid)
    except ProcessLookupError:
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            return
        time.sleep(3)


def main() -> None:
    parser = argparse.ArgumentParser(description="Flight recorder para benchmark Fase 2A.")
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--maxiter", type=int, default=2)
    parser.add_argument("--swap-limit-gb", type=float, default=10.0)
    parser.add_argument("--splits", default="all")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--ram-limit-gb", type=float, default=60.0)
    parser.add_argument("--min-available-gb", type=float, default=4.0)
    args = parser.parse_args()

    stamp = utc_stamp()
    log_dir = REPORT_DIR / "crash_watch" / stamp
    log_dir.mkdir(parents=True, exist_ok=True)
    start_local = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    csv_path = log_dir / "samples.csv"
    jsonl_path = log_dir / "samples.jsonl"
    bench_log = log_dir / "benchmark_stdout_stderr.log"
    summary_path = log_dir / "summary.json"

    cmd = [
        str(GPAW_PYTHON),
        str(BENCH_SCRIPT),
        "--maxiter",
        str(args.maxiter),
        "--swap-limit-gb",
        str(args.swap_limit_gb),
        "--ram-limit-gb",
        str(args.ram_limit_gb),
        "--min-available-gb",
        str(args.min_available_gb),
        "--splits",
        args.splits,
    ]
    if args.resume:
        cmd.append("--resume")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    env["MPLCONFIGDIR"] = "/tmp/mpl-phase2"
    env["DFT_RUNS_ROOT"] = str(EXTERNAL_RUNS_ROOT)
    env["PHASE2_FORCE_RUNS_DIR"] = str(PHASE2_FORCE_RUNS_DIR)

    write_text(log_dir / "command.json", json.dumps({
        "started_at": iso_now(),
        "start_local": start_local,
        "cwd": str(ROOT),
        "cmd": cmd,
        "interval_s": args.interval,
    }, indent=2, ensure_ascii=False))
    write_snapshot(log_dir, "preflight", start_local)

    with bench_log.open("w", encoding="utf-8") as bench_handle, csv_path.open("w", newline="", encoding="utf-8") as csv_handle:
        proc = subprocess.Popen(
            cmd,
            cwd=ROOT,
            env=env,
            stdout=bench_handle,
            stderr=bench_handle,
            preexec_fn=os.setsid,
        )
        fieldnames = list(sample_once().keys()) + ["benchmark_pid", "benchmark_returncode"]
        writer = csv.DictWriter(csv_handle, fieldnames=fieldnames)
        writer.writeheader()
        last_snapshot = 0.0
        samples = 0
        try:
            while proc.poll() is None:
                row = sample_once()
                row["benchmark_pid"] = proc.pid
                row["benchmark_returncode"] = ""
                writer.writerow(row)
                csv_handle.flush()
                append_text(jsonl_path, json.dumps(row, ensure_ascii=False))
                samples += 1
                if time.time() - last_snapshot > 60:
                    write_snapshot(log_dir, f"periodic_{samples}", start_local)
                    last_snapshot = time.time()
                time.sleep(args.interval)
        except KeyboardInterrupt:
            write_snapshot(log_dir, "keyboard_interrupt", start_local)
            kill_process_group(proc)
            raise
        finally:
            rc = proc.poll()
            if rc is None:
                kill_process_group(proc)
                rc = proc.wait(timeout=10)
            row = sample_once()
            row["benchmark_pid"] = proc.pid
            row["benchmark_returncode"] = rc
            writer.writerow(row)
            append_text(jsonl_path, json.dumps(row, ensure_ascii=False))

    write_snapshot(log_dir, "postrun", start_local)
    summary = {
        "finished_at": iso_now(),
        "benchmark_returncode": rc,
        "log_dir": str(log_dir),
        "samples_csv": str(csv_path),
        "samples_jsonl": str(jsonl_path),
        "benchmark_log": str(bench_log),
        "benchmark_rows": load_benchmark_rows(),
        "latest_memory": meminfo(),
        "dft_processes_after": process_summary(DFT_PATTERN),
        "ui_processes_after": process_summary(UI_PATTERN),
    }
    write_text(summary_path, json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
