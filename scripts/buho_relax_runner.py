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

import atexit
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from buho import dft_runtime
RELAX_DIR = ROOT / "runs" / "relax_basic"
LOG_FILE = RELAX_DIR / "runner.log"


def ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str, also_print: bool = True) -> None:
    line = f"[{ts()}] {msg}"
    if also_print:
        print(line, flush=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
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
    except (ProcessLookupError, PermissionError, OSError):
        return False


def pid_cwd(pid: int) -> Path | None:
    if os.name != "posix":
        return None
    try:
        return Path(f"/proc/{pid}/cwd").resolve()
    except Exception:
        return None


def pid_matches_job(pid: int, job_dir: Path) -> bool:
    cwd = pid_cwd(pid)
    if cwd:
        return cwd == job_dir.resolve()
    return os.name != "posix" and is_pid_alive(pid)


class RunnerLock:
    def __init__(self, handle, lock_path: Path, *, remove_on_close: bool = False):
        self.handle = handle
        self.lock_path = lock_path
        self.remove_on_close = remove_on_close

    def close(self) -> None:
        try:
            self.handle.close()
        finally:
            if self.remove_on_close:
                try:
                    self.lock_path.unlink()
                except FileNotFoundError:
                    pass
                except Exception:
                    pass


def _pid_from_lock(lock_path: Path) -> int | None:
    try:
        text = lock_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    for token in text.replace("\n", " ").split():
        if token.startswith("pid="):
            try:
                return int(token.split("=", 1)[1])
            except ValueError:
                return None
    return None


def acquire_runner_lock(relax_dir: Path) -> RunnerLock | None:
    """Evita dos runners simultáneos sobre el mismo batch/directorio."""

    lock_path = relax_dir / ".runner.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        import fcntl

        fh = open(lock_path, "w")
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log(f"ABORT otro runner ya tiene el candado: {lock_path}")
            fh.close()
            return None
        remove_on_close = False
    else:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            pid = _pid_from_lock(lock_path)
            if pid is not None and not is_pid_alive(pid):
                try:
                    lock_path.unlink()
                    fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                except Exception:
                    log(f"ABORT otro runner ya tiene el candado: {lock_path}")
                    return None
            else:
                log(f"ABORT otro runner ya tiene el candado: {lock_path}")
                return None
        fh = os.fdopen(fd, "w")
        remove_on_close = True
    fh.seek(0)
    fh.truncate()
    fh.write(f"pid={os.getpid()} started={datetime.now().isoformat()}Z\n")
    fh.flush()
    return RunnerLock(fh, lock_path, remove_on_close=remove_on_close)


def cleanup_stale_running(relax_dir: Path) -> int:
    """Regresa a pending jobs marcados running cuyo PID ya no corresponde al job."""
    n = 0
    for job_dir in relax_dir.iterdir():
        if not job_dir.is_dir():
            continue
        st = read_status(job_dir)
        if st.get("status") != "running":
            continue
        pid = st.get("pid")
        alive = isinstance(pid, int) and is_pid_alive(pid) and pid_matches_job(pid, job_dir)
        if alive:
            continue
        update = {
            "status": "pending",
            "candidate_id": st.get("candidate_id", job_dir.name),
            "formula": st.get("formula", "?"),
            "recovered_from": "stale-running",
            "stale_pid": pid,
            "recovered_at": datetime.now().isoformat() + "Z",
        }
        write_status(job_dir, update)
        for name in ("error.txt", "runner_stdout.log", "runner_stderr.log"):
            try:
                (job_dir / name).unlink()
            except FileNotFoundError:
                pass
            except Exception:
                pass
        n += 1
    if n:
        log(f"RECOVER {n} jobs running con PID muerto/no coincidente -> pending")
    return n


def count_external_running(relax_dir: Path) -> int:
    n = 0
    for job_dir in relax_dir.iterdir():
        if not job_dir.is_dir():
            continue
        st = read_status(job_dir)
        pid = st.get("pid")
        if (
            st.get("status") == "running"
            and isinstance(pid, int)
            and is_pid_alive(pid)
            and pid_matches_job(pid, job_dir)
        ):
            n += 1
    return n


# Mapa candidate_id → pre_dft_score (los mejores se procesan primero)
def _load_score_map(relax_dir: Path = RELAX_DIR) -> dict[str, float]:
    import csv
    scores: dict[str, float] = {}
    candidates = [
        ROOT / "data" / "processed" / "top500_candidates.csv",
        relax_dir.parent.parent / "data" / "processed" / "top500_candidates.csv",
    ]
    for top_csv in candidates:
        if not top_csv.exists():
            continue
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


def get_jobs_by_status(status: str, relax_dir: Path = RELAX_DIR) -> list[Path]:
    score_map = _load_score_map(relax_dir)
    jobs = [
        d for d in relax_dir.iterdir()
        if d.is_dir() and read_status(d).get("status") == status
    ]
    # Orden por score descendente (mejores primero); sin score → al final
    jobs.sort(key=lambda d: (-score_map.get(d.name, -1.0), d.name))
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


def _subprocess_group_kwargs() -> dict:
    if os.name == "posix":
        return {"preexec_fn": os.setsid}
    if sys.platform == "win32":
        flag = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        return {"creationflags": flag} if flag else {}
    return {}


def launch_job(job_dir: Path, n_cores: int, runtime: dft_runtime.DFTRuntime) -> Slot:
    """Lanza un job DFT usando el runtime ya validado por preflight."""
    cmd, env = dft_runtime.build_job_command(job_dir, runtime, n_cores)
    stdout_log = open(job_dir / "runner_stdout.log", "w")
    stderr_log = open(job_dir / "runner_stderr.log", "w")

    proc = subprocess.Popen(
        cmd,
        cwd=str(job_dir),
        stdout=stdout_log,
        stderr=stderr_log,
        env=env,
        **_subprocess_group_kwargs(),
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
        if ret == 0:
            outcome = "converged"
            write_status(slot.job_dir, {
                "status": "converged", "returncode": ret,
                "elapsed_min": round(slot.elapsed_min, 1),
                "finished_at": datetime.now().isoformat() + "Z",
            })
        else:
            # ¿Fallo TRANSITORIO de arranque MPI? (0 iteraciones SCF + murió rápido)
            # → reintentar hasta 2 veces en vez de perder el dato. Fallos reales
            # (con iters, o lentos) se marcan failed sin reintentar.
            n_iters = 0
            r2 = slot.job_dir / "r2scan.txt"
            if r2.exists():
                try:
                    n_iters = r2.read_text(errors="replace").count("iter:")
                except Exception:
                    pass
            retries = int(st.get("retries", 0))
            if n_iters == 0 and slot.elapsed_min < 2.0 and retries < 2:
                for x in ("error.txt", "r2scan.txt"):
                    try: (slot.job_dir / x).unlink()
                    except Exception: pass
                write_status(slot.job_dir, {
                    "status": "pending", "retries": retries + 1,
                    "candidate_id": slot.job_dir.name,
                    "formula": st.get("formula", "?"),
                })
                outcome = f"retry({retries + 1}, transitorio MPI)"
            else:
                outcome = "failed"
                write_status(slot.job_dir, {
                    "status": "failed", "returncode": ret,
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
    ap.add_argument("--slots",  type=int, default=5,    help="Slots MPI simultáneos (óptimo barrido: 5)")
    ap.add_argument("--cores",  type=int, default=8,    help="Cores domain por slot (óptimo barrido: 8)")
    ap.add_argument("--relax-dir", default=str(RELAX_DIR), help="Directorio de jobs")
    ap.add_argument("--filter",    default=None, help="Filtrar por modo (ej: pure)")
    ap.add_argument("--poll",   type=int, default=30,   help="Intervalo de polling (s)")
    ap.add_argument("--stagger", type=int, default=8,   help="Segundos entre arranques (evita lockstep del init/FFT)")
    ap.add_argument("--mpirun", default=None,           help="Ejecutable mpiexec/mpirun para modo directo")
    ap.add_argument("--launcher", choices=["auto", "conda", "direct"], default="auto",
                    help="Runtime GPAW: auto, conda o Python directo")
    ap.add_argument("--conda-bin", default=None, help="Ruta/ejecutable de conda")
    ap.add_argument("--conda-env", default=None, help="Nombre del env con GPAW")
    ap.add_argument("--python", default=None, help="Python con gpaw/ase para launcher direct")
    ap.add_argument("--setup-path", default=None, help="Directorio PAW datasets de GPAW")
    ap.add_argument("--bash", default=None, help="Ruta/ejecutable bash para job.sh")
    ap.add_argument("--preflight-only", action="store_true",
                    help="Validar runtime y salir sin tocar la cola")
    ap.add_argument("--skip-preflight", action="store_true",
                    help="No validar GPAW/ASE/MPI antes de lanzar")
    ap.add_argument("--dry-run", action="store_true",   help="Solo mostrar jobs, no lanzar")
    args = ap.parse_args()

    relax_dir = Path(args.relax_dir)
    global LOG_FILE
    LOG_FILE = relax_dir / "runner.log"

    runtime = None
    if not args.dry_run or args.preflight_only:
        try:
            runtime = dft_runtime.build_runtime(
                repo_root=ROOT,
                launcher=args.launcher,
                conda_bin=args.conda_bin,
                conda_env=args.conda_env,
                python=args.python,
                mpi_launcher=args.mpirun,
                setup_path=args.setup_path,
                bash=args.bash,
            )
            needs_bash = relax_dir.is_dir() and any(
                (job_dir / "job.sh").exists() for job_dir in relax_dir.iterdir() if job_dir.is_dir()
            )
            if not args.skip_preflight:
                dft_runtime.preflight(runtime, n_cores=args.cores, needs_bash=needs_bash)
        except dft_runtime.RuntimeCheckError as exc:
            print(str(exc), file=sys.stderr, flush=True)
            raise SystemExit(2) from exc

    if args.preflight_only:
        assert runtime is not None
        print(json.dumps({"status": "ok", "runtime": runtime.as_dict()}, indent=2), flush=True)
        return

    lock_fh = acquire_runner_lock(relax_dir)
    if lock_fh is None:
        return
    atexit.register(lock_fh.close)

    # Señal de parada limpia
    _stop = [False]
    active_slots: list[Slot] = []

    def _shutdown(sig, frame):
        log("SHUTDOWN señal recibida — esperando jobs activos...")
        _stop[0] = True

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    cleanup_stale_running(relax_dir)
    pending = get_jobs_by_status("pending", relax_dir)
    if args.filter:
        pending = [d for d in pending
                   if read_status(d).get("generation_mode") == args.filter
                   or args.filter in read_status(d).get("formula", "")]

    log(f"{'='*70}")
    log(f"BUHO Relax Runner — {ts()}")
    log(f"Jobs pendientes: {len(pending)}  Slots: {args.slots}  Cores/slot: {args.cores}")
    log(f"Directorio: {relax_dir}")
    if runtime:
        log(f"Runtime DFT: {json.dumps(runtime.as_dict(), ensure_ascii=False)}")
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
        # Stagger: lanzar jobs separados en el tiempo para que NO entren en
        # lockstep (todos golpeando la FFT memory-heavy a la vez). Jobs en
        # fases distintas (compute vs memoria) comparten el bus mejor → más
        # throughput. Ver diagnóstico: lockstep = 305s/iter, desfasado = ~39s/iter.
        cleanup_stale_running(relax_dir)
        external_running = max(0, count_external_running(relax_dir) - len(active_slots))
        slots_free = args.slots - len(active_slots) - external_running
        launched_this_wave = 0
        while slots_free > 0 and idx < len(pending) and not _stop[0]:
            job_dir = pending[idx]
            idx += 1
            # Recheck — puede que otro runner ya lo haya lanzado
            if read_status(job_dir).get("status") != "pending":
                continue
            try:
                assert runtime is not None
                slot = launch_job(job_dir, args.cores, runtime)
                active_slots.append(slot)
                slots_free -= 1
                launched_this_wave += 1
                # Escalonar arranques (excepto el último del wave)
                if args.stagger > 0 and slots_free > 0 and idx < len(pending):
                    time.sleep(args.stagger)
                    # recoger los que terminen durante el stagger
                    active_slots = [s for s in active_slots if not check_slot(s)]
                    if _stop[0]:
                        break
                    cleanup_stale_running(relax_dir)
                    external_running = max(0, count_external_running(relax_dir) - len(active_slots))
                    slots_free = args.slots - len(active_slots) - external_running
            except Exception as e:
                log(f"ERROR lanzando {job_dir.name}: {e}")

        # ── Recargar pendientes si hay más en disco ─────────────────────────
        if idx >= len(pending) and active_slots:
            # puede haber llegado más (raro, pero seguro)
            pending = get_jobs_by_status("pending", relax_dir)
            if args.filter:
                pending = [d for d in pending
                           if args.filter in read_status(d).get("formula", "")]
            idx = 0

        # ── Salir si no hay nada más ────────────────────────────────────────
        if not active_slots and idx >= len(pending):
            log("DONE Todos los jobs completados.")
            break

        # ── Estado rápido cada poll ─────────────────────────────────────────
        n_conv = len(get_jobs_by_status("converged", relax_dir))
        n_fail = len(get_jobs_by_status("failed", relax_dir))
        n_run  = len(active_slots)
        n_pend = len(get_jobs_by_status("pending", relax_dir))
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
                if os.name == "posix":
                    os.killpg(os.getpgid(s.proc.pid), signal.SIGTERM)
                else:
                    s.proc.terminate()
    lock_fh.close()


if __name__ == "__main__":
    main()
