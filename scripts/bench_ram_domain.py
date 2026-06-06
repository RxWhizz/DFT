#!/usr/bin/env python3
"""Sonda de RAM por job según domain cores — GPAW 24.6.0.

Para cada domain∈{1,2,4,8}: corre un single-point de supercelda (maxiter=8) y
muestrea el pico de RSS TOTAL del grupo de procesos (suma de ranks). Reporta
(cores, peak_RAM_GB, RAM/core, t_iter). Permite calcular cuántos jobs caben en
RAM para cada estrategia de paralelización.

Uso: .venv/bin/python3 scripts/bench_ram_domain.py
"""
import json, os, re, shutil, subprocess, threading, time
from pathlib import Path

ROOT = Path("/home/luis-ochoa/Documents/Vscode/py/dft")
CONDA = str(Path.home() / "miniforge3/bin/conda")
ENV = "gpaw246"
RELAX = ROOT / "runs/relax_basic"
SUPER_JOB = "0143dc601867b0c0"
BENCH = ROOT / "runs/_ram_domain"
SETUP_PATH = str(ROOT / ".venv/lib/python3.12/site-packages/gpaw_data/setups")
MAXITER = 8

_INP = '''\
import time, json
from ase.io import read
from gpaw import GPAW, PW, FermiDirac
from gpaw.mixer import Mixer
from gpaw.mpi import world
atoms = read("structure.cif")
_p = {parallel}
calc = GPAW(mode=PW(300), xc="PBE", kpts={{"size":[1,1,1],"gamma":True}},
            occupations=FermiDirac(0.05),
            convergence={{"density":1e-3,"eigenstates":1e-4,"energy":1e-4}},
            mixer=Mixer(0.1,8,50), parallel=_p if _p else None,
            maxiter={maxiter}, txt="scf.txt")
atoms.calc = calc
try:
    atoms.get_potential_energy()
except Exception:
    pass
'''


def sample_rss_gb():
    """Suma RSS (GB) de todos los 'python input.py' vivos."""
    try:
        out = subprocess.check_output(
            ["ps", "-eo", "rss,cmd"], text=True)
    except Exception:
        return 0.0
    tot = 0
    for line in out.splitlines():
        if "python input.py" in line and "grep" not in line:
            try:
                tot += int(line.split()[0])
            except Exception:
                pass
    return tot / 1048576.0


def run(name, ncores, parallel, timeout=600):
    d = BENCH / name
    d.mkdir(parents=True, exist_ok=True)
    shutil.copy2(RELAX / SUPER_JOB / "structure.cif", d / "structure.cif")
    (d / "input.py").write_text(_INP.format(parallel=repr(parallel), maxiter=MAXITER))
    env = os.environ.copy()
    for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        env[k] = "1"
    cmd = [CONDA, "run", "-n", ENV, "bash", "-c",
           f"export GPAW_SETUP_PATH={SETUP_PATH}; exec mpiexec -n {ncores} python input.py"]
    log = open(d / "run.log", "w")
    p = subprocess.Popen(cmd, cwd=str(d), env=env, stdout=log, stderr=log,
                         start_new_session=True)
    peak = [0.0]
    stop = [False]

    def sampler():
        while not stop[0]:
            r = sample_rss_gb()
            if r > peak[0]:
                peak[0] = r
            time.sleep(1)

    th = threading.Thread(target=sampler)
    th.start()
    try:
        p.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
    stop[0] = True
    th.join()

    txt = (d / "scf.txt").read_text(errors="replace") if (d / "scf.txt").exists() else ""
    its = re.findall(r"iter:\s*(\d+)\s*\|?\s*(\d{1,2}):(\d{2}):(\d{2})", txt)
    t_iter = None
    if len(its) > 4:
        t = [int(h)*3600+int(m)*60+int(s) for _, h, m, s in its]
        dt = [(t[i]-t[i-1]) % 86400 for i in range(1, len(t))][2:]
        t_iter = round(sum(dt)/len(dt), 1) if dt else None
    return {"name": name, "cores": ncores, "peak_ram_gb": round(peak[0], 2),
            "ram_per_core_gb": round(peak[0]/ncores, 2),
            "n_iters": len(its), "t_iter_s": t_iter}


def main():
    shutil.rmtree(BENCH, ignore_errors=True)
    BENCH.mkdir(parents=True, exist_ok=True)
    print(f"{'='*60}\nRAM por job según domain cores — GPAW 24.6\n{'='*60}")
    print(f"{'config':10} {'cores':6} {'peak_RAM':9} {'RAM/core':9} {'t/iter':8}")
    out = []
    for name, n, par in [("dom1", 1, {}),
                         ("dom2", 2, {"kpt":1,"domain":2,"band":1}),
                         ("dom4", 4, {"kpt":1,"domain":4,"band":1}),
                         ("dom8", 8, {"kpt":1,"domain":8,"band":1})]:
        r = run(name, n, par)
        out.append(r)
        print(f"{r['name']:10} {r['cores']:<6} {r['peak_ram_gb']:<9} "
              f"{r['ram_per_core_gb']:<9} {r['t_iter_s']}s", flush=True)
    Path(ROOT / "reports/ram_domain.json").write_text(json.dumps(out, indent=2))
    print(f"\n→ reports/ram_domain.json")
    shutil.rmtree(BENCH, ignore_errors=True)


if __name__ == "__main__":
    main()
