"""Runner dedicado para jobs Fase 2A."""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from buho.phase2_force import ROOT
from buho.phase2_force.common import RUNS_DIR, display_path


CONDA_BIN = str(Path.home() / "miniforge3" / "bin" / "conda")
GPAW_ENV = "gpaw246"
GPAW_SETUP_PATH = str(ROOT / ".venv" / "lib" / "python3.12" / "site-packages" / "gpaw_data" / "setups")
ACTIVE_PATTERN = ("buho_relax_runner", "phase2_force_runner", "mpiexec", "mpirun", "input.py", "conda run")
SCF_ITER_RE = re.compile(r"iter:\s*(\d+)\s+\d{1,2}:\d{2}:\d{2}")


def ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_status(job_dir: Path) -> dict:
    try:
        return json.loads((job_dir / "status.json").read_text(encoding="utf-8"))
    except Exception:
        return {"status": "unknown"}


def write_status(job_dir: Path, update: dict) -> None:
    status = read_status(job_dir)
    status.update(update)
    (job_dir / "status.json").write_text(json.dumps(status, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def acquire_lock(lock_path: Path):
    import fcntl

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    handle.write(f"pid={os.getpid()} started={datetime.now().isoformat()}Z\n")
    handle.flush()
    return handle


def active_dft_processes() -> list[str]:
    current_tree = {os.getpid()}
    pid = os.getpid()
    while True:
        try:
            status = Path(f"/proc/{pid}/status").read_text(encoding="utf-8", errors="replace")
        except Exception:
            break
        ppid = None
        for line in status.splitlines():
            if line.startswith("PPid:"):
                try:
                    ppid = int(line.split()[1])
                except Exception:
                    ppid = None
                break
        if not ppid or ppid in current_tree:
            break
        current_tree.add(ppid)
        pid = ppid
    try:
        proc = subprocess.run(["pgrep", "-af", "|".join(ACTIVE_PATTERN)], capture_output=True, text=True)
    except Exception:
        return []
    lines = []
    for line in proc.stdout.splitlines():
        parts = line.split(maxsplit=1)
        try:
            pid = int(parts[0])
        except Exception:
            pid = None
        if pid in current_tree or "pgrep -af" in line:
            continue
        if "phase2_force_smoke_benchmark.py" in line:
            continue
        lines.append(line)
    return lines


def log(batch_dir: Path, message: str, also_print: bool = True) -> None:
    line = f"[{ts()}] {message}"
    if also_print:
        print(line, flush=True)
    with (batch_dir / "runner.log").open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def parse_epoch(value: str | None) -> float | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def label_log_paths(job_dir: Path) -> list[Path]:
    st = read_status(job_dir)
    paths: list[Path] = []
    for label in st.get("labels_expected") or []:
        rel = label.get("relative_dir")
        if rel:
            paths.append(job_dir / rel / "r2scan.txt")
    paths.extend(job_dir.glob("r2scan/r2scan.txt"))
    paths.extend(job_dir.glob("u_scan/*/r2scan.txt"))
    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        if path not in seen:
            seen.add(path)
            deduped.append(path)
    return deduped


def scf_log_progress(job_dir: Path) -> dict:
    st = read_status(job_dir)
    started_epoch = parse_epoch(st.get("started_at") or st.get("start_time"))
    newest: dict | None = None
    fresh_logs = 0
    total_iters = 0
    now = time.time()

    for path in label_log_paths(job_dir):
        if not path.exists():
            continue
        stat = path.stat()
        if started_epoch is not None and stat.st_mtime < started_epoch - 120:
            continue
        fresh_logs += 1
        try:
            text = path.read_text(errors="replace")
        except Exception:
            text = ""
        matches = [int(value) for value in SCF_ITER_RE.findall(text)]
        last_iter = matches[-1] if matches else 0
        total_iters += last_iter
        item = {
            "path": path,
            "relative_path": str(path.relative_to(job_dir)),
            "mtime": stat.st_mtime,
            "age_min": (now - stat.st_mtime) / 60,
            "last_iter": last_iter,
            "size": stat.st_size,
        }
        if newest is None or stat.st_mtime > newest["mtime"]:
            newest = item

    return {
        "fresh_logs": fresh_logs,
        "total_iters": total_iters,
        "newest": newest,
    }


def processes_under_job(job_dir: Path, root_pid: int | None = None) -> set[int]:
    job_root = str(job_dir.resolve())
    pids: set[int] = set()
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        pid = int(proc.name)
        try:
            cwd = os.readlink(proc / "cwd")
        except Exception:
            continue
        if cwd == job_root or cwd.startswith(job_root + os.sep):
            pids.add(pid)

    if isinstance(root_pid, int):
        pids.add(root_pid)
        changed = True
        while changed:
            changed = False
            for proc in Path("/proc").iterdir():
                if not proc.name.isdigit():
                    continue
                pid = int(proc.name)
                if pid in pids:
                    continue
                try:
                    status = (proc / "status").read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                ppid = None
                for line in status.splitlines():
                    if line.startswith("PPid:"):
                        try:
                            ppid = int(line.split()[1])
                        except Exception:
                            ppid = None
                        break
                if ppid in pids:
                    pids.add(pid)
                    changed = True
    return pids


def kill_job_processes(batch_dir: Path, job_dir: Path, root_pid: int | None) -> list[int]:
    pids = processes_under_job(job_dir, root_pid)
    pgids: set[int] = set()
    for pid in sorted(pids):
        try:
            pgids.add(os.getpgid(pid))
        except ProcessLookupError:
            pass
    for pgid in sorted(pgids):
        try:
            os.killpg(pgid, signal.SIGTERM)
            log(batch_dir, f"SELF-HEAL SIGTERM pgid={pgid} job={job_dir.name}")
        except ProcessLookupError:
            pass
    for pid in sorted(pids):
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
    time.sleep(3)
    for pid in sorted(pids):
        if not Path(f"/proc/{pid}").exists():
            continue
        try:
            os.kill(pid, signal.SIGKILL)
            log(batch_dir, f"SELF-HEAL SIGKILL pid={pid} job={job_dir.name}")
        except (ProcessLookupError, PermissionError):
            pass
    return sorted(pids)


def stalled_no_scf_reason(slot: Slot, threshold_min: float) -> str | None:
    if threshold_min <= 0 or slot.elapsed_min < threshold_min:
        return None
    progress = scf_log_progress(slot.job_dir)
    newest = progress.get("newest")
    if newest and int(newest.get("last_iter") or 0) == 0 and float(newest.get("age_min") or 0) >= threshold_min:
        return (
            f"no_scf_iterations_after_{slot.elapsed_min:.1f}min; "
            f"latest_log={newest['relative_path']}; "
            f"log_age={float(newest['age_min']):.1f}min; "
            f"log_size={newest['size']}"
        )
    if not newest and slot.elapsed_min >= threshold_min:
        return f"no_phase2_scf_log_after_{slot.elapsed_min:.1f}min"
    return None


def self_heal_slot(batch_dir: Path, slot: Slot, reason: str) -> bool:
    st = read_status(slot.job_dir)
    pid = st.get("pid")
    now = datetime.now(timezone.utc).isoformat()
    write_status(slot.job_dir, {
        "status": "failed",
        "self_healed": True,
        "self_heal_action": "killed_stalled_no_scf_job",
        "self_heal_reason": reason,
        "finished_at": now,
        "updated_at": now,
    })
    killed = kill_job_processes(batch_dir, slot.job_dir, pid if isinstance(pid, int) else slot.proc.pid)
    write_status(slot.job_dir, {"self_heal_pids": killed})
    try:
        slot.proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    log(batch_dir, f"SELF-HEAL DONE {slot.job_dir.name} reason={reason}")
    return True


def cleanup_stale_running(batch_dir: Path) -> int:
    n = 0
    for job_dir in sorted(d for d in batch_dir.iterdir() if d.is_dir()):
        st = read_status(job_dir)
        if st.get("status") != "running":
            continue
        pid = st.get("pid")
        if isinstance(pid, int) and pid_alive(pid):
            continue
        write_status(job_dir, {
            "status": "pending",
            "recovered_from": "stale-running",
            "stale_pid": pid,
            "recovered_at": datetime.utcnow().isoformat() + "Z",
        })
        n += 1
    return n


def jobs_by_status(batch_dir: Path, statuses: set[str]) -> list[Path]:
    jobs = [d for d in batch_dir.iterdir() if d.is_dir() and read_status(d).get("status") in statuses]
    jobs.sort(key=lambda path: int(read_status(path).get("selection_rank", 10**9)))
    return jobs


class Slot:
    def __init__(self, job_dir: Path, proc: subprocess.Popen):
        self.job_dir = job_dir
        self.proc = proc
        self.started = datetime.now()

    @property
    def elapsed_min(self) -> float:
        return (datetime.now() - self.started).total_seconds() / 60


def launch_job(batch_dir: Path, job_dir: Path, cores: int) -> Slot:
    inner = f"export GPAW_SETUP_PATH={GPAW_SETUP_PATH}; exec mpiexec -n {cores} python input.py"
    cmd = [CONDA_BIN, "run", "-n", GPAW_ENV, "bash", "-c", inner]
    env = os.environ.copy()
    env["OMP_NUM_THREADS"] = "1"
    env["OPENBLAS_NUM_THREADS"] = "1"
    env["MKL_NUM_THREADS"] = "1"
    stdout = open(job_dir / "runner_stdout.log", "w")
    stderr = open(job_dir / "runner_stderr.log", "w")
    proc = subprocess.Popen(
        cmd,
        cwd=str(job_dir),
        stdout=stdout,
        stderr=stderr,
        env=env,
        preexec_fn=os.setsid,
    )
    write_status(job_dir, {
        "status": "running",
        "pid": proc.pid,
        "mpi_cores": cores,
        "started_at": datetime.utcnow().isoformat() + "Z",
    })
    log(batch_dir, f"LAUNCH {job_dir.name} pid={proc.pid} cores={cores}")
    return Slot(job_dir, proc)


def check_slot(batch_dir: Path, slot: Slot) -> bool:
    ret = slot.proc.poll()
    if ret is None:
        return False
    st = read_status(slot.job_dir)
    if st.get("status") == "running":
        write_status(slot.job_dir, {
            "status": "failed",
            "returncode": ret,
            "elapsed_min": round(slot.elapsed_min, 1),
            "finished_at": datetime.utcnow().isoformat() + "Z",
        })
    log(batch_dir, f"DONE {slot.job_dir.name} status={read_status(slot.job_dir).get('status')} rc={ret} elapsed={slot.elapsed_min:.1f} min")
    return True


def run_batch(batch_id: int, slots: int = 5, cores: int = 8, poll: int = 30, stagger: int = 8,
              dry_run: bool = False, resume: bool = False, override_active: bool = False,
              runs_dir: Path = RUNS_DIR, start_real: bool = False,
              limit: int | None = None, no_scf_stall_minutes: float = 60.0) -> dict:
    batch_dir = runs_dir / f"batch_{batch_id:03d}"
    if not batch_dir.exists():
        raise FileNotFoundError(f"No existe {batch_dir}; prepara el lote primero.")

    if not dry_run and not start_real:
        raise RuntimeError("Guard activo: usa --dry-run o confirma una corrida real con --start-real.")

    active = active_dft_processes()
    if active and not override_active and not dry_run:
        raise RuntimeError("Hay procesos DFT/runner activos; usa --override-active solo si estas seguro:\n" + "\n".join(active[:20]))

    if dry_run:
        global_lock = None
        batch_lock = None
    else:
        global_lock = acquire_lock(runs_dir / ".phase2_force_global.lock")
        if global_lock is None:
            raise RuntimeError(f"Otro runner phase2_force ya tiene lock global en {runs_dir}")
        batch_lock = acquire_lock(batch_dir / ".runner.lock")
        if batch_lock is None:
            raise RuntimeError(f"Otro runner ya tiene lock del lote {batch_id}")

    if not resume and not dry_run:
        cleanup_stale_running(batch_dir)

    pending = jobs_by_status(batch_dir, {"pending"} if not resume else {"pending", "failed"})
    if limit is not None:
        pending = pending[:limit]
    summary = {
        "batch_id": batch_id,
        "batch_dir": display_path(batch_dir),
        "slots": slots,
        "cores": cores,
        "n_pending": len(pending),
        "limit": limit,
        "dry_run": dry_run,
    }
    log(batch_dir, f"PHASE2 FORCE runner batch={batch_id} pending={len(pending)} slots={slots} cores={cores}")
    if dry_run:
        for job in pending[:10]:
            log(batch_dir, f"DRY {job.name} {read_status(job).get('formula')}")
        return summary

    stop = [False]
    active_slots: list[Slot] = []

    def _shutdown(_sig, _frame):
        log(batch_dir, "SHUTDOWN recibido; no se lanzan jobs nuevos")
        stop[0] = True

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    idx = 0
    while not stop[0]:
        active_slots = [slot for slot in active_slots if not check_slot(batch_dir, slot)]
        healed_slots: list[Slot] = []
        for slot in active_slots:
            reason = stalled_no_scf_reason(slot, no_scf_stall_minutes)
            if reason and self_heal_slot(batch_dir, slot, reason):
                healed_slots.append(slot)
        if healed_slots:
            active_slots = [slot for slot in active_slots if slot not in healed_slots]
        free = slots - len(active_slots)
        while free > 0 and idx < len(pending) and not stop[0]:
            job = pending[idx]
            idx += 1
            if read_status(job).get("status") not in {"pending", "failed"}:
                continue
            if read_status(job).get("status") == "failed" and not resume:
                continue
            active_slots.append(launch_job(batch_dir, job, cores))
            free -= 1
            if stagger and free > 0 and idx < len(pending):
                time.sleep(stagger)
                active_slots = [slot for slot in active_slots if not check_slot(batch_dir, slot)]
                free = slots - len(active_slots)

        n_conv = len(jobs_by_status(batch_dir, {"converged"}))
        n_part = len(jobs_by_status(batch_dir, {"partial"}))
        n_fail = len(jobs_by_status(batch_dir, {"failed"}))
        n_pend = len(jobs_by_status(batch_dir, {"pending"}))
        log(batch_dir, f"STATUS pending={n_pend} running={len(active_slots)} partial={n_part} converged={n_conv} failed={n_fail}")

        if not active_slots and idx >= len(pending):
            break
        time.sleep(poll)

    return {
        **summary,
        "n_converged": len(jobs_by_status(batch_dir, {"converged"})),
        "n_partial": len(jobs_by_status(batch_dir, {"partial"})),
        "n_failed": len(jobs_by_status(batch_dir, {"failed"})),
        "n_remaining": len(jobs_by_status(batch_dir, {"pending"})),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Runner Fase 2A DFT E+F.")
    parser.add_argument("--batch-id", type=int, required=True)
    parser.add_argument("--slots", type=int, default=5)
    parser.add_argument("--cores", type=int, default=8)
    parser.add_argument("--poll", type=int, default=30)
    parser.add_argument("--stagger", type=int, default=8)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--start-real", action="store_true",
                        help="Confirmacion explicita para lanzar DFT real; sin esto solo se permite --dry-run.")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--override-active", action="store_true")
    parser.add_argument("--runs-dir", default=str(RUNS_DIR))
    parser.add_argument("--limit", type=int, default=None,
                        help="Maximo de jobs logicos a lanzar en esta invocacion.")
    parser.add_argument("--no-scf-stall-minutes", type=float, default=60.0,
                        help="Self-heal: mata jobs Fase 2A sin iteraciones SCF en el log activo tras este tiempo; 0 desactiva.")
    args = parser.parse_args()
    result = run_batch(args.batch_id, args.slots, args.cores, args.poll, args.stagger,
                       args.dry_run, args.resume, args.override_active, Path(args.runs_dir),
                       start_real=args.start_real, limit=args.limit,
                       no_scf_stall_minutes=args.no_scf_stall_minutes)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
