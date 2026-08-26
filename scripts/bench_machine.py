#!/usr/bin/env python3
"""Calibra cuántos jobs concurrentes y cuántos núcleos por job aguanta la máquina.

Para cada reparto (S slots × C núcleos) lanza S jobs idénticos a la vez, mide el
tiempo por iteración SCF de cada uno y calcula el **throughput agregado**
—Σ(1/t_iter), iteraciones por segundo de la máquina entera— junto al pico de
RAM. El óptimo maximiza throughput sin salirse de la memoria.

Qué cambia respecto a `bench_sweep.py`, que es de donde sale:

* Los repartos se derivan de la topología real en vez de estar escritos a mano
  para un Xeon de 44/88 núcleos.
* La raíz del proyecto se resuelve desde el archivo, no de una ruta absoluta a
  un checkout que ya no se usa.
* El techo de RAM sale de la RAM instalada, no de un 52 fijo.
* GPAW se lanza con `launch_job` del runner: si el runner cambia de entorno
  conda o de flags, el barrido lo sigue. Duplicarlo era la razón de que este
  barrido midiera `mpiexec` mientras el runner usaba `job.sh`.
* El resultado se guarda como calibración indexada por huella de hardware, que
  el monitor puede leer. Antes se escribía un JSON que no leía nadie.

Uso:
    python scripts/bench_machine.py --quick          # ~15 min, 3 repartos
    python scripts/bench_machine.py                  # barrido completo, horas
    python scripts/bench_machine.py --budget 44      # solo núcleos físicos
    python scripts/bench_machine.py --dry-run        # enseña el plan y sale
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from buho.bench import calibration as calib                      # noqa: E402
from buho.bench.machine import (                                 # noqa: E402
    Machine, Split, budgets_for, detect, ram_limit_gb, splits_for,
)

MAXITER = 10          # basta para el t/iter estable; no se busca converger
AVG_ITERS = 28        # iteraciones típicas hasta converger (mixer beta=0.10)
BENCH_DIR = ROOT / "local_runs" / "_bench"
PROGRESO = ROOT / "data" / "bench" / "progress.json"

_INPUT = '''\
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
    # El original hacía `except Exception: pass`, así que un reparto imposible
    # —domain que no divide la malla, por ejemplo— se veía igual que uno lento:
    # cero iteraciones y ninguna pista. Se deja constancia.
    import traceback
    with open("bench_error.txt", "w") as fh:
        traceback.print_exc(file=fh)
'''


def elegir_estructura() -> Path:
    """Una estructura que el pipeline sepa calcular de verdad.

    Se prefieren las de jobs **convergidos**: son prueba de que sus elementos
    tienen dataset PAW y de que la configuración funciona. Coger «la mayor» sin
    más eligió una de catión orgánico —con C, H, N— que el pipeline no calcula,
    y el barrido entero murió con `Could not find required PAW dataset "C.PBE"`.
    Además así se mide sobre el tipo de sistema que se va a correr.
    """
    convergidas: list[Path] = []
    otras: list[Path] = []
    for status in ROOT.glob("local_runs/*/batch_*/*/status.json"):
        cif = status.parent / "structure.cif"
        if not cif.is_file():
            continue
        try:
            estado = json.loads(status.read_text(errors="replace")).get("status")
        except (OSError, json.JSONDecodeError):
            estado = None
        (convergidas if estado == "converged" else otras).append(cif)

    for grupo in (convergidas, otras):
        if grupo:
            # La mayor del grupo: el caso más exigente entre los que funcionan.
            return max(grupo, key=lambda p: p.stat().st_size)

    raise SystemExit(
        "No hay ninguna structure.cif de un job convergido con la que medir.\n"
        "Prepara y corre un lote antes: el barrido mide sobre trabajo real."
    )


def rss_total_gb() -> float:
    """Suma del RSS de los procesos de cálculo, en GB."""
    try:
        salida = subprocess.check_output(["ps", "-eo", "rss,cmd"], text=True)
    except (OSError, subprocess.SubprocessError):
        return 0.0
    total = 0
    for linea in salida.splitlines():
        if "python input.py" in linea and "grep" not in linea:
            try:
                total += int(linea.split()[0])
            except (ValueError, IndexError):
                pass
    return total / 1048576.0


def t_por_iteracion(d: Path) -> tuple[float | None, int]:
    """Segundos por iteración SCF, descartando el arranque."""
    scf = d / "scf.txt"
    if not scf.exists():
        return None, 0
    marcas = re.findall(r"iter:\s*(\d+)\s*\|?\s*(\d{1,2}):(\d{2}):(\d{2})",
                        scf.read_text(errors="replace"))
    if len(marcas) < 5:
        return None, len(marcas)
    segundos = [int(h) * 3600 + int(m) * 60 + int(s) for _, h, m, s in marcas]
    deltas = [(segundos[i] - segundos[i - 1]) % 86400 for i in range(1, len(segundos))][2:]
    return (round(sum(deltas) / len(deltas), 2) if deltas else None), len(marcas)


def medir_reparto(split: Split, estructura: Path, techo_ram: float,
                  timeout: int = 1800) -> dict:
    """Lanza `split.slots` jobs de `split.cores` núcleos y mide el conjunto."""
    import buho_relax_runner as runner

    # `launch_job` escribe una línea en el `runner.log` del directorio de
    # relajaciones. Ese es un global que el propio runner rebinde en su `main()`;
    # aquí se hace igual, apuntándolo al directorio del barrido. Sin esto,
    # medir aborta con FileNotFoundError si `runs/relax_basic` no existe.
    runner.LOG_FILE = BENCH_DIR / "bench.log"

    paralelo = {} if split.cores == 1 else {"kpt": 1, "domain": split.cores, "band": 1}
    dirs = []
    for i in range(split.slots):
        d = BENCH_DIR / f"s{split.slots}c{split.cores}_slot{i}"
        d.mkdir(parents=True, exist_ok=True)
        shutil.copy2(estructura, d / "structure.cif")
        (d / "input.py").write_text(_INPUT.format(parallel=repr(paralelo), maxiter=MAXITER))
        dirs.append(d)

    pico = [0.0]
    parar = threading.Event()
    oom = [False]
    procesos: list = []

    def vigilar_ram() -> None:
        while not parar.wait(1.0):
            actual = rss_total_gb()
            pico[0] = max(pico[0], actual)
            if actual > techo_ram:
                oom[0] = True
                for p in procesos:
                    try:
                        p.kill()
                    except OSError:
                        pass
                return

    hilo = threading.Thread(target=vigilar_ram, daemon=True)
    hilo.start()

    t0 = time.time()
    slots = [runner.launch_job(d, split.cores) for d in dirs]
    procesos.extend(getattr(s, "proc", s) for s in slots)
    for p in procesos:
        try:
            p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            p.kill()
    wall = round(time.time() - t0, 1)
    parar.set()
    hilo.join(timeout=5)

    tiempos, iteraciones, errores = [], [], []
    for d in dirs:
        t, n = t_por_iteracion(d)
        iteraciones.append(n)
        if t:
            tiempos.append(t)
        err = d / "bench_error.txt"
        if err.exists():
            lineas = [l for l in err.read_text(errors="replace").splitlines() if l.strip()]
            if lineas:
                errores.append(lineas[-1])

    throughput = round(sum(1.0 / t for t in tiempos), 4) if tiempos else 0.0
    return {
        "slots": split.slots,
        "cores": split.cores,
        "total_cores": split.total_cores,
        "n_ok": len(tiempos),
        "avg_t_iter_s": round(sum(tiempos) / len(tiempos), 2) if tiempos else None,
        "throughput": throughput,
        "peak_ram_gb": round(pico[0], 2),
        "wall_s": wall,
        "min_iters": min(iteraciones) if iteraciones else 0,
        "oom": oom[0],
        "error": errores[0] if errores else None,
    }


def escribir_progreso(estado: str, *, hechos: int = 0, total: int = 0,
                      actual: str | None = None, resultados: list | None = None,
                      error: str | None = None) -> None:
    """Deja el avance en disco para que el monitor lo lea.

    El barrido dura horas en un proceso aparte: sin esto, la interfaz solo
    podría decir «corriendo» sin saber por dónde va.
    """
    try:
        PROGRESO.parent.mkdir(parents=True, exist_ok=True)
        PROGRESO.write_text(json.dumps({
            "status": estado,
            "pid": os.getpid(),
            "done": hechos,
            "total": total,
            "current": actual,
            "results": resultados or [],
            "error": error,
            "updated_at": time.time(),
        }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError:
        pass   # el progreso es informativo: no se aborta el barrido por él


def maquina_ocupada() -> list[str]:
    """Procesos de cálculo ajenos al barrido que falsearían la medición.

    Medir con la máquina cargada da un t/iter inflado y un throughput bajo, y
    quien lea el resultado configurará menos slots de los que aguanta. Encima
    el barrido le roba núcleos al trabajo real.
    """
    import psutil

    culpables = []
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmd = " ".join(proc.info["cmdline"] or ())
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if not cmd:
            continue
        if "_bench" in cmd:          # nuestro propio barrido
            continue
        if any(p in cmd for p in ("buho_relax_runner", "python input.py", "gpaw-python")):
            culpables.append(f"{proc.info['pid']}: {cmd[:90]}")
    return culpables


def plan(maquina: Machine, args) -> list[tuple[int, Split]]:
    """Repartos a medir, en orden."""
    presupuestos = [args.budget] if args.budget else budgets_for(maquina)
    max_splits = 3 if args.quick else args.max_splits
    trabajo = []
    for b in presupuestos:
        for s in splits_for(b, max_splits=max_splits):
            trabajo.append((b, s))
    return trabajo


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true",
                    help="Solo 3 repartos por presupuesto (~15 min en vez de horas).")
    ap.add_argument("--budget", type=int, default=None,
                    help="Medir solo este presupuesto de núcleos.")
    ap.add_argument("--max-splits", type=int, default=9,
                    help="Repartos por presupuesto (default 9).")
    ap.add_argument("--timeout", type=int, default=1800,
                    help="Segundos máximos por reparto (default 1800).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Enseña el plan y la máquina detectada, sin medir.")
    ap.add_argument("--keep", action="store_true",
                    help="No borrar los directorios de medición (para diagnosticar).")
    ap.add_argument("--force", action="store_true",
                    help="Medir aunque haya cálculos corriendo (los datos saldrán sesgados).")
    args = ap.parse_args()

    maquina = detect()
    techo = ram_limit_gb(maquina)
    trabajo = plan(maquina, args)

    print(f"\n  {maquina.describe()}")
    print(f"  huella: {maquina.fingerprint}   techo de RAM: {techo} GB\n")

    previa = calib.load(maquina, ROOT)
    if previa:
        print(f"  Calibración previa: {previa.best} "
              f"({previa.throughput} iters/s, medida {previa.measured_at[:10]})\n")

    if args.dry_run:
        for b, s in trabajo:
            print(f"    presupuesto {b:>4}  →  {s}")
        print(f"\n  {len(trabajo)} repartos. Sin --dry-run se miden de verdad.")
        return 0

    ocupada = maquina_ocupada()
    if ocupada and not args.force:
        print("  La máquina está calculando ahora mismo:")
        for c in ocupada[:5]:
            print(f"    {c}")
        if len(ocupada) > 5:
            print(f"    … y {len(ocupada) - 5} más")
        print("\n  Medir así da un t/iter inflado y recomendaría menos slots de los")
        print("  que aguanta, además de robarle núcleos al trabajo real.")
        print("  Espera a que termine, o usa --force si sabes lo que haces.")
        return 2

    estructura = elegir_estructura()
    print(f"  midiendo sobre {estructura.relative_to(ROOT)}\n")

    shutil.rmtree(BENCH_DIR, ignore_errors=True)
    BENCH_DIR.mkdir(parents=True, exist_ok=True)

    cabecera = (f"{'reparto':>10} {'cores':>6} {'ok':>6} {'t/iter':>9} "
                f"{'throughput':>11} {'RAM pico':>9}")
    print(cabecera)
    print("  " + "-" * (len(cabecera) - 2))

    resultados: list[dict] = []
    presupuesto_actual = None
    escribir_progreso("running", hechos=0, total=len(trabajo))
    try:
        for presupuesto, split in trabajo:
            if presupuesto != presupuesto_actual:
                print(f"  --- presupuesto {presupuesto} núcleos ---")
                presupuesto_actual = presupuesto

            escribir_progreso("running", hechos=len(resultados), total=len(trabajo),
                              actual=str(split), resultados=resultados)
            r = medir_reparto(split, estructura, techo, timeout=args.timeout)
            resultados.append(r)

            marca = "  OOM" if r["oom"] else ""
            if not marca and r["error"]:
                marca = f"  {r['error'][:46]}"
            print(f"{str(split):>10} {r['total_cores']:>6} "
                  f"{str(r['n_ok']) + '/' + str(split.slots):>6} "
                  f"{str(r['avg_t_iter_s']) + 's':>9} {r['throughput']:>11} "
                  f"{str(r['peak_ram_gb']) + 'GB':>9}{marca}", flush=True)
            time.sleep(3)   # que la máquina respire entre repartos
    except KeyboardInterrupt:
        print("\n  interrumpido — se guarda lo medido hasta aquí")
    finally:
        # Si algún reparto perdió slots, los directorios son la única prueba de
        # por qué: se conservan salvo que todo haya ido bien.
        fallo = any(r["n_ok"] < r["slots"] for r in resultados)
        if args.keep or fallo:
            print(f"\n  directorios conservados en {BENCH_DIR.relative_to(ROOT)}")
        else:
            shutil.rmtree(BENCH_DIR, ignore_errors=True)

    presupuesto = args.budget or (trabajo[0][0] if trabajo else 0)
    cal = calib.build(maquina, presupuesto, resultados)
    if cal is None:
        print("\n  Ningún reparto completó todos sus slots: no hay nada que calibrar.")
        escribir_progreso("error", hechos=len(resultados), total=len(trabajo),
                          resultados=resultados,
                          error="Ningún reparto completó todos sus slots.")
        return 1

    ruta = calib.save(cal, ROOT)
    print(f"\n  ÓPTIMO: {cal.best}  →  {cal.throughput} iters/s, "
          f"RAM {cal.peak_ram_gb} GB")
    print(f"  Guardado en {ruta.relative_to(ROOT)}")
    print(f"\n  Para usarlo, en configs/monitor.yaml:")
    print(f"    runner_slots: {cal.best.slots}")
    print(f"    runner_cores: {cal.best.cores}")
    escribir_progreso("done", hechos=len(resultados), total=len(trabajo),
                      resultados=resultados)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
