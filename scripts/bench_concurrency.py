#!/usr/bin/env python3
"""Benchmark de concurrencia: mide t/iter con N slots simultáneos.

Para cada N en [1,2,4]: lanza N jobs idénticos (OMP pinned a 1 thread),
espera a que lleguen a 20 iteraciones SCF, calcula t/iter (promedio de las
iters 6-20, descartando warmup), y reporta throughput = N / t_iter.

Uso: python scripts/bench_concurrency.py
"""
import json, os, re, signal, subprocess, sys, time
from datetime import datetime
from pathlib import Path

ROOT = Path("/home/luis-ochoa/Documents/Vscode/py/dft")
PY = str(ROOT / ".venv/bin/python3")
RELAX = ROOT / "runs/relax_basic"
TARGET_ITERS = 20
CONFIGS = [1, 2, 4]


def pick_test_jobs(n):
    """Devuelve n dirs de jobs pending Pb-estables (sin Ge/Sn que crashean)."""
    pend = []
    for d in sorted(RELAX.iterdir()):
        if not d.is_dir():
            continue
        try:
            s = json.loads((d / "status.json").read_text())
        except Exception:
            continue
        f = s.get("formula", "")
        # Solo Pb puro en B-site (Ge/Sn dan AssertionError intermitente en MGGA/eigensolver)
        if s.get("status") == "pending" and "Pb" in f and "Ge" not in f and "Sn" not in f:
            pend.append(d)
        if len(pend) >= n:
            break
    return pend[:n]


def clean(d):
    for f in ("r2scan.txt", "relax.log", "relax.traj", "relaxed.cif",
              "error.txt", "run.log", "bench.log"):
        (d / f).unlink(missing_ok=True)


def n_iters(d):
    txt = d / "r2scan.txt"
    if not txt.exists():
        return 0
    return txt.read_text(errors="replace").count("iter:")


def t_per_iter(d, skip=5):
    """t/iter promedio descartando las primeras `skip` iters (warmup)."""
    txt = d / "r2scan.txt"
    if not txt.exists():
        return None
    its = re.findall(r"\|iter:\s+(\d+)\|\s+(\d{2}):(\d{2}):(\d{2})",
                     txt.read_text(errors="replace"))
    if len(its) < skip + 2:
        return None
    t = [int(h) * 3600 + int(m) * 60 + int(s) for _, h, m, s in its]
    dt = [(t[i] - t[i - 1]) % 86400 for i in range(1, len(t))]
    steady = dt[skip:]   # descarta warmup
    return sum(steady) / len(steady) if steady else None


def launch(d):
    env = os.environ.copy()
    env["OMP_NUM_THREADS"] = "1"
    env["OPENBLAS_NUM_THREADS"] = "1"
    env["MKL_NUM_THREADS"] = "1"
    log = open(d / "bench.log", "w")
    return subprocess.Popen(
        ["mpirun", "-n", "1", PY, "input.py"],
        cwd=str(d), stdout=log, stderr=log, env=env,
        start_new_session=True,
    )


def kill_proc(p):
    try:
        os.killpg(os.getpgid(p.pid), signal.SIGKILL)
    except Exception:
        try:
            p.kill()
        except Exception:
            pass


def run_config(n, timeout_s=2400):
    print(f"\n{'='*60}")
    print(f"CONFIG: {n} slot(s) concurrente(s)  —  {datetime.now():%H:%M:%S}")
    print(f"{'='*60}")
    jobs = pick_test_jobs(n)
    if len(jobs) < n:
        print(f"  ✗ solo {len(jobs)} jobs pending disponibles")
        return None
    for d in jobs:
        clean(d)
    procs = [launch(d) for d in jobs]
    print(f"  lanzados {n} jobs: {[d.name[:8] for d in jobs]}")

    t0 = time.time()
    # Esperar a que TODOS los VIVOS lleguen a TARGET_ITERS o timeout.
    # No cortamos si uno crashea — seguimos midiendo los demás.
    while time.time() - t0 < timeout_s:
        iters = [n_iters(d) for d in jobs]
        alive = [p.poll() is None for p in procs]
        # vivos que aún no llegan a target
        pending_alive = [it for it, al in zip(iters, alive) if al and it < TARGET_ITERS]
        if not pending_alive:   # todos los vivos llegaron (o murieron)
            break
        time.sleep(15)

    iters = [n_iters(d) for d in jobs]
    dead = [i for i, p in enumerate(procs) if p.poll() is not None and iters[i] < TARGET_ITERS]
    if dead:
        print(f"  ⚠️ {len(dead)} job(s) crashearon antes de 20 iters (excluidos del promedio)")
    tpis = [t_per_iter(d) for d in jobs]
    tpis_valid = [t for t in tpis if t]
    for d, it, tp in zip(jobs, iters, tpis):
        print(f"    {d.name[:12]}  iters={it:<3} t/iter={tp:.0f}s" if tp
              else f"    {d.name[:12]}  iters={it:<3} t/iter=?")
    for p in procs:
        kill_proc(p)
    for d in jobs:  # reset a pending
        clean(d)
        s = json.loads((d / "status.json").read_text())
        (d / "status.json").write_text(json.dumps(
            {"status": "pending", "candidate_id": d.name,
             "formula": s.get("formula", "?")}, indent=2))
    time.sleep(5)

    if not tpis_valid:
        return None
    avg_tpi = sum(tpis_valid) / len(tpis_valid)
    # throughput real = suma de (1/t_iter) sobre los jobs que SÍ corrieron
    throughput = sum(1.0 / t for t in tpis_valid)
    return {"n": n, "n_valid": len(tpis_valid),
            "avg_t_iter_s": round(avg_tpi, 1),
            "throughput_ji_s": round(throughput, 4),
            "per_job": [round(t, 1) for t in tpis_valid]}


def main():
    results = []
    for n in CONFIGS:
        r = run_config(n)
        if r:
            results.append(r)
            print(f"  → {n} slots: t/iter={r['avg_t_iter_s']}s  "
                  f"throughput={r['throughput_ji_s']} jobs·iter/s")

    print(f"\n{'='*60}")
    print("RESUMEN")
    print(f"{'='*60}")
    print(f"{'slots':>6} {'t/iter(s)':>10} {'throughput':>12} {'vs_1slot':>9}")
    base = results[0]["throughput_ji_s"] if results else 1
    for r in results:
        rel = r["throughput_ji_s"] / base
        print(f"{r['n']:>6} {r['avg_t_iter_s']:>10} "
              f"{r['throughput_ji_s']:>12} {rel:>8.2f}x")
    if results:
        best = max(results, key=lambda r: r["throughput_ji_s"])
        print(f"\nÓPTIMO: {best['n']} slots "
              f"(throughput {best['throughput_ji_s']} jobs·iter/s)")
    Path(ROOT / "reports/concurrency_benchmark.json").write_text(
        json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
