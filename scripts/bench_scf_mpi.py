#!/usr/bin/env python3
"""Benchmark de SCF single-point con paralelización MPI.

Pregunta clave: para un SINGLE-POINT PBE (no FIRE), ¿la paralelización MPI
ayuda? En particular:
  - Superceldas (40 átomos, Γ-only = 1 k-point): la única vía a >1 core es
    `domain` decomposition. domain>1 crasheaba con FIRE/MGGA → ¿funciona ahora
    con PBE single-point?
  - Celdas puras (5 átomos, [2,2,2] = 8 k-points): kpt-parallel puede usar
    hasta 8 cores. ¿Cuánto escala?

Para cada (job, config) genera un input single-point, corre `mpirun -n N`,
parsea init/iter/total/converged. NO modifica los input.py de producción.

Uso: .venv/bin/python3 scripts/bench_scf_mpi.py
"""
import json, os, re, shutil, subprocess, sys, time
from datetime import datetime
from pathlib import Path

ROOT = Path("/home/luis-ochoa/Documents/Vscode/py/dft")
PY = str(ROOT / ".venv/bin/python3")
SRC = str(ROOT / "src")
RELAX = ROOT / "runs/relax_basic"

# Jobs de prueba (Pb-estables)
PURE_JOB = "10f36370db3af4fb"   # CsPbCl3, 5 átomos, 8 k-points
SUPER_JOB = "0143dc601867b0c0"  # CsPbBr0.75Cl0.25, 40 átomos, Γ-only

# (nombre, n_cores, kpts, parallel_dict)
CONFIGS_PURE = [
    ("pure_n1",        1, [2, 2, 2], {}),
    ("pure_kpt2",      2, [2, 2, 2], {"kpt": 2, "domain": 1, "band": 1}),
    ("pure_kpt4",      4, [2, 2, 2], {"kpt": 4, "domain": 1, "band": 1}),
    ("pure_kpt8",      8, [2, 2, 2], {"kpt": 8, "domain": 1, "band": 1}),
    ("pure_domain4",   4, [2, 2, 2], {"kpt": 1, "domain": 4, "band": 1}),
]
CONFIGS_SUPER = [
    ("super_n1",       1, [1, 1, 1], {}),
    ("super_domain2",  2, [1, 1, 1], {"kpt": 1, "domain": 2, "band": 1}),
    ("super_domain4",  4, [1, 1, 1], {"kpt": 1, "domain": 4, "band": 1}),
    ("super_domain8",  8, [1, 1, 1], {"kpt": 1, "domain": 8, "band": 1}),
]

_INPUT = '''\
import sys, time, json
sys.path.insert(0, "{src}")
from ase.io import read
from gpaw import GPAW, PW, FermiDirac
from gpaw.mixer import Mixer
from gpaw.mpi import world

t0 = time.time()
atoms = read("{cif}")
_parallel = {parallel}
calc = GPAW(
    mode=PW(300),
    xc="PBE",
    kpts={{"size": {kpts}, "gamma": True}},
    occupations=FermiDirac(0.05),
    convergence={{"density": 1e-3, "eigenstates": 1e-4, "energy": 1e-4}},
    mixer=Mixer(0.05, 8, 50),
    parallel=_parallel if _parallel else None,
    maxiter=12,
    txt="{txt}",
)
atoms.calc = calc
try:
    e = float(atoms.get_potential_energy())
    ok = True
    err = ""
except Exception as exc:
    e = None; ok = False; err = repr(exc)[:300]
t1 = time.time()
if world.rank == 0:
    json.dump({{"energy": e, "ok": ok, "err": err, "wall_s": round(t1 - t0, 1)}},
              open("{res}", "w"))
'''


def parse_txt(txt_path):
    """Devuelve (n_iters, t_init_s, t_iter_avg_s) parseando los timestamps SCF."""
    if not txt_path.exists():
        return 0, None, None
    content = txt_path.read_text(errors="replace")
    # Formato GPAW: "|iter:   1| 17:57:34 | ..."
    its = re.findall(r"iter:\s*(\d+)\|\s*(\d{2}):(\d{2}):(\d{2})", content)
    if len(its) < 2:
        return len(its), None, None
    t = [int(h) * 3600 + int(m) * 60 + int(s) for _, h, m, s in its]
    dt = [(t[i] - t[i - 1]) % 86400 for i in range(1, len(t))]
    # descarta warmup (primeras 3)
    steady = dt[3:] if len(dt) > 4 else dt
    t_iter = sum(steady) / len(steady) if steady else None
    return len(its), None, (round(t_iter, 1) if t_iter else None)


def run_cfg(job, name, ncores, kpts, parallel, timeout=900):
    jd = RELAX / job
    bdir = jd / f"_bench_{name}"
    bdir.mkdir(exist_ok=True)
    shutil.copy2(jd / "structure.cif", bdir / "structure.cif")
    txt = "scf.txt"
    res = "res.json"
    inp = _INPUT.format(src=SRC, cif="structure.cif", parallel=repr(parallel),
                        kpts=kpts, txt=txt, res=res)
    (bdir / "input_bench.py").write_text(inp)

    env = os.environ.copy()
    for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        env[k] = "1"

    t0 = time.time()
    stderr = ""
    timed_out = False
    try:
        p = subprocess.run(
            ["mpirun", "-n", str(ncores), PY, "input_bench.py"],
            cwd=str(bdir), env=env, timeout=timeout,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        stderr = p.stderr.decode(errors="replace")[-300:]
    except subprocess.TimeoutExpired:
        timed_out = True
    wall = round(time.time() - t0, 1)

    rj = {}
    if (bdir / res).exists():
        try:
            rj = json.loads((bdir / res).read_text())
        except Exception:
            pass
    n_it, _, t_iter = parse_txt(bdir / txt)

    # Crash real = init falla (0 iters). No-convergencia en maxiter=12 es
    # esperada y benigna: lo que medimos es t/iter, no convergencia.
    if n_it >= 5:
        status = "ok"
    elif timed_out:
        status = "TIMEOUT"
    else:
        status = "CRASH"

    out = {
        "config": name, "n": ncores, "kpts": kpts, "parallel": parallel,
        "status": status, "wall_s": wall, "n_iters": n_it, "t_iter_s": t_iter,
        "energy": rj.get("energy"),
    }
    if status != "ok":
        out["error"] = (rj.get("err") or stderr or "?").replace("\n", " ")[:200]
    return out


def main():
    results = {"pure": [], "super": []}
    print(f"{'='*70}\nBENCHMARK SCF single-point + MPI  —  {datetime.now():%H:%M:%S}\n{'='*70}")

    print(f"\n### SUPERCELDA (40 átomos, Γ-only) — job {SUPER_JOB}")
    print("    PREGUNTA CLAVE: ¿domain>1 funciona con PBE single-point?")
    for name, n, kpts, par in CONFIGS_SUPER:
        r = run_cfg(SUPER_JOB, name, n, kpts, par)
        results["super"].append(r)
        msg = (f"  {name:16} n={n}  {r['status']:8} wall={r['wall_s']:>6}s "
               f"iters={r['n_iters']:<3} t/iter={r['t_iter_s']}s")
        if r["status"] != "ok":
            msg += f"\n       → {r.get('error','')[:120]}"
        print(msg, flush=True)

    print(f"\n### CELDA PURA (5 átomos, 8 k-points) — job {PURE_JOB}")
    for name, n, kpts, par in CONFIGS_PURE:
        r = run_cfg(PURE_JOB, name, n, kpts, par)
        results["pure"].append(r)
        msg = (f"  {name:16} n={n}  {r['status']:8} wall={r['wall_s']:>6}s "
               f"iters={r['n_iters']:<3} t/iter={r['t_iter_s']}s")
        if r["status"] != "ok":
            msg += f"\n       → {r.get('error','')[:120]}"
        print(msg, flush=True)

    # Resumen speedup
    print(f"\n{'='*70}\nRESUMEN (speedup wall vs n=1)\n{'='*70}")
    for tag in ("super", "pure"):
        rs = [r for r in results[tag] if r["status"] == "ok"]
        if not rs:
            print(f"{tag}: sin configs OK"); continue
        base = rs[0]["wall_s"]
        print(f"\n{tag.upper()}:")
        for r in rs:
            sp = base / r["wall_s"] if r["wall_s"] else 0
            print(f"  {r['config']:16} n={r['n']}  wall={r['wall_s']:>6}s  speedup={sp:.2f}x")

    Path(ROOT / "reports").mkdir(exist_ok=True)
    Path(ROOT / "reports/scf_mpi_benchmark.json").write_text(json.dumps(results, indent=2))
    print(f"\n→ reports/scf_mpi_benchmark.json")

    # Limpieza de dirs temporales
    for tag, job in (("super", SUPER_JOB), ("pure", PURE_JOB)):
        for r in results[tag]:
            bdir = RELAX / job / f"_bench_{r['config']}"
            shutil.rmtree(bdir, ignore_errors=True)


if __name__ == "__main__":
    main()
