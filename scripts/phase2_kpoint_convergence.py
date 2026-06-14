#!/usr/bin/env python3
"""GATING Fase 2A: convergencia de FUERZAS en k-points (Γ-only vs [2,2,2] vs [3,3,3]).

Decide si Γ-only [1,1,1] basta para las fuerzas (objetivo de Fase 2 = datos E+F para MACE)
o si hace falta [2,2,2]. Γ-only reduce la RAM ~4× → resuelve el deadlock. Mide para cada
malla: RMS de fuerzas (vs referencia [3,3,3]), energía/átomo, pico de RAM y wall-time.

Estructura de prueba: supercelda 2×2×2 (40 átomos) de CsSnI3 (Sn = el caso difícil).
Nivel: PBE single-point (sin U, consistente con MPtrj/MACE-MP-0), PW(450), FermiDirac 0.2.

Uso: .venv/bin/python3 scripts/phase2_kpoint_convergence.py
"""
import json, os, re, shutil, subprocess, threading, time
from pathlib import Path

ROOT = Path("/home/luis-ochoa/Documents/Vscode/py/dft")
CONDA = str(Path.home() / "miniforge3/bin/conda")
ENV = "gpaw246"
SETUP_PATH = str(ROOT / ".venv/lib/python3.12/site-packages/gpaw_data/setups")
WORK = ROOT / "runs" / "_phase2_kpoint_test"
N_CORES = 8
# (etiqueta, kpts) — [3,3,3] = referencia
CONFIGS = [("gamma", [1, 1, 1]), ("k222", [2, 2, 2]), ("k333", [3, 3, 3])]

_INPUT = '''\
import json, time
import numpy as np
from ase import Atoms
from ase.build import make_supercell
from gpaw import GPAW, PW, FermiDirac
from gpaw.mixer import Mixer
from gpaw.mpi import world

# CsSnI3 cúbica primitiva → supercelda 2x2x2 (40 átomos)
a0 = 6.10
prim = Atoms("CsSnI3",
             scaled_positions=[(0,0,0),(0.5,0.5,0.5),(0.5,0.5,0.0),(0.5,0.0,0.5),(0.0,0.5,0.5)],
             cell=[a0,a0,a0], pbc=True)
atoms = make_supercell(prim, np.diag([2,2,2]))

calc = GPAW(mode=PW(450), xc="PBE",
            kpts={{"size": {kpts}, "gamma": True}},
            occupations=FermiDirac(0.2),
            mixer=Mixer(0.05, 8, 50),
            convergence={{"density": 1e-4, "eigenstates": 1e-6, "energy": 1e-5}},
            maxiter=300, txt="gpaw.txt")
atoms.calc = calc
t0 = time.time()
ok = True; err = ""
try:
    e = float(atoms.get_potential_energy())
    f = atoms.get_forces()
    try:
        s = atoms.get_stress(voigt=True).tolist()
    except Exception:
        s = None
except Exception as exc:
    ok = False; err = repr(exc)[:300]; e = None; f = None; s = None
wall = time.time() - t0
if world.rank == 0:
    json.dump({{"ok": ok, "err": err, "e": e,
               "epa": (e/len(atoms) if e is not None else None),
               "forces": (np.asarray(f).tolist() if f is not None else None),
               "stress": s, "wall_s": round(wall,1), "natoms": len(atoms)}},
              open("result.json", "w"))
'''


def sample_peak_rss_gb(stop, peak):
    while not stop[0]:
        try:
            out = subprocess.check_output(["ps", "-eo", "rss,cmd"], text=True)
            tot = sum(int(l.split()[0]) for l in out.splitlines()
                      if "python input.py" in l and "grep" not in l)
            peak[0] = max(peak[0], tot / 1048576.0)
        except Exception:
            pass
        time.sleep(1)


def run_config(name, kpts, timeout=3600):
    d = WORK / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "input.py").write_text(_INPUT.format(kpts=kpts))
    env = os.environ.copy()
    for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        env[k] = "1"
    cmd = [CONDA, "run", "-n", ENV, "bash", "-c",
           f"export GPAW_SETUP_PATH={SETUP_PATH}; exec mpiexec -n {N_CORES} python input.py"]
    stop = [False]; peak = [0.0]
    th = threading.Thread(target=sample_peak_rss_gb, args=(stop, peak)); th.start()
    t0 = time.time()
    log = open(d / "run.log", "w")
    try:
        subprocess.run(cmd, cwd=str(d), env=env, timeout=timeout,
                       stdout=log, stderr=subprocess.STDOUT)
    except subprocess.TimeoutExpired:
        pass
    stop[0] = True; th.join()
    wall = round(time.time() - t0, 1)
    res = {}
    if (d / "result.json").exists():
        try: res = json.loads((d / "result.json").read_text())
        except Exception: pass
    its = 0
    if (d / "gpaw.txt").exists():
        its = (d / "gpaw.txt").read_text(errors="replace").count("iter:")
    return {"name": name, "kpts": kpts, "peak_ram_gb": round(peak[0], 2),
            "wall_s": wall, "scf_iters": its, **res}


def main():
    shutil.rmtree(WORK, ignore_errors=True); WORK.mkdir(parents=True, exist_ok=True)
    print(f"{'='*70}\nFase 2A — convergencia de FUERZAS en k-points (CsSnI3 40 átomos, PBE)\n{'='*70}")
    results = []
    for name, kpts in CONFIGS:
        print(f"\n[{name}] kpts={kpts} corriendo (n={N_CORES})…", flush=True)
        r = run_config(name, kpts)
        results.append(r)
        ok = r.get("ok")
        print(f"  ok={ok} iters={r['scf_iters']} wall={r['wall_s']}s "
              f"RAM_pico={r['peak_ram_gb']}GB epa={r.get('epa')}")
        if not ok:
            print(f"  ERROR: {r.get('err','')[:120]}")

    # Comparar fuerzas vs referencia [3,3,3]
    import numpy as np
    ref = next((r for r in results if r["name"] == "k333" and r.get("forces")), None)
    print(f"\n{'='*70}\nRESUMEN — RMS de fuerzas vs referencia [3,3,3]\n{'='*70}")
    print(f"{'config':8} {'iters':6} {'RAM(GB)':8} {'wall(s)':8} {'RMS_F(eV/Å)':14} {'maxΔF':10} {'Δepa(eV)':10}")
    out = []
    for r in results:
        rms = maxd = depa = None
        if ref and r.get("forces"):
            f = np.asarray(r["forces"]); fr = np.asarray(ref["forces"])
            df = f - fr
            rms = float(np.sqrt(np.mean(df**2)))
            maxd = float(np.abs(df).max())
            depa = float(r["epa"] - ref["epa"]) if (r.get("epa") and ref.get("epa")) else None
        print(f"{r['name']:8} {r['scf_iters']:<6} {r['peak_ram_gb']:<8} {r['wall_s']:<8} "
              f"{(f'{rms:.4f}' if rms is not None else '—'):14} "
              f"{(f'{maxd:.4f}' if maxd is not None else '—'):10} "
              f"{(f'{depa:+.4f}' if depa is not None else '—'):10}")
        out.append({**{k: r[k] for k in ('name','kpts','scf_iters','peak_ram_gb','wall_s','epa','ok')},
                    "rms_force_vs_ref": rms, "max_force_diff": maxd, "depa_vs_ref": depa})

    # Veredicto
    g = next((o for o in out if o["name"] == "gamma"), None)
    print(f"\n{'='*70}\nVEREDICTO\n{'='*70}")
    if g and g.get("rms_force_vs_ref") is not None:
        rms = g["rms_force_vs_ref"]
        verdict = "GAMMA-ONLY OK" if rms < 0.03 else "GAMMA-ONLY INSUFICIENTE → usar [2,2,2]"
        print(f"Γ-only RMS_F vs [3,3,3] = {rms:.4f} eV/Å  (umbral 0.03)  → {verdict}")
        k2 = next((o for o in out if o["name"] == "k222"), None)
        if k2 and k2.get("peak_ram_gb") and g.get("peak_ram_gb"):
            print(f"RAM: Γ-only {g['peak_ram_gb']}GB  vs  [2,2,2] {k2['peak_ram_gb']}GB "
                  f"({k2['peak_ram_gb']/max(g['peak_ram_gb'],0.1):.1f}× más)")
    Path(ROOT / "reports/training fase 2").mkdir(parents=True, exist_ok=True)
    (ROOT / "reports/training fase 2/phase2_kpoint_convergence.json").write_text(json.dumps(out, indent=2))
    print(f"\n→ reports/training fase 2/phase2_kpoint_convergence.json")
    shutil.rmtree(WORK, ignore_errors=True)


if __name__ == "__main__":
    main()
