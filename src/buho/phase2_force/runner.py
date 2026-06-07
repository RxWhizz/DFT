"""Runner dedicado para jobs Fase 2A."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
from datetime import datetime
from pathlib import Path

from buho.phase2_force import ROOT
from buho.phase2_force.common import RUNS_DIR


CONDA_BIN = str(Path.home() / "miniforge3" / "bin" / "conda")
GPAW_ENV = "gpaw246"
GPAW_SETUP_PATH = str(ROOT / ".venv" / "lib" / "python3.12" / "site-packages" / "gpaw_data" / "setups")
ACTIVE_PATTERN = ("buho_relax_runner", "phase2_force_runner", "mpiexec", "mpirun", "gpaw", "input.py", "conda run")


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
    try:
        proc = subprocess.run(["pgrep", "-af", "|".join(ACTIVE_PATTERN)], capture_output=True, text=True)
    except Exception:
        return []
    lines = []
    this_pid = str(os.getpid())
    for line in proc.stdout.splitlines():
        if this_pid in line or "pgrep -af" in line:
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
              runs_dir: Path = RUNS_DIR) -> dict:
    batch_dir = runs_dir / f"batch_{batch_id:03d}"
    if not batch_dir.exists():
        raise FileNotFoundError(f"No existe {batch_dir}; prepara el lote primero.")

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
    summary = {
        "batch_id": batch_id,
        "batch_dir": str(batch_dir.relative_to(ROOT)),
        "slots": slots,
        "cores": cores,
        "n_pending": len(pending),
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
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--override-active", action="store_true")
    parser.add_argument("--runs-dir", default=str(RUNS_DIR))
    args = parser.parse_args()
    result = run_batch(args.batch_id, args.slots, args.cores, args.poll, args.stagger,
                       args.dry_run, args.resume, args.override_active, Path(args.runs_dir))
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
