#!/usr/bin/env python3
"""Monitor GPAW vía /proc/PID/fd."""
from __future__ import annotations

import argparse
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


_ITER_RE  = re.compile(r"iter:\s+(\d+)\s+(\d{2}:\d{2}:\d{2})(.*)")
_DONE_RE  = re.compile(r"Timing information|Total:")
_ERROR_RE = re.compile(r"Traceback|MemoryError|Segfault|Killed", re.I)
_CONV_RE  = re.compile(r"Converged after|scf cycle converged", re.I)


# ── Helpers ──────────────────────────────────────────────────────────────────

def ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def find_gpaw_pids() -> list[int]:
    """Devuelve PIDs GPAW/python del repo."""
    try:
        out = subprocess.check_output(
            ["pgrep", "-f", "main.py.*run"], text=True, stderr=subprocess.DEVNULL
        )
        return [int(p) for p in out.split() if p.strip()]
    except Exception:
        return []


def proc_fd_files(pid: int) -> dict[int, str]:
    """Devuelve {fd."""
    fd_dir = Path(f"/proc/{pid}/fd")
    result = {}
    if not fd_dir.exists():
        return result
    for fd_path in fd_dir.iterdir():
        try:
            target = os.readlink(str(fd_path))
            if target.startswith("/") and not target.startswith("/dev") \
                    and "pipe" not in target and "socket" not in target \
                    and "anon" not in target:
                result[int(fd_path.name)] = target
        except (OSError, ValueError):
            pass
    return result


def read_fd(pid: int, fd: int) -> str | None:
    """Read entire content open fd via /proc/PID/fd/N."""
    fd_path = f"/proc/{pid}/fd/{fd}"
    try:
        with open(fd_path, "rb") as f:
            return f.read().decode("utf-8", errors="replace")
    except OSError:
        return None


def proc_status(pid: int) -> dict:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text().split()
        status_lines = Path(f"/proc/{pid}/status").read_text().splitlines()
        rss = next((int(l.split()[1]) for l in status_lines if l.startswith("VmRSS")), 0)
        cpu = int(stat[13]) + int(stat[14])
        return {"state": stat[2], "rss_mb": rss // 1024, "cpu_ticks": cpu}
    except Exception:
        return {}


# ── Per-archivo tracker ─────────────────────────────────────────────────────────

class FileTracker:
    def __init__(self, path: str, fd: int, pid: int):
        self.path = path
        self.fd   = fd
        self.pid  = pid
        self.name = Path(path).name
        self.last_content  = ""
        self.last_iter     = 0
        self.last_energy: float | None = None
        self.reset_count   = 0
        self.completed     = False

    def refresh(self, log):
        """Read via /proc/PID/fd y diff against last seen content."""
        content = read_fd(self.pid, self.fd)
        if content is None:
            log(f"[{ts()}] WARN  {self.name}: fd/{self.fd} unreadable")
            return

        # ── Detect reset (content shrank - GPAW truncated its archivo) ──────────
        if len(content) < len(self.last_content) - 256 and self.last_content:
            self.reset_count += 1
            log(
                f"[{ts()}] RESET {self.name}: file rewritten by GPAW "
                f"({len(self.last_content)}→{len(content)} bytes). "
                f"Reset #{self.reset_count}. Replaying new content↓"
            )
            self.last_content = ""

        # ── New content since last revisa ──────────────────────────────────────
        new_part = content[len(self.last_content):]

        if new_part.strip():
            # Log cada new iter línea
            for m in _ITER_RE.finditer(new_part):
                n    = int(m.group(1))
                t    = m.group(2)
                rest = m.group(3).strip()
                parts = rest.split()
                # GPAW HSE06
                # Early iters (no EXX convergencia yet) print log10-change first
                energy = None
                if parts:
                    try:
                        v = float(parts[0])
                        if v < -10.0:   # plausible DFT total energía
                            energy = v
                    except ValueError:
                        pass
                delta_e = ""
                if energy is not None and self.last_energy is not None:
                    delta_e = f"  ΔE={energy - self.last_energy:+.5f} eV"
                log(
                    f"[{ts()}] ITER  {self.name}: "
                    f"iter {n:>3}  @{t}  E={energy if energy is not None else '?':>14}{delta_e}"
                )
                self.last_iter   = n
                self.last_energy = energy

            # Convergence / done / error
            if _DONE_RE.search(new_part) and not self.completed:
                log(f"[{ts()}] DONE  {self.name}: calculation finished!")
                self.completed = True
            if _CONV_RE.search(new_part):
                log(f"[{ts()}] CONV  {self.name}: SCF converged")
            if _ERROR_RE.search(new_part):
                log(f"[{ts()}] ERROR {self.name}: error detected:\n{new_part[:400]}")
        else:
            # No new text - just reporte we're alive
            log(
                f"[{ts()}] POLL  {self.name}: "
                f"no new output since last check  "
                f"(last iter={self.last_iter}  E={self.last_energy})"
            )

        self.last_content = content


# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid",      type=int,   default=None)
    parser.add_argument("--interval", type=int,   default=120,
                        help="Poll interval in seconds (default 120)")
    parser.add_argument("--log", "-l", default="monitor.log")
    args = parser.parse_args()

    log_path = Path(args.log)

    def log(msg: str):
        print(msg, flush=True)
        with open(log_path, "a") as f:
            f.write(msg + "\n")

    _stop = [False]
    signal.signal(signal.SIGINT,  lambda *_: _stop.__setitem__(0, True))
    signal.signal(signal.SIGTERM, lambda *_: _stop.__setitem__(0, True))

    pid = args.pid
    if pid is None:
        pids = find_gpaw_pids()
        if not pids:
            print("No GPAW process found. Pass --pid explicitly.", file=sys.stderr)
            sys.exit(1)
        pid = pids[0]

    log(f"{'='*70}")
    log(f"  GPAW Monitor  {ts()}")
    log(f"  PID={pid}   interval={args.interval}s   log={log_path}")
    log(f"{'='*70}")

    # Discover salida archivos this process has open
    trackers: dict[int, FileTracker] = {}

    def refresh_fds():
        fds = proc_fd_files(pid)
        for fd, path in fds.items():
            # Only track txt/log archivos (GPAW salida)
            if path.endswith((".txt", ".log")) and fd not in trackers:
                log(f"[{ts()}] TRACK fd/{fd} → {path}")
                trackers[fd] = FileTracker(path, fd, pid)

    refresh_fds()
    prev_ticks = 0

    while not _stop[0]:
        # ── Revisa process alive ────────────────────────────────────────────
        st = proc_status(pid)
        if not st:
            log(f"[{ts()}] DEAD  PID {pid} is gone!")
            break

        # CPU activity (ticks since last poll)
        ticks_now = st.get("cpu_ticks", 0)
        ticks_delta = ticks_now - prev_ticks if prev_ticks else 0
        prev_ticks = ticks_now

        log(
            f"[{ts()}] ALIVE PID={pid}  state={st['state']}  "
            f"RSS={st['rss_mb']} MB  Δcpu={ticks_delta} ticks/{args.interval}s"
        )

        # ── Read each tracked fd directly ─────────────────────────────────────
        for tracker in list(trackers.values()):
            tracker.refresh(log)

        # ── Revisa para new fds opened since last time ──────────────────────────
        refresh_fds()

        time.sleep(args.interval)

    log(f"[{ts()}] Monitor stopped.")


if __name__ == "__main__":
    main()
