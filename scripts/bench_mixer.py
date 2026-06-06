#!/usr/bin/env python3
"""Test de convergencia del mixer para single-point de supercelda.

Mide iters-a-convergencia y t/iter para distintos mixers, a 1 core (las
superceldas Γ-only no escalan con MPI: domain crashea). El objetivo es bajar
el tiempo/job — el grueso del cribado son 482 superceldas a 1 core.
"""
import json, os, re, shutil, subprocess, time
from pathlib import Path

ROOT = Path("/home/luis-ochoa/Documents/Vscode/py/dft")
PY = str(ROOT / ".venv/bin/python3")
SRC = str(ROOT / "src")
RELAX = ROOT / "runs/relax_basic"
SUPER_JOB = "0143dc601867b0c0"   # CsPbBr0.75Cl0.25, 40 átomos

# (nombre, beta, nmaxold, density_conv)
MIXERS = [
    ("beta0.05_n8_d1e-3", 0.05, 8, 1e-3),
    ("beta0.10_n8_d1e-3", 0.10, 8, 1e-3),
    ("beta0.10_n5_d1e-3", 0.10, 5, 1e-3),
    ("beta0.10_n8_d2e-3", 0.10, 8, 2e-3),
]

_INP = '''\
import sys, time, json
sys.path.insert(0, "{src}")
from ase.io import read
from gpaw import GPAW, PW, FermiDirac
from gpaw.mixer import Mixer
from gpaw.mpi import world
t0 = time.time()
atoms = read("structure.cif")
calc = GPAW(mode=PW(300), xc="PBE", kpts={{"size":[1,1,1],"gamma":True}},
            occupations=FermiDirac(0.05),
            convergence={{"density": {dens}, "eigenstates": 1e-4, "energy": 1e-4}},
            mixer=Mixer({beta}, {nmax}, 50), maxiter=120, txt="scf.txt")
atoms.calc = calc
try:
    e = float(atoms.get_potential_energy()); ok = True; err = ""
except Exception as exc:
    e = None; ok = False; err = repr(exc)[:200]
t1 = time.time()
if world.rank == 0:
    json.dump({{"energy": e, "ok": ok, "err": err, "wall_s": round(t1-t0,1)}}, open("res.json","w"))
'''


def run(name, beta, nmax, dens, timeout=2400):
    bdir = RELAX / SUPER_JOB / f"_mx_{name}"
    bdir.mkdir(exist_ok=True)
    shutil.copy2(RELAX / SUPER_JOB / "structure.cif", bdir / "structure.cif")
    (bdir / "input.py").write_text(_INP.format(src=SRC, dens=dens, beta=beta, nmax=nmax))
    env = os.environ.copy()
    for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        env[k] = "1"
    t0 = time.time()
    to = False
    try:
        subprocess.run(["mpirun", "-n", "1", PY, "input.py"], cwd=str(bdir),
                       env=env, timeout=timeout, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        to = True
    wall = round(time.time() - t0, 1)
    txt = (bdir / "scf.txt").read_text(errors="replace") if (bdir / "scf.txt").exists() else ""
    its = re.findall(r"iter:\s*(\d+)\|\s*(\d{2}):(\d{2}):(\d{2})", txt)
    n_it = len(its)
    t_iter = None
    if n_it > 5:
        t = [int(h)*3600+int(m)*60+int(s) for _, h, m, s in its]
        dt = [(t[i]-t[i-1]) % 86400 for i in range(1, len(t))][3:]
        t_iter = round(sum(dt)/len(dt), 1) if dt else None
    rj = {}
    if (bdir / "res.json").exists():
        rj = json.loads((bdir / "res.json").read_text())
    converged = rj.get("ok", False) and not to
    shutil.rmtree(bdir, ignore_errors=True)
    return {"mixer": name, "converged": converged, "n_iters": n_it,
            "t_iter_s": t_iter, "wall_s": wall, "energy": rj.get("energy"),
            "timeout": to}


def main():
    print(f"{'='*64}\nMIXER CONVERGENCE TEST — supercelda single-point, 1 core\n{'='*64}")
    print(f"{'mixer':22} {'conv':5} {'iters':6} {'t/iter':8} {'wall':8} {'E(eV)'}")
    out = []
    for name, beta, nmax, dens in MIXERS:
        r = run(name, beta, nmax, dens)
        out.append(r)
        e = f"{r['energy']:.2f}" if r["energy"] else "—"
        print(f"{r['mixer']:22} {str(r['converged']):5} {r['n_iters']:<6} "
              f"{str(r['t_iter_s']):8} {r['wall_s']:<8} {e}", flush=True)
    Path(ROOT / "reports/mixer_test.json").write_text(json.dumps(out, indent=2))
    print(f"\n→ reports/mixer_test.json")
    # mejor = convergido con menor wall
    conv = [r for r in out if r["converged"]]
    if conv:
        best = min(conv, key=lambda r: r["wall_s"])
        print(f"\nMEJOR: {best['mixer']} — {best['n_iters']} iters, "
              f"{best['wall_s']}s ({best['wall_s']/60:.1f} min/job)")


if __name__ == "__main__":
    main()
