#!/usr/bin/env python3
"""Fine-tuning MULTI-CABEZA de MACE-MP-0 para el MLIP de perovskitas ABX₃.

Lee data/mlip_datasets/build/heads.json (generado por build_mlip_training.py) y entrena
un modelo de varias cabezas sobre el foundation MACE-MP-0 'small':

  cabeza 'phase2a'   — dominio objetivo (nuestros frames PBE GPAW)
  cabeza 'cssni3'    — breadth (FHI-aims all-electron)
  cabeza 'perovsiap' — breadth (VASP PBE)

Cada cabeza tiene su propio E0s ("average") → combina referencias de energía distintas;
el cuerpo (representación) y las fuerzas/stress se comparten. Loss ponderado con las
fuerzas como señal principal (forces_weight=100). Al terminar evalúa RMSE en la valid de
la cabeza target y anexa a la curva de aprendizaje.

Uso:
  PYTHONPATH=src .venv/bin/python3 scripts/train_mlip.py [--smoke] [--tag mh001]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ase.io import read  # noqa: E402

from phase2_mace_train import evaluate  # type: ignore  # noqa: E402

BUILD = ROOT / "data" / "mlip_datasets" / "build"
MODELS = ROOT / "models" / "mace_phase2"
CURVE_CSV = MODELS / "mlip_learning_curve.csv"
METRICS_JSON = ROOT / "reports" / "training fase 2" / "mlip_metrics.json"
TARGET_HEAD = "phase2a"


def build_mace_cmd(heads: dict, name: str, work, *, epochs: int, lr: float,
                   batch: int, valid_batch: int, workers: int, patience: int,
                   eval_interval: int, device: str, dtype: str,
                   python_exe: str | None = None, mh_replay: bool = False,
                   save_cpu: bool = True) -> list[str]:
    """Construye el comando mace.cli.run_train — FUENTE ÚNICA (local CPU y Colab GPU).

    `heads` se serializa con repr() para --heads (mace lo parsea con ast.literal_eval).
    Para Colab: python_exe="python", device="cuda", dtype="float32", rutas relativas en
    `heads` y `work`. El comando se vuelca a JSON y el notebook lo ejecuta tal cual.
    """
    py = python_exe or str(ROOT / ".venv/bin/python3")
    work = str(work)
    cmd = [
        py, "-m", "mace.cli.run_train",
        "--name", name,
        "--foundation_model", "small",
        "--multiheads_finetuning", "True" if mh_replay else "False",
        "--heads", repr(heads),
        "--energy_key", "REF_energy", "--forces_key", "REF_forces",
        "--stress_key", "REF_stress", "--compute_stress", "True",
        "--loss", "weighted",
        "--energy_weight", "1.0", "--forces_weight", "100.0", "--stress_weight", "1.0",
        "--lr", str(lr), "--max_num_epochs", str(epochs),
        "--batch_size", str(batch), "--valid_batch_size", str(valid_batch),
        "--num_workers", str(workers), "--pin_memory", "False",
        "--device", device, "--default_dtype", dtype,
        "--eval_interval", str(eval_interval),
        "--ema", "--ema_decay", "0.99", "--patience", str(patience), "--seed", "42",
        "--model_dir", work, "--log_dir", f"{work}/logs",
        "--checkpoints_dir", f"{work}/checkpoints", "--results_dir", f"{work}/results",
    ]
    if save_cpu:
        cmd.append("--save_cpu")
    return cmd


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default=datetime.now().strftime("%Y%m%dT%H%M"))
    ap.add_argument("--heads-json", default=str(BUILD / "heads.json"))
    ap.add_argument("--epochs", type=int, default=50)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--threads", type=int, default=32,
                    help="threads intra-op torch/OMP (88 cores; no cuestan RAM)")
    ap.add_argument("--batch-size", type=int, default=8,
                    help="moderado: hay estructuras de hasta 324 átomos (anti-OOM con 62GB)")
    ap.add_argument("--valid-batch-size", type=int, default=16)
    ap.add_argument("--num-workers", type=int, default=4,
                    help="dataloader workers; pocos para no replicar memoria (anti-OOM)")
    ap.add_argument("--patience", type=int, default=15,
                    help="early-stop: épocas sin mejora en valid antes de cortar")
    ap.add_argument("--eval-interval", type=int, default=1,
                    help="evaluar cada N épocas (1 → early-stop reacciona pronto)")
    ap.add_argument("--device", default="cpu", choices=["cpu", "cuda"],
                    help="cpu local; cuda en GPU (Colab)")
    ap.add_argument("--dtype", default="float32", choices=["float32", "float64"],
                    help="float32 (GPU, rápido) o float64 (legacy CPU)")
    ap.add_argument("--mh-replay", action="store_true",
                    help="añade pt_head (replay del foundation MP); más costoso en CPU")
    ap.add_argument("--smoke", action="store_true", help="2 épocas, validación de plumbing")
    args = ap.parse_args()

    # Forzar (no setdefault) para que el subproceso mace herede el valor alto.
    os.environ["OMP_NUM_THREADS"] = str(args.threads)
    os.environ["MKL_NUM_THREADS"] = str(args.threads)
    os.environ["OPENBLAS_NUM_THREADS"] = str(args.threads)
    import torch
    torch.set_num_threads(args.threads)

    heads = json.loads(Path(args.heads_json).read_text())
    if not heads:
        raise SystemExit(f"heads.json vacío en {args.heads_json}")
    # Cada cabeza ya trae train_file/valid_file/E0s. Stringify para --heads (ast.literal_eval).
    heads_arg = repr(heads)

    MODELS.mkdir(parents=True, exist_ok=True)
    work = MODELS / f"mlip_{args.tag}"
    work.mkdir(parents=True, exist_ok=True)
    epochs = 2 if args.smoke else args.epochs
    name = f"phase2_mlip_{args.tag}"

    cmd = build_mace_cmd(
        heads, name, work, epochs=epochs, lr=args.lr, batch=args.batch_size,
        valid_batch=args.valid_batch_size, workers=args.num_workers,
        patience=args.patience, eval_interval=args.eval_interval,
        device=args.device, dtype=args.dtype, mh_replay=args.mh_replay)
    _ = heads_arg  # heads serializado dentro de build_mace_cmd
    print(" ".join(cmd[:6]), "... (heads:", list(heads), f"device={args.device})", flush=True)
    res = subprocess.run(cmd, cwd=str(work), text=True,
                         stdout=open(work / "train_stdout.log", "w"),
                         stderr=subprocess.STDOUT)
    if res.returncode != 0:
        tail = (work / "train_stdout.log").read_text()[-3000:]
        raise SystemExit(f"mace run_train falló (rc={res.returncode}):\n{tail}")

    produced = sorted(work.glob("*.model"), key=lambda p: p.stat().st_mtime)
    if not produced:
        raise SystemExit("entrenó pero no se encontró .model en " + str(work))
    final = MODELS / f"{name}.model"
    final.write_bytes(produced[-1].read_bytes())
    print(f"modelo: {final}", flush=True)

    # Evaluar sobre la valid de la cabeza target (phase2a) con claves REF_*.
    valid_path = Path(heads[TARGET_HEAD]["valid_file"])
    valid = read(str(valid_path), index=":")
    for at in valid:
        res2 = at.calc.results if at.calc is not None else {}
        if "energy" in res2:
            at.info["REF_energy"] = float(res2["energy"])
        if "forces" in res2:
            import numpy as np
            at.arrays["REF_forces"] = np.asarray(res2["forces"], float)
        at.calc = None
    try:
        metrics = evaluate(final, valid, work)   # nota: evaluate() usa float64
    except Exception as exc:
        print(f"(eval inline omitido: {exc})", flush=True)
        metrics = {}

    row = {"tag": args.tag, "heads": ",".join(heads), "epochs": epochs,
           "n_train": sum(len(read(str(h["train_file"]), index=":")) for h in heads.values()),
           "target_head": TARGET_HEAD, "n_valid_target": len(valid),
           **metrics, "finished_at": datetime.now(timezone.utc).isoformat()}
    new_file = not CURVE_CSV.exists()
    with CURVE_CSV.open("a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(row.keys()))
        if new_file:
            w.writeheader()
        w.writerow(row)
    METRICS_JSON.parent.mkdir(parents=True, exist_ok=True)
    METRICS_JSON.write_text(json.dumps({"status": "trained", "model": str(final), **row},
                                       indent=2, ensure_ascii=False))
    print(json.dumps(row, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
