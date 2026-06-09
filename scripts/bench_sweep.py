#!/usr/bin/env python3
"""Barrido completo slots×cores — GPAW 24.6.0, single-point supercelda.

Para cada split (S slots, C cores/slot) lanza S jobs CONCURRENTES, cada uno con
domain=C, y mide:
  - t/iter por job (promedio)
  - throughput AGREGADO = Σ_slots (1/t_iter)  [iters/s de toda la máquina]
  - pico de RAM total
  - wall-clock proyectado para 482 superceldas (×28 iters/job)

El split óptimo maximiza throughput agregado cabiendo en RAM. Revela el efecto
NUMA dual-socket (1×44 cruza ambos sockets) empíricamente.

Uso: .venv/bin/python3 scripts/bench_sweep.py
"""
import json, os, re, shutil, subprocess, threading, time
from pathlib import Path

ROOT = Path("/home/luis-ochoa/Documents/Vscode/py/dft")
CONDA = str(Path.home() / "miniforge3/bin/conda")
ENV = "gpaw246"
RELAX = ROOT / "runs/relax_basic"
SUPER_JOB = "0143dc601867b0c0"
BENCH = ROOT / "runs/_sweep"
SETUP_PATH = str(ROOT / ".venv/lib/python3.12/site-packages/gpaw_data/setups")
MAXITER = 10            # mide steady t/iter sin esperar convergencia
AVG_ITERS = 28         # iters a convergencia (mixer beta=0.10)
N_SUPERCELLS = 482
RAM_LIMIT_GB = 52.0    # guard: aborta el split si el RSS total lo supera (evita OOM)

# (slots, cores/slot)
SPLITS_44 = [(1, 44), (2, 22), (3, 14), (4, 11), (5, 8), (8, 5), (11, 4), (22, 2), (44, 1)]
SPLITS_88 = [(2, 44), (4, 22), (8, 11), (11, 8), (22, 4), (44, 2), (88, 1)]
SPLITS = SPLITS_44 + SPLITS_88

_INP = '''\
from ase.io import read
from gpaw import GPAW, PW, FermiDirac
from gpaw.mixer import Mixer
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
    try:
        out = subprocess.check_output(["ps", "-eo", "rss,cmd"], text=True)
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


def popen(d, ncores):
    env = os.environ.copy()
    for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        env[k] = "1"
    cmd = [CONDA, "run", "-n", ENV, "bash", "-c",
           f"export GPAW_SETUP_PATH={SETUP_PATH}; exec mpiexec -n {ncores} python input.py"]
    log = open(d / "run.log", "w")
    return subprocess.Popen(cmd, cwd=str(d), env=env, stdout=log, stderr=log,
                            start_new_session=True)


def parse_t_iter(d):
    txt = (d / "scf.txt").read_text(errors="replace") if (d / "scf.txt").exists() else ""
    its = re.findall(r"iter:\s*(\d+)\s*\|?\s*(\d{1,2}):(\d{2}):(\d{2})", txt)
    if len(its) < 5:
        return None, len(its)
    t = [int(h)*3600+int(m)*60+int(s) for _, h, m, s in its]
    dt = [(t[i]-t[i-1]) % 86400 for i in range(1, len(t))][2:]   # descarta warmup
    return (round(sum(dt)/len(dt), 1) if dt else None), len(its)


# Modelo de RAM/job ajustado a los datos del presupuesto 44: RAM/job ≈ 1.2 + 0.27·C
def est_ram_gb(slots, cores):
    return round(slots * (1.2 + 0.27 * cores), 1)


def run_split(slots, cores, timeout=1200):
    parallel = {} if cores == 1 else {"kpt": 1, "domain": cores, "band": 1}
    dirs = []
    for i in range(slots):
        d = BENCH / f"s{slots}c{cores}_slot{i}"
        d.mkdir(parents=True, exist_ok=True)
        shutil.copy2(RELAX / SUPER_JOB / "structure.cif", d / "structure.cif")
        (d / "input.py").write_text(_INP.format(parallel=repr(parallel), maxiter=MAXITER))
        dirs.append(d)

    peak = [0.0]; stop = [False]; oom = [False]
    procs_ref = [[]]
    def sampler():
        while not stop[0]:
            r = sample_rss_gb()
            if r > peak[0]: peak[0] = r
            if r > RAM_LIMIT_GB:   # guard OOM: aborta el split
                oom[0] = True
                for p in procs_ref[0]:
                    try: p.kill()
                    except Exception: pass
                break
            time.sleep(1)
    th = threading.Thread(target=sampler); th.start()

    t0 = time.time()
    procs = [popen(d, cores) for d in dirs]
    procs_ref[0] = procs
    for p in procs:
        try: p.wait(timeout=timeout)
        except subprocess.TimeoutExpired: p.kill()
    wall = round(time.time() - t0, 1)
    stop[0] = True; th.join()

    tpis, niters = [], []
    for d in dirs:
        ti, n = parse_t_iter(d)
        niters.append(n)
        if ti: tpis.append(ti)
    n_ok = len(tpis)
    avg_tpi = round(sum(tpis)/n_ok, 2) if tpis else None
    throughput = round(sum(1.0/t for t in tpis), 4) if tpis else 0.0
    # wall proyectado para 482 superceldas × 28 iters
    proj_h = round((N_SUPERCELLS * AVG_ITERS) / throughput / 3600, 1) if throughput else None
    return {"slots": slots, "cores": cores, "total_cores": slots*cores,
            "n_ok": n_ok, "avg_t_iter_s": avg_tpi, "throughput": throughput,
            "peak_ram_gb": round(peak[0], 2), "wall_s": wall,
            "proj_hours_482": proj_h, "min_iters": min(niters) if niters else 0,
            "oom": oom[0]}


def main():
    import sys
    budget = sys.argv[1] if len(sys.argv) > 1 else "all"
    global SPLITS
    if budget == "44":
        SPLITS = SPLITS_44
    elif budget == "88":
        SPLITS = SPLITS_88
    else:
        SPLITS = SPLITS_44 + SPLITS_88
    shutil.rmtree(BENCH, ignore_errors=True); BENCH.mkdir(parents=True, exist_ok=True)
    print(f"{'='*88}\nBARRIDO slots×cores — GPAW 24.6 single-point supercelda (budget={budget})\n{'='*88}")
    hdr = f"{'split':>10} {'tot':>4} {'ok':>4} {'t/iter':>8} {'throughput':>11} {'RAM_pico':>9} {'ETA_482':>9}"
    print(hdr); print("-"*len(hdr))
    out = []
    last_budget = None
    for slots, cores in SPLITS:
        budget = slots * cores
        tag = 88 if (slots, cores) in SPLITS_88 else 44
        if tag != last_budget:
            print(f"  --- presupuesto {tag} cores ---")
            last_budget = tag
        # Predicción de RAM: saltar configs que reventarían (ahorra tiempo)
        est = est_ram_gb(slots, cores)
        if est > RAM_LIMIT_GB:
            print(f"{str(slots)+'x'+str(cores):>10} {slots*cores:>4} {'SKIP':>4} "
                  f"{'—':>8} {'—':>11} {str(est)+'GB':>9} {'(OOM est)':>9}", flush=True)
            out.append({"slots": slots, "cores": cores, "total_cores": slots*cores,
                        "skipped": True, "est_ram_gb": est, "throughput": 0.0})
            continue
        r = run_split(slots, cores)
        r["est_ram_gb"] = est
        out.append(r)
        eta = f"{r['proj_hours_482']}h" if r['proj_hours_482'] else "—"
        flag = " OOM!" if r.get("oom") else ""
        print(f"{str(slots)+'x'+str(cores):>10} {r['total_cores']:>4} "
              f"{str(r['n_ok'])+'/'+str(slots):>4} "
              f"{str(r['avg_t_iter_s'])+'s':>8} {r['throughput']:>11} "
              f"{str(r['peak_ram_gb'])+'GB':>9} {eta:>9}{flag}", flush=True)
        Path(ROOT / "reports/sweep_benchmark.json").write_text(json.dumps(out, indent=2))
        time.sleep(3)   # respiro entre splits

    print("\n" + "="*88)
    valid = [r for r in out if r["throughput"] and r["n_ok"] == r["slots"]]
    if valid:
        best = max(valid, key=lambda r: r["throughput"])
        print(f"ÓPTIMO (máx throughput, todos los slots OK): {best['slots']}x{best['cores']} "
              f"→ throughput={best['throughput']} iters/s, ETA 482 ≈ {best['proj_hours_482']}h, "
              f"RAM {best['peak_ram_gb']}GB")
    print(f"→ reports/sweep_benchmark.json")
    shutil.rmtree(BENCH, ignore_errors=True)


if __name__ == "__main__":
    main()
