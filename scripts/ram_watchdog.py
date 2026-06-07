#!/usr/bin/env python3
"""Guardián de RAM — mata el job MPI más grande si RAM > límite o swap > umbral.

Dos niveles de alerta:
  1. RAM usada > --limit (61 GB): mata el job más pesado + baja slots
  2. Swap usado > --swap-limit (2 GB): RAM ya se llenó antes que el watchdog
     actuara → baja slots inmediatamente (el swap es señal de crash inminente)

Con vm.swappiness=1 el kernel solo toca swap cuando RAM está al borde:
  swap > 2 GB = señal de que un job superó el límite y el kernel empezó a desalojar.

Uso:
    python scripts/ram_watchdog.py
    python scripts/ram_watchdog.py --limit 61 --swap-limit 2 --poll 15
"""
import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT = Path('/home/luis-ochoa/Documents/Vscode/py/dft')
RUNS_ROOT = Path(os.environ.get('DFT_RUNS_ROOT', '/media/luis-ochoa/Nuevo vol/dft/runs'))
RELAX_DIR = Path(os.environ.get('DFT_RELAX_DIR', str(RUNS_ROOT / 'relax_basic')))


def ts():
    return datetime.now().strftime('%H:%M:%S')


def mem_used_gb():
    info = open('/proc/meminfo').read()
    total = int(re.search(r'MemTotal:\s+(\d+)', info).group(1))
    avail = int(re.search(r'MemAvailable:\s+(\d+)', info).group(1))
    return (total - avail) / 1024 / 1024


def mem_avail_gb():
    info = open('/proc/meminfo').read()
    avail = int(re.search(r'MemAvailable:\s+(\d+)', info).group(1))
    return avail / 1024 / 1024


def swap_used_gb():
    info = open('/proc/meminfo').read()
    total = int(re.search(r'SwapTotal:\s+(\d+)', info).group(1))
    free  = int(re.search(r'SwapFree:\s+(\d+)',  info).group(1))
    return (total - free) / 1024 / 1024


def get_mpi_jobs():
    """Devuelve lista de (pid, rss_mb, job_dir) de procesos mpirun activos."""
    try:
        pids = subprocess.run(['pgrep', '-f', 'mpi(exec|run).*input.py'],
                              capture_output=True, text=True).stdout.strip().split()
    except Exception:
        return []

    jobs = []
    for pid in pids:
        if not pid:
            continue
        try:
            # Memoria total del grupo de procesos (mpirun + workers)
            pgid = os.getpgid(int(pid))
            # Suma RSS de todos los procesos del grupo
            group_rss = 0
            for p in Path('/proc').iterdir():
                if not p.name.isdigit():
                    continue
                try:
                    ppgid = int((p / 'status').read_text().split('Tgid:')[0].split()[-1])
                except Exception:
                    continue
                if os.getpgid(int(p.name)) == pgid:
                    try:
                        rss = int((p / 'status').read_text().split('VmRSS:')[1].split()[0])
                        group_rss += rss
                    except Exception:
                        pass

            # Buscar el directorio del job
            cwd = Path(f'/proc/{pid}/cwd').resolve()
            jobs.append((int(pid), group_rss // 1024, cwd))
        except Exception:
            pass

    return sorted(jobs, key=lambda x: -x[1])  # mayor RAM primero


def kill_largest_job(jobs, log):
    if not jobs:
        log('WARN  No hay jobs MPI para matar.')
        return

    pid, rss_mb, cwd = jobs[0]
    log(f'KILL  Matando job más grande: pid={pid}  RSS={rss_mb} MB  dir={cwd.name}')

    try:
        pgid = os.getpgid(pid)
        os.killpg(pgid, signal.SIGTERM)
        time.sleep(3)
        os.killpg(pgid, signal.SIGKILL)
    except Exception as e:
        log(f'KILL  Error: {e}')

    # Marcar job como pending (no failed — OOM no es culpa del cálculo)
    status_file = cwd / 'status.json'
    if status_file.exists():
        try:
            s = json.loads(status_file.read_text())
            s['status'] = 'pending'
            s['oom_killed'] = True
            for k in ('pid','start_time','mpi_cores','returncode','elapsed_min','finished_at'):
                s.pop(k, None)
            status_file.write_text(json.dumps(s, indent=2))
        except Exception:
            pass


def downgrade_runner(log, relax_dir=RELAX_DIR, fallback_slots=2, fallback_cores=8):
    """Mata el runner actual y lo relanza con menos slots."""
    runner_pids = subprocess.run(['pgrep', '-f', 'buho_relax_runner'],
                                 capture_output=True, text=True).stdout.strip().split()
    for rpid in runner_pids:
        if rpid:
            try:
                os.kill(int(rpid), signal.SIGTERM)
                log(f'RUNNER  Detenido runner pid={rpid}')
            except Exception:
                pass
    time.sleep(3)

    project = PROJECT
    python  = str(project / '.venv' / 'bin' / 'python3')
    script  = str(project / 'scripts' / 'buho_relax_runner.py')
    relax   = str(relax_dir)
    log_f   = str(Path(relax) / 'runner.log')

    cmd = [
        python, script,
        '--slots', str(fallback_slots),
        '--cores', str(fallback_cores),
        '--poll', '60',
        '--relax-dir', relax,
    ]

    env = os.environ.copy()
    env['PYTHONPATH'] = str(project / 'src')

    with open(log_f, 'a') as lf:
        proc = subprocess.Popen(cmd, env=env, stdout=lf, stderr=lf,
                                start_new_session=True)
    log(f'RUNNER  Relanzado con {fallback_slots} slots × {fallback_cores} cores  pid={proc.pid}')


def main():
    ap = argparse.ArgumentParser(description='RAM watchdog para jobs GPAW')
    ap.add_argument('--limit',          type=float, default=61.0,
                    help='Límite de RAM usada en GB antes de matar job (default: 61)')
    ap.add_argument('--swap-limit',     type=float, default=2.0,
                    help='Límite de swap usado en GB — señal de crash inminente (default: 2)')
    ap.add_argument('--poll',           type=int,   default=15,
                    help='Intervalo de polling en segundos (default: 15)')
    ap.add_argument('--fallback-slots', type=int,   default=2,
                    help='Slots tras OOM (default: 2)')
    ap.add_argument('--fallback-cores', type=int,   default=8,
                    help='Cores/slot tras OOM (default: 8)')
    ap.add_argument('--relax-dir', default=str(RELAX_DIR),
                    help='Directorio de jobs a relanzar tras OOM')
    args = ap.parse_args()

    relax_dir = Path(args.relax_dir)
    log_path = relax_dir / 'watchdog.log'

    def log(msg):
        line = f'[{ts()}] {msg}'
        print(line, flush=True)
        try:
            with open(log_path, 'a') as f:
                f.write(line + '\n')
        except Exception:
            pass

    _stop = [False]
    signal.signal(signal.SIGINT,  lambda *_: _stop.__setitem__(0, True))
    signal.signal(signal.SIGTERM, lambda *_: _stop.__setitem__(0, True))

    log(f'Watchdog iniciado — RAM límite={args.limit} GB  swap límite={args.swap_limit} GB  poll={args.poll}s')
    log(f'Fallback: {args.fallback_slots} slots × {args.fallback_cores} cores')

    while not _stop[0]:
        used  = mem_used_gb()
        avail = mem_avail_gb()
        swap  = swap_used_gb()

        ram_critical  = used >= args.limit
        swap_active   = swap >= args.swap_limit

        if swap_active:
            # Swap en uso = RAM se llenó, el kernel está desalojando páginas
            # Bajar slots inmediatamente sin esperar que la RAM explote
            log(f'🔴 SWAP activo={swap:.2f} GB ≥ {args.swap_limit} GB — RAM desbordada')
            log(f'   RAM usada={used:.1f} GB  disponible={avail:.1f} GB')
            jobs = get_mpi_jobs()
            if jobs:
                for j in jobs[:3]:
                    log(f'     pid={j[0]}  RSS={j[1]} MB  {j[2].name}')
            kill_largest_job(jobs, log)
            log(f'DOWNGRADE  Swap disparó la alarma → reduciendo a {args.fallback_slots} slots × {args.fallback_cores} cores')
            downgrade_runner(log, relax_dir, args.fallback_slots, args.fallback_cores)

        elif ram_critical:
            log(f'⚠️  RAM usada={used:.1f} GB ≥ {args.limit} GB — matando job más grande')
            jobs = get_mpi_jobs()
            if jobs:
                for j in jobs[:3]:
                    log(f'     pid={j[0]}  RSS={j[1]} MB  {j[2].name}')
            kill_largest_job(jobs, log)
            log(f'DOWNGRADE  RAM disparó la alarma → reduciendo a {args.fallback_slots} slots × {args.fallback_cores} cores')
            downgrade_runner(log, relax_dir, args.fallback_slots, args.fallback_cores)

        else:
            log(f'OK   RAM={used:.1f} GB  swap={swap:.2f} GB  libre={avail:.1f} GB')

        time.sleep(args.poll)

    log('Watchdog detenido.')


if __name__ == '__main__':
    main()
