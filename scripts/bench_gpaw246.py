#!/usr/bin/env python3
"""Benchmark de paralelización en GPAW 24.6.0 (conda env gpaw246) vs master.

Responde, sobre un build estable conocido-bueno:
  (1) ¿`domain>1` funciona con PBE single-point en supercelda? (master crashea)
  (2) ESCALADO DE CONCURRENCIA: 1/2/4 jobs concurrentes a 1 core → throughput.
      Discrimina la hipótesis: si 2 slots → ~1.8× era un BUG de master; si
      sigue ~1.13× es ancho de banda real. (master: 2 slots = 1.13×)
  (3) t/iter a 1 core vs master (~27s/iter).

Corre TODO con el env conda (mpich propio) vía `conda run -n gpaw246`.
NO usa el venv ni src/ del proyecto — input standalone.

Uso: .venv/bin/python3 scripts/bench_gpaw246.py
"""
import json, os, re, shutil, subprocess, time
from pathlib import Path

ROOT = Path("/home/luis-ochoa/Documents/Vscode/py/dft")
CONDA = str(Path.home() / "miniforge3/bin/conda")
ENV = "gpaw246"
RELAX = ROOT / "runs/relax_basic"
SUPER_JOB = "0143dc601867b0c0"   # CsPbBr0.75Cl0.25, 40 átomos, Γ-only
BENCH_ROOT = ROOT / "runs/_bench246"
MAXITER = 12   # mide t/iter sin esperar convergencia completa

_INP = '''\
import time, json
from ase.io import read
from gpaw import GPAW, PW, FermiDirac
from gpaw.mixer import Mixer
from gpaw.mpi import world
t0 = time.time()
atoms = read("structure.cif")
_parallel = {parallel}
calc = GPAW(mode=PW(300), xc="PBE", kpts={{"size":[1,1,1],"gamma":True}},
            occupations=FermiDirac(0.05),
            convergence={{"density":1e-3,"eigenstates":1e-4,"energy":1e-4}},
            mixer=Mixer(0.1, 8, 50),
            parallel=_parallel if _parallel else None,
            maxiter={maxiter}, txt="scf.txt")
atoms.calc = calc
try:
    e = float(atoms.get_potential_energy()); ok = True; err = ""
except Exception as exc:
    e = None; ok = False; err = repr(exc)[:300]
t1 = time.time()
if world.rank == 0:
    json.dump({{"energy": e, "ok": ok, "err": err, "wall_s": round(t1-t0,1)}}, open("res.json","w"))
'''


def make_dir(name, parallel):
    d = BENCH_ROOT / name
    d.mkdir(parents=True, exist_ok=True)
    shutil.copy2(RELAX / SUPER_JOB / "structure.cif", d / "structure.cif")
    (d / "input.py").write_text(_INP.format(parallel=repr(parallel), maxiter=MAXITER))
    return d


def parse(d):
    txt = (d / "scf.txt").read_text(errors="replace") if (d / "scf.txt").exists() else ""
    # GPAW 24.6: "iter:   1 19:10:53"; master: "|iter:   1| 19:10:53 |" → pipe opcional
    its = re.findall(r"iter:\s*(\d+)\s*\|?\s*(\d{1,2}):(\d{2}):(\d{2})", txt)
    n = len(its)
    t_iter = None
    if n > 5:
        t = [int(h)*3600+int(m)*60+int(s) for _, h, m, s in its]
        dt = [(t[i]-t[i-1]) % 86400 for i in range(1, len(t))][3:]
        t_iter = round(sum(dt)/len(dt), 1) if dt else None
    rj = {}
    if (d / "res.json").exists():
        try: rj = json.loads((d / "res.json").read_text())
        except Exception: pass
    return n, t_iter, rj


# Mismos datasets PAW que usa master (venv) → energías comparables apples-to-apples
SETUP_PATH = str(ROOT / ".venv/lib/python3.12/site-packages/gpaw_data/setups")


def popen(d, ncores):
    env = os.environ.copy()
    for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        env[k] = "1"
    # El activate.d del env sobreescribe GPAW_SETUP_PATH → exportar DENTRO de
    # bash tras la activación (gana). Apunta a los datasets del venv/master.
    cmd = [CONDA, "run", "-n", ENV, "bash", "-c",
           f"export GPAW_SETUP_PATH={SETUP_PATH}; "
           f"exec mpiexec -n {ncores} python input.py"]
    log = open(d / "run.log", "w")
    return subprocess.Popen(cmd, cwd=str(d), env=env, stdout=log, stderr=log,
                            start_new_session=True)


def run_one(name, ncores, parallel, timeout=900):
    d = make_dir(name, parallel)
    t0 = time.time()
    p = popen(d, ncores)
    try:
        p.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
    wall = round(time.time() - t0, 1)
    n, t_iter, rj = parse(d)
    status = "ok" if n >= 5 else "CRASH"
    err = ""
    if status == "CRASH":
        err = (rj.get("err") or (d / "run.log").read_text(errors="replace")[-200:]).replace("\n", " ")[:180]
    return {"name": name, "n": ncores, "status": status, "wall_s": wall,
            "n_iters": n, "t_iter_s": t_iter, "energy": rj.get("energy"), "error": err}


def run_concurrent(nslots, timeout=1200):
    """Lanza nslots jobs single-point a 1 core SIMULTÁNEOS; mide throughput."""
    dirs = [make_dir(f"conc{nslots}_slot{i}", {}) for i in range(nslots)]
    t0 = time.time()
    procs = [popen(d, 1) for d in dirs]
    for p in procs:
        try: p.wait(timeout=timeout)
        except subprocess.TimeoutExpired: p.kill()
    wall = round(time.time() - t0, 1)
    tpis = []
    for d in dirs:
        n, t_iter, _ = parse(d)
        if t_iter: tpis.append(t_iter)
    avg = round(sum(tpis)/len(tpis), 1) if tpis else None
    throughput = round(sum(1.0/t for t in tpis), 4) if tpis else 0
    return {"slots": nslots, "n_ok": len(tpis), "avg_t_iter_s": avg,
            "throughput": throughput, "wall_s": wall, "per_job": tpis}


def main():
    shutil.rmtree(BENCH_ROOT, ignore_errors=True)
    BENCH_ROOT.mkdir(parents=True, exist_ok=True)
    print(f"{'='*66}\nBENCHMARK GPAW 24.6.0 (estable) — supercelda single-point\n{'='*66}")

    # (1) ¿domain funciona?
    print("\n### (1) DOMAIN DECOMPOSITION (master crashea con AssertionError)")
    dom = []
    for name, n, par in [("dom_n1", 1, {}),
                         ("dom2", 2, {"kpt":1,"domain":2,"band":1}),
                         ("dom4", 4, {"kpt":1,"domain":4,"band":1}),
                         ("dom8", 8, {"kpt":1,"domain":8,"band":1})]:
        r = run_one(name, n, par)
        dom.append(r)
        msg = f"  {name:8} n={n}  {r['status']:6} wall={r['wall_s']:>6}s iters={r['n_iters']:<3} t/iter={r['t_iter_s']}s"
        if r["status"] != "ok": msg += f"\n      → {r['error'][:120]}"
        print(msg, flush=True)
    base = next((r["wall_s"] for r in dom if r["name"]=="dom_n1" and r["status"]=="ok"), None)
    if base:
        print("  speedup domain (wall vs n=1):")
        for r in dom:
            if r["status"]=="ok":
                print(f"    {r['name']:8} {base/r['wall_s']:.2f}x")

    # (2) Escalado de concurrencia
    print("\n### (2) ESCALADO DE CONCURRENCIA a 1 core (discrimina bug vs bandwidth)")
    print("    master: 1 slot=1.0x, 2 slots=1.13x throughput")
    conc = []
    for ns in [1, 2, 4, 8]:
        r = run_concurrent(ns)
        conc.append(r)
        print(f"  {ns} slot(s): t/iter={r['avg_t_iter_s']}s  throughput={r['throughput']}  "
              f"(n_ok={r['n_ok']})", flush=True)
    if conc and conc[0]["throughput"]:
        b = conc[0]["throughput"]
        print("  throughput relativo:")
        for r in conc:
            print(f"    {r['slots']} slots: {r['throughput']/b:.2f}x")

    out = {"domain": dom, "concurrency": conc}
    Path(ROOT / "reports/gpaw246_benchmark.json").write_text(json.dumps(out, indent=2))
    print(f"\n→ reports/gpaw246_benchmark.json")
    shutil.rmtree(BENCH_ROOT, ignore_errors=True)


if __name__ == "__main__":
    main()
