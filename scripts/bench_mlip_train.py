#!/usr/bin/env python3
"""Benchmark de paralelización del entrenamiento MACE multi-cabeza (CPU).

El entrenamiento es UN solo proceso (no N jobs como el DFT de Fase 1/2). Las perillas son:
  - threads   (OMP/MKL/torch intra-op): aceleran sin casi costo de RAM
  - batch_size: más throughput pero más RAM transitoria (¡estructuras de 324 átomos!)
  - num_workers: solapan carga de datos; replican poco con copy-on-write

Mide, por configuración, el TIEMPO/ÉPOCA (delta entre evals consecutivos del log) y el
PICO DE RAM del árbol de procesos (muestreo de /proc). Elige el óptimo = mínimo tiempo/época
con pico_RAM < --ram-cap (anti-OOM). Opcional: lanza el entrenamiento completo con el óptimo.

Para que el pico de RAM sea realista, el set de benchmark incluye las estructuras más
grandes (perovsiap hasta 324 átomos). El tiempo/época en el set reducido escala en RATIO
entre configs (lo que importa para elegir).

Uso:
  PYTHONPATH=src .venv/bin/python3 scripts/bench_mlip_train.py [--ram-cap 45] [--launch-best]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ase.io import read, write  # noqa: E402

BUILD = ROOT / "data" / "mlip_datasets" / "build"
BENCH = ROOT / "data" / "mlip_datasets" / "bench"
PY = str(ROOT / ".venv/bin/python3")
TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+) INFO: Epoch (\d+):")


# ─────────────────────── set de benchmark (incluye estructuras grandes) ───────────────────────

def build_bench_set(per_head: int = 400) -> dict:
    """Crea bench/<head>_{train,valid}.xyz: muestra por cabeza, incluyendo las más grandes."""
    BENCH.mkdir(parents=True, exist_ok=True)
    heads_cfg = {}
    full = json.loads((BUILD / "heads.json").read_text())
    rng = np.random.RandomState(0)
    for head, cfg in full.items():
        frames = read(cfg["train_file"], index=":")
        sizes = np.array([len(a) for a in frames])
        # incluir las ~40 más grandes (RAM realista) + relleno aleatorio
        big = list(np.argsort(sizes)[-40:])
        rest = [i for i in range(len(frames)) if i not in set(big)]
        extra = list(rng.permutation(rest)[:max(0, per_head - len(big))])
        idx = sorted(set(big) | set(extra))
        sub = [frames[i] for i in idx]
        n_val = max(2, len(sub) // 5)
        tr, va = sub[:-n_val], sub[-n_val:]
        tp, vp = BENCH / f"{head}_train.xyz", BENCH / f"{head}_valid.xyz"
        write(str(tp), tr, format="extxyz")
        write(str(vp), va, format="extxyz")
        heads_cfg[head] = {"train_file": str(tp), "valid_file": str(vp), "E0s": "average"}
    (BENCH / "heads.json").write_text(json.dumps(heads_cfg, indent=2))
    return heads_cfg


# ─────────────────────── muestreo de RAM del árbol de procesos ───────────────────────

def tree_rss_gb(root_pid: int) -> float:
    """Suma RSS (GiB) de root_pid y descendientes leyendo /proc."""
    pids = {root_pid}
    # construir descendencia
    children: dict[int, list[int]] = {}
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            ppid = int(next(l.split()[1] for l in (proc / "status").read_text().splitlines()
                            if l.startswith("PPid:")))
        except Exception:
            continue
        children.setdefault(ppid, []).append(int(proc.name))
    stack = [root_pid]
    while stack:
        p = stack.pop()
        for c in children.get(p, []):
            if c not in pids:
                pids.add(c); stack.append(c)
    total_kb = 0
    for p in pids:
        try:
            for line in Path(f"/proc/{p}/status").read_text().splitlines():
                if line.startswith("VmRSS:"):
                    total_kb += int(line.split()[1]); break
        except Exception:
            pass
    return total_kb / (1024 * 1024)


class RssSampler(threading.Thread):
    def __init__(self, pid: int, interval: float = 1.0):
        super().__init__(daemon=True)
        self.pid, self.interval, self.peak, self._stop = pid, interval, 0.0, False

    def run(self):
        while not self._stop:
            self.peak = max(self.peak, tree_rss_gb(self.pid))
            time.sleep(self.interval)

    def stop(self):
        self._stop = True


# ─────────────────────── una corrida de benchmark ───────────────────────

def run_config(heads_cfg: dict, threads: int, batch: int, workers: int,
               epochs: int = 3) -> dict:
    tag = f"t{threads}_b{batch}_w{workers}"
    work = BENCH / f"run_{tag}"
    work.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    for k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        env[k] = str(threads)
    cmd = [
        PY, "-m", "mace.cli.run_train", "--name", f"bench_{tag}",
        "--foundation_model", "small", "--multiheads_finetuning", "False",
        "--heads", repr(heads_cfg),
        "--energy_key", "REF_energy", "--forces_key", "REF_forces",
        "--stress_key", "REF_stress", "--compute_stress", "True",
        "--loss", "weighted", "--energy_weight", "1.0",
        "--forces_weight", "100.0", "--stress_weight", "1.0",
        "--lr", "1e-4", "--max_num_epochs", str(epochs), "--eval_interval", "1",
        "--batch_size", str(batch), "--valid_batch_size", str(max(batch, 8)),
        "--num_workers", str(workers), "--pin_memory", "False",
        "--device", "cpu", "--default_dtype", "float64",
        "--ema", "--ema_decay", "0.99", "--seed", "42",
        "--model_dir", str(work), "--log_dir", str(work / "logs"),
        "--checkpoints_dir", str(work / "ckpt"), "--results_dir", str(work / "res"),
        "--save_cpu",
    ]
    log_path = work / "out.log"
    t0 = time.time()
    proc = subprocess.Popen(cmd, cwd=str(work), env=env,
                            stdout=open(log_path, "w"), stderr=subprocess.STDOUT)
    sampler = RssSampler(proc.pid)
    sampler.start()
    rc = proc.wait()
    sampler.stop()
    wall = time.time() - t0

    # tiempo/época: deltas entre timestamps de "Epoch N:" consecutivos
    epoch_ts: dict[int, float] = {}
    logf = next(iter(work.glob("logs/*.log")), log_path)
    for line in Path(logf).read_text(errors="replace").splitlines():
        m = TS_RE.search(line)
        if m and int(m.group(2)) not in epoch_ts:
            epoch_ts[int(m.group(2))] = datetime.strptime(
                m.group(1), "%Y-%m-%d %H:%M:%S.%f").timestamp()
    eps = sorted(epoch_ts)
    deltas = [epoch_ts[b] - epoch_ts[a] for a, b in zip(eps[:-1], eps[1:])]
    sec_per_epoch = float(np.median(deltas)) if deltas else None
    return {"tag": tag, "threads": threads, "batch_size": batch, "num_workers": workers,
            "rc": rc, "wall_s": round(wall, 1),
            "sec_per_epoch": round(sec_per_epoch, 1) if sec_per_epoch else None,
            "peak_ram_gb": round(sampler.peak, 2), "epochs_logged": len(eps)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ram-cap", type=float, default=45.0,
                    help="pico de RAM (GiB) máximo permitido al elegir óptimo")
    ap.add_argument("--per-head", type=int, default=400, help="frames/cabeza en el bench")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--threads-grid", default="16,32,64")
    ap.add_argument("--batch-grid", default="4,8,16")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--launch-best", action="store_true",
                    help="tras elegir óptimo, lanza train_mlip.py completo en background")
    args = ap.parse_args()

    print("Construyendo set de benchmark (incluye estructuras grandes)…", flush=True)
    heads_cfg = build_bench_set(args.per_head)

    threads_grid = [int(x) for x in args.threads_grid.split(",")]
    batch_grid = [int(x) for x in args.batch_grid.split(",")]
    results = []
    print(f"\n{'config':18s} {'s/época':>9} {'pico_RAM_GB':>12} {'rc':>4}", flush=True)
    for th in threads_grid:
        for bs in batch_grid:
            r = run_config(heads_cfg, th, bs, args.workers, args.epochs)
            results.append(r)
            flag = "" if r["rc"] == 0 else "   FALLÓ"
            print(f"{r['tag']:18s} {str(r['sec_per_epoch']):>9} "
                  f"{r['peak_ram_gb']:>12} {r['rc']:>4}{flag}", flush=True)

    ok = [r for r in results if r["rc"] == 0 and r["sec_per_epoch"]]
    feasible = [r for r in ok if r["peak_ram_gb"] < args.ram_cap]
    pool = feasible or ok
    best = min(pool, key=lambda r: r["sec_per_epoch"]) if pool else None

    out = {"ram_cap_gb": args.ram_cap, "per_head": args.per_head,
           "results": results, "best": best,
           "note": "tiempo/época en set reducido — usar el RATIO entre configs"}
    (BENCH / "bench_results.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print("\n=== ÓPTIMO ===")
    print(json.dumps(best, indent=2, ensure_ascii=False))
    if not feasible:
        print(f"AVISO: ninguna config bajó de {args.ram_cap} GB; se eligió la más rápida igual.")

    if args.launch_best and best:
        print(f"\nLanzando entrenamiento completo con {best['tag']}…", flush=True)
        cmd = [PY, str(ROOT / "scripts/train_mlip.py"), "--tag", "mh_b000",
               "--epochs", "50", "--threads", str(best["threads"]),
               "--batch-size", str(best["batch_size"]),
               "--num-workers", str(best["num_workers"])]
        print(" ".join(cmd))
        print("(ejecuta este comando con run_in_background, o usa --launch-best desde un wrapper)")


if __name__ == "__main__":
    main()
