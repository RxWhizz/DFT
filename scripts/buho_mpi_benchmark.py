#!/usr/bin/env python3
"""Benchmark de scaling MPI para relajaciones BUHO r2SCAN.

Corre 5 jobs representativos con 5 configuraciones MPI y mide:
  - Tiempo de inicialización GPAW
  - Tiempo por iteración SCF
  - Número de iteraciones hasta convergencia
  - RAM pico por configuración

Configuraciones:
  A: 1 slot  × 44 cores
  B: 2 slots × 16 cores
  C: 3 slots ×  4 cores
  D: 4 slots ×  4 cores
  E: 3 slots ×  8 cores  ← baseline post-fix

Uso:
  python scripts/buho_mpi_benchmark.py
  python scripts/buho_mpi_benchmark.py --timeout 30 --config E
  python scripts/buho_mpi_benchmark.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT    = Path(__file__).resolve().parent.parent
PYTHON  = str(ROOT / '.venv' / 'bin' / 'python3')
RELAX   = ROOT / 'runs' / 'relax_basic'
BENCH   = ROOT / 'runs' / 'mpi_benchmark'
REPORTS = ROOT / 'reports'

CONFIGS = {
    'A': {'slots': 1, 'cores': 44, 'label': '1×44'},
    'B': {'slots': 2, 'cores': 16, 'label': '2×16'},
    'C': {'slots': 3, 'cores':  4, 'label': '3×4'},
    'D': {'slots': 4, 'cores':  4, 'label': '4×4'},
    'E': {'slots': 3, 'cores':  8, 'label': '3×8 (baseline)'},
}

# Jobs representativos: (candidate_id, descripcion, tipo)
# Se seleccionan buscando en runs/relax_basic/ por fórmula
BENCHMARK_TARGETS = [
    ('pure_Pb',    lambda f: 'Pb' in f and 'Sn' not in f and 'Ge' not in f
                              and len(f) < 10),  # CsPbI3, CsPbBr3...
    ('pure_Sn',    lambda f: 'Sn' in f and 'Pb' not in f and len(f) < 10),
    ('super_Pb',   lambda f: 'Pb' in f and ('Br' in f or 'Cl' in f)
                              and 'FA' in f and 'Sn' not in f),  # 40-atom mixto Pb
    ('super_Sn',   lambda f: 'Sn' in f and 'FA' in f and 'Pb' not in f),  # 40-atom mixto Sn
    ('super_mixed_A', lambda f: ('FA' in f or 'MA' in f) and 'K' in f),    # A-site mixto
]

N_BENCH_JOBS = 1  # jobs por tipo (1 = rápido, 2 = promedia ruido)


def is_supported_kpt_only_layout(job_type: str, n_cores: int) -> bool:
    """GPAW master solo está estable aquí con kpt-only: domain=band=1."""
    if job_type.startswith('super_'):
        return False
    cap = 4 if job_type.startswith('super_') else 8
    return 1 <= n_cores <= cap and 8 % n_cores == 0


def unsupported_layout_reason(job_type: str, n_cores: int) -> str:
    if job_type.startswith('super_'):
        return (
            f"SKIP: {job_type} diferido; superceldas 40 atomos no inicializan "
            "dentro del presupuesto benchmark con 2x2x2/450 eV"
        )
    cap = 4 if job_type.startswith('super_') else 8
    return (
        f"SKIP: {n_cores} ranks requiere domain/band; "
        f"{job_type} soporta kpt-only <= {cap} ranks"
    )


def find_benchmark_jobs() -> dict[str, list[Path]]:
    """Encuentra jobs representativos en runs/relax_basic/."""
    import yaml
    sys.path.insert(0, str(ROOT / 'src'))
    from buho.generator.heuristic_generator import HeuristicGenerator
    all_cands = {c.candidate_id: c for c in
                 HeuristicGenerator.load_jsonl(str(ROOT / 'data' / 'raw' / 'generated_candidates.jsonl'))}

    selected: dict[str, list[Path]] = {name: [] for name, _ in BENCHMARK_TARGETS}

    for job_dir in sorted(RELAX.iterdir()):
        if not job_dir.is_dir(): continue
        cid = job_dir.name
        c = all_cands.get(cid)
        if c is None: continue
        formula = c.formula
        for name, pred in BENCHMARK_TARGETS:
            if len(selected[name]) < N_BENCH_JOBS and pred(formula):
                selected[name].append(job_dir)
                break

    return selected


def prepare_bench_job(src_job: Path, n_cores: int, bench_dir: Path) -> Path:
    """Copia job a directorio de benchmark y regenera input.py con n_cores."""
    import yaml
    sys.path.insert(0, str(ROOT / 'src'))

    bench_dir.mkdir(parents=True, exist_ok=True)
    # Copiar estructura
    for f in ('structure.cif', 'POSCAR', 'metadata.json'):
        if (src_job / f).exists():
            shutil.copy2(src_job / f, bench_dir / f)

    # Regenerar input.py con n_cores correcto
    from buho.generator.heuristic_generator import HeuristicGenerator
    from buho.dft_jobs.prepare_relaxation_jobs import RelaxationJobPreparer
    from ase.io import read as ase_read

    with open(ROOT / 'config' / 'generator.yaml') as f:
        cfg = yaml.safe_load(f)

    all_cands = {c.candidate_id: c for c in
                 HeuristicGenerator.load_jsonl(str(ROOT / 'data' / 'raw' / 'generated_candidates.jsonl'))}
    c = all_cands[src_job.name]
    atoms = ase_read(str(bench_dir / 'structure.cif'))
    prep = RelaxationJobPreparer(cfg, project_root=ROOT, n_cores=n_cores, python=PYTHON)
    prep._write_input(bench_dir, c, atoms)

    # status.json
    (bench_dir / 'status.json').write_text(json.dumps({
        'status': 'pending',
        'candidate_id': c.candidate_id,
        'formula': c.formula,
    }, indent=2))
    return bench_dir


def parse_r2scan(txt: Path) -> dict:
    """Extrae métricas de timing del archivo de salida GPAW."""
    if not txt.exists():
        return {}

    content = txt.read_text(errors='replace')
    result = {}

    # Tiempo de inicialización: línea "Initialization done in: X s"
    m = re.search(r'Initialization done in:\s+([\d.]+)', content)
    if m:
        result['t_init_s'] = float(m.group(1))

    # Iteraciones SCF con timestamp
    iter_times = []
    prev_time  = None
    for line in content.splitlines():
        m = re.match(r'\s*\|iter:\s+(\d+)\|\s+(\d{2}):(\d{2}):(\d{2})\s*\|\s*([-\d.]+)', line)
        if m:
            n    = int(m.group(1))
            h, mn, s = int(m.group(2)), int(m.group(3)), int(m.group(4))
            t_abs = h * 3600 + mn * 60 + s
            energy = float(m.group(5))
            if prev_time is not None:
                dt = (t_abs - prev_time) % 86400
                iter_times.append(dt)
            prev_time = t_abs
            result['last_iter'] = n
            result['last_energy'] = energy

    if iter_times:
        result['t_iter_avg_s'] = round(sum(iter_times) / len(iter_times), 1)
        result['t_iter_min_s'] = min(iter_times)
        result['t_iter_max_s'] = max(iter_times)
        result['n_scf_iters']  = len(iter_times) + 1

    # Convergencia
    result['scf_converged'] = 'SCF Converged' in content or 'Converged' in content

    # Max RSS
    m = re.search(r'Max RSS:\s+([\d.]+)', content)
    if m:
        result['max_rss_mib'] = float(m.group(1))

    return result


def run_job(bench_dir: Path, n_cores: int, timeout_min: int) -> dict:
    """Ejecuta un job con mpirun y extrae métricas."""
    cmd = ['mpirun', '-n', str(n_cores), PYTHON, 'input.py']
    t0  = time.time()

    proc = subprocess.Popen(
        cmd,
        cwd=str(bench_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    timed_out = False
    try:
        _stdout, stderr = proc.communicate(timeout=timeout_min * 60)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            _stdout, stderr = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            _stdout, stderr = proc.communicate()

    elapsed = time.time() - t0
    (bench_dir / 'stdout.txt').write_text(_stdout or '')
    (bench_dir / 'stderr.txt').write_text(stderr or '')

    metrics = parse_r2scan(bench_dir / 'r2scan.txt')
    metrics['t_total_s']     = round(elapsed, 1)
    metrics['t_total_min']   = round(elapsed / 60, 1)
    metrics['returncode']    = proc.returncode
    metrics['job_converged'] = proc.returncode == 0 and not timed_out

    if timed_out:
        metrics['timeout'] = True

    if proc.returncode != 0 or timed_out:
        stderr_tail = stderr[-500:] if stderr else ''
        metrics['error'] = stderr_tail

    return metrics


def ram_snapshot_gb() -> float:
    info = open('/proc/meminfo').read()
    total = int(re.search(r'MemTotal:\s+(\d+)', info).group(1))
    avail = int(re.search(r'MemAvailable:\s+(\d+)', info).group(1))
    return (total - avail) / 1024 / 1024


def main():
    ap = argparse.ArgumentParser(description='BUHO MPI scaling benchmark')
    ap.add_argument('--timeout', type=int, default=30,
                    help='Timeout por job en minutos (default: 30)')
    ap.add_argument('--config',  default='all',
                    help='Config a probar: A,B,C,D,E o "all" (default: all)')
    ap.add_argument('--dry-run', action='store_true',
                    help='Solo muestra qué jobs se usarían')
    ap.add_argument('--watchdog', action='store_true', default=True,
                    help='Activa watchdog RAM durante benchmark')
    args = ap.parse_args()

    BENCH.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)

    # Seleccionar configs a probar
    configs_to_run = (CONFIGS if args.config == 'all'
                      else {k: CONFIGS[k] for k in args.config.split(',') if k in CONFIGS})

    cfg_desc = ', '.join(f"{k}({v['label']})" for k, v in configs_to_run.items())
    print(f"{'='*70}")
    print(f"BUHO MPI Benchmark — {datetime.now():%Y-%m-%d %H:%M}")
    print(f"Configs: {cfg_desc}")
    print(f"Timeout: {args.timeout} min/job")
    print(f"{'='*70}\n")

    # Encontrar jobs
    bench_jobs = find_benchmark_jobs()
    total_jobs = sum(len(v) for v in bench_jobs.values())
    print(f"Jobs encontrados:")
    for typ, jobs in bench_jobs.items():
        for j in jobs:
            cid  = j.name
            import yaml; sys.path.insert(0, str(ROOT/'src'))
            from buho.generator.heuristic_generator import HeuristicGenerator
            all_c = {c.candidate_id: c for c in HeuristicGenerator.load_jsonl(
                str(ROOT/'data'/'raw'/'generated_candidates.jsonl'))}
            formula = all_c.get(cid, type('',(),{'formula': cid})()).formula
            print(f"  [{typ:20s}]  {formula}")

    if args.dry_run:
        print('\nDry-run: no se ejecuta nada.')
        return

    # Watchdog RAM en background
    watchdog_pid = None
    if args.watchdog:
        wdog = subprocess.Popen(
            [PYTHON, str(ROOT/'scripts'/'ram_watchdog.py'),
             '--limit', '61', '--swap-limit', '2', '--poll', '10',
             '--fallback-slots', '2', '--fallback-cores', '8'],
            stdout=open(RELAX/'watchdog.log','a'),
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        watchdog_pid = wdog.pid
        print(f"\nWatchdog PID: {watchdog_pid}")

    results = []

    try:
        for cfg_key, cfg in configs_to_run.items():
            n_cores = cfg['cores']
            label   = cfg['label']
            print(f"\n{'─'*70}")
            print(f"CONFIG {cfg_key}: {label}  ({cfg['slots']} slots × {n_cores} cores)")
            print(f"{'─'*70}")

            for typ, jobs in bench_jobs.items():
                for src_job in jobs:
                    from buho.generator.heuristic_generator import HeuristicGenerator
                    all_c = {c.candidate_id: c for c in HeuristicGenerator.load_jsonl(
                        str(ROOT/'data'/'raw'/'generated_candidates.jsonl'))}
                    c = all_c.get(src_job.name)
                    formula = c.formula if c else src_job.name

                    bench_subdir = BENCH / f"cfg_{cfg_key}" / src_job.name
                    bench_subdir.mkdir(parents=True, exist_ok=True)

                    # Limpiar run anterior si existe
                    for f in ('r2scan.txt','relax.log','relax.traj','relaxed.cif',
                              'relaxed.gpw','error.txt','stdout.txt','stderr.txt'):
                        (bench_subdir / f).unlink(missing_ok=True)

                    print(f"\n  [{typ}] {formula}  ({n_cores} cores)  ", end='', flush=True)

                    if not is_supported_kpt_only_layout(typ, n_cores):
                        reason = unsupported_layout_reason(typ, n_cores)
                        metrics = {
                            'skipped': True,
                            'skip_reason': reason,
                            'job_converged': False,
                        }
                        print(reason)
                        results.append({
                            'config': cfg_key,
                            'label':  label,
                            'n_cores': n_cores,
                            'n_slots': cfg['slots'],
                            'job_type': typ,
                            'formula': formula,
                            'candidate_id': src_job.name,
                            **metrics,
                        })
                        (REPORTS / 'mpi_benchmark.json').write_text(json.dumps(results, indent=2))
                        continue

                    prepare_bench_job(src_job, n_cores, bench_subdir)
                    ram_before = ram_snapshot_gb()

                    try:
                        metrics = run_job(bench_subdir, n_cores, args.timeout)
                    except subprocess.TimeoutExpired:
                        metrics = {'timeout': True, 't_total_min': args.timeout,
                                   'job_converged': False}
                        print(f"TIMEOUT ({args.timeout}min)")
                    except Exception as e:
                        metrics = {'error': str(e), 'job_converged': False}
                        print(f"ERROR: {e}")
                    else:
                        status = 'OK' if metrics.get('job_converged') else 'FAIL'
                        t_init = metrics.get('t_init_s', '?')
                        t_iter = metrics.get('t_iter_avg_s', '?')
                        n_iter = metrics.get('n_scf_iters', '?')
                        t_tot  = metrics.get('t_total_min', '?')
                        print(f"{status}  t_init={t_init}s  t_iter={t_iter}s  "
                              f"n_iter={n_iter}  total={t_tot}min")

                    metrics['ram_before_gb'] = round(ram_before, 1)
                    metrics['ram_after_gb']  = round(ram_snapshot_gb(), 1)

                    results.append({
                        'config': cfg_key,
                        'label':  label,
                        'n_cores': n_cores,
                        'n_slots': cfg['slots'],
                        'job_type': typ,
                        'formula': formula,
                        'candidate_id': src_job.name,
                        **metrics,
                    })

                    # Guardado incremental — sobrevive interrupciones
                    (REPORTS / 'mpi_benchmark.json').write_text(json.dumps(results, indent=2))

    finally:
        if watchdog_pid:
            try: os.kill(watchdog_pid, 9)
            except: pass

    # Guardar resultados
    out_json = REPORTS / 'mpi_benchmark.json'
    out_json.write_text(json.dumps(results, indent=2))

    # Tabla resumen en Markdown
    _write_report(results)
    print(f"\n\nResultados guardados en {out_json}")
    print(f"Reporte en {REPORTS / 'mpi_benchmark.md'}")

    # Imprimir tabla resumen
    _print_summary(results)


def _print_summary(results: list[dict]):
    print(f"\n{'='*80}")
    print("RESUMEN — tiempo por iteración SCF (segundos, promedio por config)")
    print(f"{'Config':<10} {'Cores':>6} {'Init(s)':>8} {'t/iter(s)':>10} {'N_iters':>8} {'Total(min)':>11}")
    print('-' * 58)

    from collections import defaultdict
    by_config: dict = defaultdict(list)
    for r in results:
        if r.get('t_iter_avg_s'):
            by_config[r['config']].append(r)

    for cfg_key in sorted(by_config):
        rows = by_config[cfg_key]
        n_cores   = rows[0].get('n_cores', '?')
        t_init    = [r.get('t_init_s', 0) for r in rows if r.get('t_init_s')]
        t_iter    = [r.get('t_iter_avg_s', 0) for r in rows if r.get('t_iter_avg_s')]
        n_iters   = [r.get('n_scf_iters', 0) for r in rows if r.get('n_scf_iters')]
        t_total   = [r.get('t_total_min', 0) for r in rows if r.get('t_total_min')]
        label     = CONFIGS.get(cfg_key, {}).get('label', cfg_key)

        def avg(lst): return round(sum(lst)/len(lst), 1) if lst else '—'
        print(f"{label:<10} {n_cores:>6} {avg(t_init):>8} {avg(t_iter):>10} "
              f"{avg(n_iters):>8} {avg(t_total):>11}")
    print(f"{'='*80}")


def _write_report(results: list[dict]):
    lines = [
        '# BUHO MPI Benchmark Report',
        f'Generated: {datetime.now():%Y-%m-%d %H:%M}',
        '',
        '## Results by Configuration',
        '',
        '| Config | Cores | Job Type | Formula | t_init(s) | t/iter(s) | N_iters | Total(min) | Status |',
        '|--------|-------|----------|---------|-----------|-----------|---------|------------|--------|',
    ]
    for r in results:
        status = 'skip' if r.get('skipped') else ('✓' if r.get('job_converged') else '✗')
        lines.append(
            f"| {r.get('label','?')} | {r.get('n_cores','?')} | {r.get('job_type','?')} "
            f"| {r.get('formula','?')[:25]} | {r.get('t_init_s','—')} "
            f"| {r.get('t_iter_avg_s','—')} | {r.get('n_scf_iters','—')} "
            f"| {r.get('t_total_min','—')} | {status} |"
        )
    (REPORTS / 'mpi_benchmark.md').write_text('\n'.join(lines))


if __name__ == '__main__':
    main()
