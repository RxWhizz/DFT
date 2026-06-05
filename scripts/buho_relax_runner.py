#!/usr/bin/env python3
"""Scheduler para relajaciones BUHO — 2 slots MPI simultáneos.

Gestiona una cola de jobs pendientes en runs/relax_basic/ y mantiene
hasta N_SLOTS procesos mpirun activos en paralelo.

Uso:
    python scripts/buho_relax_runner.py
    python scripts/buho_relax_runner.py --slots 2 --cores 22
    python scripts/buho_relax_runner.py --slots 1 --cores 44 --filter pure

Por cada job:
  cd runs/relax_basic/{id}/ && mpirun -n 22 python input.py

Actualiza status.json:
  pending  → running (al lanzar, con pid y start_time)
  running  → converged / failed (la input.py actualiza al terminar)
             si el proceso muere sin actualizar → runner marca como failed
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RELAX_DIR = ROOT / "runs" / "relax_basic"
LOG_FILE = RELAX_DIR / "runner.log"


def ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str, also_print: bool = True) -> None:
    line = f"[{ts()}] {msg}"
    if also_print:
        print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def read_status(job_dir: Path) -> dict:
    p = job_dir / "status.json"
    try:
        return json.loads(p.read_text())
    except Exception:
        return {"status": "unknown"}


def write_status(job_dir: Path, update: dict) -> None:
    p = job_dir / "status.json"
    try:
        current = read_status(job_dir)
        current.update(update)
        p.write_text(json.dumps(current, indent=2))
    except Exception as e:
        log(f"WARN  cannot write {p}: {e}")


def is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


# Mapa candidate_id → pre_dft_score (los mejores se procesan primero)
def _load_score_map() -> dict:
    import csv
    scores: dict[str, float] = {}
    top_csv = RELAX_DIR.parent.parent / "data" / "processed" / "top500_candidates.csv"
    if top_csv.exists():
        try:
            with open(top_csv) as f:
                for row in csv.DictReader(f):
                    cid = row.get("candidate_id")
                    sc = row.get("pre_dft_score")
                    if cid and sc:
                        scores[cid] = float(sc)
        except Exception:
            pass
    return scores


_SCORE_MAP = _load_score_map()


def get_jobs_by_status(status: str) -> list[Path]:
    jobs = [
        d for d in RELAX_DIR.iterdir()
        if d.is_dir() and read_status(d).get("status") == status
    ]
    # Orden por score descendente (mejores primero); sin score → al final
    jobs.sort(key=lambda d: (-_SCORE_MAP.get(d.name, -1.0), d.name))
    return jobs


class Slot:
    def __init__(self, job_dir: Path, proc: subprocess.Popen):
        self.job_dir = job_dir
        self.proc = proc
        self.started = datetime.now()
        self.formula = read_status(job_dir).get("formula", job_dir.name)

    @property
    def elapsed_min(self) -> float:
        return (datetime.now() - self.started).total_seconds() / 60


def launch_job(job_dir: Path, n_cores: int, mpirun: str = "mpirun") -> Slot:
    """Lanza mpirun -n {cores} python input.py en el directorio del job."""
    python = sys.executable
    cmd = [mpirun, "-n", str(n_cores), python, "input.py"]

    stdout_log = open(job_dir / "runner_stdout.log", "w")
    stderr_log = open(job_dir / "runner_stderr.log", "w")

    # Pinear BLAS/OMP a 1 thread por job: GPAW PW no escala con threads
    # (FFT/bandwidth-bound) y sin pin cada job intenta tomar todos los cores
    # → oversubscription. 1 thread/job + N jobs concurrentes es el modelo correcto.
    env = os.environ.copy()
    env["OMP_NUM_THREADS"] = "1"
    env["OPENBLAS_NUM_THREADS"] = "1"
    env["MKL_NUM_THREADS"] = "1"

    proc = subprocess.Popen(
        cmd,
        cwd=str(job_dir),
        stdout=stdout_log,
        stderr=stderr_log,
        env=env,
        preexec_fn=os.setsid,  # grupo propio para poder matar con SIGTERM
    )

    write_status(job_dir, {
        "status": "running",
        "pid": proc.pid,
        "mpi_cores": n_cores,
        "start_time": datetime.now().isoformat() + "Z",
    })

    log(f"LAUNCH {job_dir.name[:12]}  formula={read_status(job_dir).get('formula','?')}  "
        f"pid={proc.pid}  cores={n_cores}")
    return Slot(job_dir, proc)


def check_slot(slot: Slot) -> bool:
    """Retorna True si el job terminó (o murió). Actualiza status si murió sin actualizar."""
    ret = slot.proc.poll()
    if ret is None:
        return False  # sigue corriendo

    # Proceso terminado — ver si input.py ya actualizó status
    st = read_status(slot.job_dir)
    if st.get("status") == "running":
        # input.py no actualizó (crash o kill)
        outcome = "converged" if ret == 0 else "failed"
        write_status(slot.job_dir, {
            "status": outcome,
            "returncode": ret,
            "elapsed_min": round(slot.elapsed_min, 1),
            "finished_at": datetime.now().isoformat() + "Z",
        })
    else:
        outcome = st.get("status", "?")

    log(f"DONE  {slot.job_dir.name[:12]}  formula={slot.formula}  "
        f"status={outcome}  elapsed={slot.elapsed_min:.1f} min  rc={ret}")

    # Cerrar logs del runner
    try:
        slot.proc.stdout.close()  # type: ignore[union-attr]
        slot.proc.stderr.close()  # type: ignore[union-attr]
    except Exception:
        pass

    return True


def main():
    import argparse
    ap = argparse.ArgumentParser(description="BUHO relax scheduler (2 slots MPI)")
    ap.add_argument("--slots",  type=int, default=2,    help="Slots MPI simultáneos")
    ap.add_argument("--cores",  type=int, default=22,   help="Cores MPI por slot")
    ap.add_argument("--relax-dir", default=str(RELAX_DIR), help="Directorio de jobs")
    ap.add_argument("--filter",    default=None, help="Filtrar por modo (ej: pure)")
    ap.add_argument("--poll",   type=int, default=30,   help="Intervalo de polling (s)")
    ap.add_argument("--mpirun", default="mpirun",       help="Ejecutable mpirun")
    ap.add_argument("--dry-run", action="store_true",   help="Solo mostrar jobs, no lanzar")
    args = ap.parse_args()

    relax_dir = Path(args.relax_dir)

    # Señal de parada limpia
    _stop = [False]
    active_slots: list[Slot] = []

    def _shutdown(sig, frame):
        log("SHUTDOWN señal recibida — esperando jobs activos...")
        _stop[0] = True

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    pending = get_jobs_by_status("pending")
    if args.filter:
        pending = [d for d in pending
                   if read_status(d).get("generation_mode") == args.filter
                   or args.filter in read_status(d).get("formula", "")]

    log(f"{'='*70}")
    log(f"BUHO Relax Runner — {ts()}")
    log(f"Jobs pendientes: {len(pending)}  Slots: {args.slots}  Cores/slot: {args.cores}")
    log(f"Directorio: {relax_dir}")
    log(f"{'='*70}")

    if args.dry_run:
        log("DRY-RUN: primeros 5 jobs que se lanzarían:")
        for d in pending[:5]:
            log(f"  {d.name} — {read_status(d).get('formula','?')}")
        return

    idx = 0  # índice en cola de pendientes

    while not _stop[0]:
        # ── Recoger jobs terminados ─────────────────────────────────────────
        active_slots = [s for s in active_slots if not check_slot(s)]

        # ── Lanzar nuevos jobs si hay slots libres ──────────────────────────
        slots_free = args.slots - len(active_slots)
        while slots_free > 0 and idx < len(pending):
            job_dir = pending[idx]
            idx += 1
            # Recheck — puede que otro runner ya lo haya lanzado
            if read_status(job_dir).get("status") != "pending":
                continue
            try:
                slot = launch_job(job_dir, args.cores, args.mpirun)
                active_slots.append(slot)
                slots_free -= 1
            except Exception as e:
                log(f"ERROR lanzando {job_dir.name}: {e}")

        # ── Recargar pendientes si hay más en disco ─────────────────────────
        if idx >= len(pending) and active_slots:
            # puede haber llegado más (raro, pero seguro)
            pending = get_jobs_by_status("pending")
            if args.filter:
                pending = [d for d in pending
                           if args.filter in read_status(d).get("formula", "")]
            idx = 0

        # ── Salir si no hay nada más ────────────────────────────────────────
        if not active_slots and idx >= len(pending):
            log("DONE Todos los jobs completados.")
            break

        # ── Estado rápido cada poll ─────────────────────────────────────────
        n_conv = len(get_jobs_by_status("converged"))
        n_fail = len(get_jobs_by_status("failed"))
        n_run  = len(active_slots)
        n_pend = len(get_jobs_by_status("pending"))
        log(f"STATUS  pendiente={n_pend}  corriendo={n_run}  "
            f"convergido={n_conv}  fallido={n_fail}", also_print=True)

        time.sleep(args.poll)

    # Esperar slots activos restantes al terminar limpiamente
    if _stop[0] and active_slots:
        log(f"Esperando {len(active_slots)} jobs activos...")
        for s in active_slots:
            try:
                s.proc.wait(timeout=300)
                check_slot(s)
            except subprocess.TimeoutExpired:
                log(f"TIMEOUT {s.job_dir.name} — enviando SIGTERM")
                os.killpg(os.getpgid(s.proc.pid), signal.SIGTERM)


if __name__ == "__main__":
    main()
