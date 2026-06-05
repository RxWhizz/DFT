#!/usr/bin/env python3
"""Monitor en tiempo real para relajaciones BUHO (runs/relax_basic/).

Muestra un dashboard que se refresca cada N segundos con:
  - Conteos globales: pendiente / corriendo / convergido / fallido
  - Tabla de jobs corriendo: fórmula, tiempo, iteración FIRE, energía, fmax
  - Últimos 5 jobs terminados
  - Log reciente del runner

Uso:
    python scripts/buho_monitor.py
    python scripts/buho_monitor.py --relax-dir runs/relax_basic --interval 30
    python scripts/buho_monitor.py --once          # imprime una vez y sale

Refurbish de gpaw_monitor.py — ahora soporta múltiples jobs simultáneos.
"""
from __future__ import annotations

import json
import os
import re
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RELAX_DIR = ROOT / "runs" / "relax_basic"

# FIRE / BFGS log pattern: "FIRE:   N  HH:MM:SS   -E.EEEEEE  fmax"
_OPTIMIZER_RE = re.compile(
    r"(?:FIRE|BFGS|LBFGS):\s+(\d+)\s+(\d{2}:\d{2}:\d{2})\s+([-\d.]+)\s+([\d.]+)"
)
# r2SCAN / GPAW SCF iter: "iter: N  HH:MM:SS  E  log10..."
_SCF_RE = re.compile(r"iter:\s+(\d+)\s+(\d{2}:\d{2}:\d{2})")
_ENERGY_RE = re.compile(r"Total:\s+([-\d.]+)")


def ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _fmt_elapsed(iso_start: str) -> str:
    try:
        start = datetime.fromisoformat(iso_start.replace("Z", "+00:00")).replace(tzinfo=None)
        secs = (datetime.now() - start).total_seconds()
        h, m = divmod(int(secs), 3600)
        m, s = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"
    except Exception:
        return "??:??:??"


def read_status(job_dir: Path) -> dict:
    p = job_dir / "status.json"
    try:
        return json.loads(p.read_text())
    except Exception:
        return {"status": "unknown", "candidate_id": job_dir.name}


def scan_all_jobs(relax_dir: Path) -> dict[str, list[Path]]:
    """Devuelve dict status→[dirs]."""
    groups: dict[str, list] = {
        "pending": [], "running": [], "converged": [], "failed": [], "other": []
    }
    for d in sorted(relax_dir.iterdir()):
        if not d.is_dir():
            continue
        st = read_status(d).get("status", "other")
        groups.setdefault(st, []).append(d)
    return groups


def parse_relax_log(job_dir: Path) -> dict:
    """Extrae último paso FIRE / BFGS del relax.log."""
    log_file = job_dir / "relax.log"
    if not log_file.exists():
        return {}
    try:
        lines = log_file.read_text(errors="replace").splitlines()
        for line in reversed(lines):
            m = _OPTIMIZER_RE.search(line)
            if m:
                return {
                    "step": int(m.group(1)),
                    "time": m.group(2),
                    "energy": float(m.group(3)),
                    "fmax":   float(m.group(4)),
                }
    except Exception:
        pass
    return {}


# Patrón con timestamp: "|iter:   N| HH:MM:SS | energy | ..."
_SCF_TS_RE = re.compile(
    r"\|iter:\s+(\d+)\|\s+(\d{2}):(\d{2}):(\d{2})\s*\|\s*([-\d.]+)"
)


def parse_scf_log(job_dir: Path) -> dict:
    """Extrae última iteración SCF, tiempo/iter promedio y energía del r2scan.txt."""
    for name in ("r2scan.txt", "gpaw.txt"):
        txt = job_dir / name
        if not txt.exists():
            continue
        try:
            content = txt.read_text(errors="replace")
            matches = _SCF_TS_RE.findall(content)
            if not matches:
                # Fallback sin timestamp
                scf_iters = _SCF_RE.findall(content)
                n_scf = int(scf_iters[-1][0]) if scf_iters else 0
                e_match = _ENERGY_RE.search(content)
                return {"scf_iter": n_scf,
                        "energy": float(e_match.group(1)) if e_match else None}

            # Calcular t/iter desde los timestamps
            times = []
            for m in matches:
                h, mn, s = int(m[1]), int(m[2]), int(m[3])
                times.append(h * 3600 + mn * 60 + s)
            deltas = [(times[i] - times[i-1]) % 86400 for i in range(1, len(times))]
            t_iter = round(sum(deltas) / len(deltas), 1) if deltas else None

            last_iter   = int(matches[-1][0])
            last_energy = float(matches[-1][4])

            # Estimación de iteraciones restantes (típico SCF converge ~25-40 iters)
            eta_iters = max(0, 30 - last_iter)
            eta_min = round(eta_iters * t_iter / 60, 1) if t_iter else None

            return {
                "scf_iter": last_iter,
                "energy": last_energy,
                "t_iter_s": t_iter,
                "eta_min": eta_min,
            }
        except Exception:
            pass
    return {}


def is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def format_running_row(job_dir: Path, st: dict) -> str:
    formula = st.get("formula", job_dir.name[:16])[:28]
    elapsed = _fmt_elapsed(st.get("start_time", ""))
    pid     = st.get("pid", 0)
    alive   = "●" if is_pid_alive(pid) else "✗"
    cores   = st.get("mpi_cores", "?")

    relax = parse_relax_log(job_dir)
    scf   = parse_scf_log(job_dir)

    if relax:
        detail = (f"FIRE step {relax['step']:>3}  "
                  f"E={relax['energy']:>13.4f} eV  "
                  f"fmax={relax['fmax']:.4f} eV/Å")
    elif scf:
        e_str = f"{scf['energy']:.3f} eV" if scf.get("energy") else "—"
        tib   = scf.get("t_iter_s")
        eta   = scf.get("eta_min")
        timing = ""
        if tib is not None:
            timing = f"  t/iter={tib:.0f}s"
            if eta is not None:
                timing += f"  ETA~{eta:.0f}min"
        detail = f"SCF iter {scf['scf_iter']:>3}  E={e_str}{timing}"
    else:
        detail = "inicializando..."

    return (f"  {alive} {formula:<26}  {elapsed}  pid={pid:<7}  "
            f"c={cores}  {detail}")


def format_done_row(job_dir: Path, st: dict) -> str:
    formula = st.get("formula", job_dir.name[:16])[:28]
    status  = st.get("status", "?")
    elapsed = f"{st.get('elapsed_min', '?')} min" if "elapsed_min" in st else ""
    e_final = st.get("final_energy_eV")
    e_str   = f"  E={e_final:.3f} eV" if e_final is not None else ""
    icon    = "✓" if status == "converged" else "✗"
    return f"  {icon} {formula:<28}  {status:<10}  {elapsed}{e_str}"


def print_dashboard(relax_dir: Path, n_recent: int = 5) -> None:
    groups = scan_all_jobs(relax_dir)

    n_pend = len(groups.get("pending", []))
    n_run  = len(groups.get("running", []))
    n_conv = len(groups.get("converged", []))
    n_fail = len(groups.get("failed", []))
    total  = n_pend + n_run + n_conv + n_fail

    # ── Header ────────────────────────────────────────────────────────────────
    print()
    print("=" * 78)
    print(f"  BUHO Relax Monitor — {ts()}")
    print(f"  {relax_dir}")
    print("=" * 78)
    print(f"  Total: {total:>4}  |  "
          f"Pendiente: {n_pend:>4}  |  "
          f"Corriendo: {n_run:>3}  |  "
          f"Convergido: {n_conv:>4}  |  "
          f"Fallido: {n_fail:>3}")
    print()

    # ── Corriendo ─────────────────────────────────────────────────────────────
    running_dirs = groups.get("running", [])
    if running_dirs:
        print(f"── CORRIENDO ({len(running_dirs)}) " + "─" * 52)
        for d in running_dirs:
            st = read_status(d)
            print(format_running_row(d, st))
        print()

    # ── Recientes ─────────────────────────────────────────────────────────────
    done_dirs = groups.get("converged", []) + groups.get("failed", [])
    # Ordenar por finish time
    def _sort_key(d):
        st = read_status(d)
        return st.get("finished_at", "0000")
    done_dirs.sort(key=_sort_key, reverse=True)

    if done_dirs:
        print(f"── RECIENTES (últimos {min(n_recent, len(done_dirs))}) " + "─" * 48)
        for d in done_dirs[:n_recent]:
            st = read_status(d)
            print(format_done_row(d, st))
        print()

    # ── Runner log (últimas líneas) ────────────────────────────────────────────
    runner_log = relax_dir / "runner.log"
    if runner_log.exists():
        try:
            lines = runner_log.read_text(errors="replace").splitlines()
            tail = lines[-6:] if len(lines) >= 6 else lines
            print("── Runner log (últimas líneas) " + "─" * 46)
            for line in tail:
                print(f"  {line}")
        except Exception:
            pass

    print("=" * 78)


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Monitor de relajaciones BUHO")
    ap.add_argument("--relax-dir", default=str(RELAX_DIR))
    ap.add_argument("--interval",  type=int, default=30, help="Refresco en segundos")
    ap.add_argument("--recent",    type=int, default=5,  help="Últimas N terminadas")
    ap.add_argument("--once",      action="store_true",  help="Mostrar una vez y salir")
    args = ap.parse_args()

    relax_dir = Path(args.relax_dir)
    if not relax_dir.exists():
        print(f"ERROR: {relax_dir} no existe", file=sys.stderr)
        sys.exit(1)

    _stop = [False]
    signal.signal(signal.SIGINT,  lambda *_: _stop.__setitem__(0, True))
    signal.signal(signal.SIGTERM, lambda *_: _stop.__setitem__(0, True))

    while not _stop[0]:
        # Limpiar pantalla en modo continuo
        if not args.once:
            print("\033[2J\033[H", end="")  # clear screen

        print_dashboard(relax_dir, n_recent=args.recent)

        if args.once:
            break

        print(f"\n  Refresco en {args.interval}s — Ctrl+C para salir")
        sys.stdout.flush()

        # Sleep interruptible
        for _ in range(args.interval):
            if _stop[0]:
                break
            time.sleep(1)


if __name__ == "__main__":
    main()
