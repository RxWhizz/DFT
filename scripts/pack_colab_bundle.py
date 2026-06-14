#!/usr/bin/env python3
"""Empaqueta el set de entrenamiento del MLIP para entrenar en Google Colab (GPU).

Toma data/mlip_datasets/build/ (generado por build_mlip_training.py) y produce un bundle
autocontenido con:
  - data/<head>_{train,valid}.xyz   (los 6 archivos, copiados)
  - heads.json                       (RUTAS RELATIVAS: data/<head>_...xyz)
  - run_train.json                   (comando mace.cli.run_train listo, device=cuda fp32)
  - holdout_cssni3.xyz               (muestra para RMSE de sanidad en el notebook)
  - meta.json                        (versiones, hiperparámetros, conteos)

El comando se genera con build_mace_cmd() de train_mlip.py → MISMA fuente de verdad que el
entrenamiento local (sin drift de hiperparámetros). El notebook solo ejecuta run_train.json.

Uso:
  PYTHONPATH=src .venv/bin/python3 scripts/pack_colab_bundle.py [--batch 16] [--epochs 50]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tarfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ase.io import read, write  # noqa: E402

from train_mlip import build_mace_cmd  # type: ignore  # noqa: E402

BUILD = ROOT / "data" / "mlip_datasets" / "build"
DATASETS = ROOT / "data" / "mlip_datasets"
BUNDLE = ROOT / "data" / "mlip_datasets" / "colab_bundle"
TARBALL = ROOT / "data" / "mlip_datasets" / "colab_mlip_bundle.tar.gz"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="mh_b000")
    ap.add_argument("--epochs", type=int, default=50)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--batch", type=int, default=16,
                    help="batch en GPU (mayor que en CPU; T4 16GB aguanta float32)")
    ap.add_argument("--valid-batch", type=int, default=32)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--patience", type=int, default=15)
    ap.add_argument("--eval-interval", type=int, default=1)
    ap.add_argument("--holdout", type=int, default=300, help="frames de sanidad cssni3")
    args = ap.parse_args()

    heads = json.loads((BUILD / "heads.json").read_text())
    if not heads:
        raise SystemExit("build/heads.json vacío — corre build_mlip_training.py primero")

    if BUNDLE.exists():
        shutil.rmtree(BUNDLE)
    (BUNDLE / "data").mkdir(parents=True)

    # 1) copiar los 6 xyz + heads.json con rutas RELATIVAS
    rel_heads: dict = {}
    for head, cfg in heads.items():
        for split in ("train_file", "valid_file"):
            src = Path(cfg[split])
            dst = BUNDLE / "data" / src.name
            shutil.copy2(src, dst)
        rel_heads[head] = {
            "train_file": f"data/{Path(cfg['train_file']).name}",
            "valid_file": f"data/{Path(cfg['valid_file']).name}",
            "E0s": cfg.get("E0s", "average"),
        }
    (BUNDLE / "heads.json").write_text(json.dumps(rel_heads, indent=2))

    # 2) comando mace para Colab (cuda, float32, python="python", work="out")
    cmd = build_mace_cmd(
        rel_heads, f"phase2_mlip_{args.tag}", "out",
        epochs=args.epochs, lr=args.lr, batch=args.batch,
        valid_batch=args.valid_batch, workers=args.workers,
        patience=args.patience, eval_interval=args.eval_interval,
        device="cuda", dtype="float32", python_exe="python", save_cpu=True)
    (BUNDLE / "run_train.json").write_text(json.dumps(cmd, indent=2))

    # 3) holdout de sanidad (muestra de cssni3.extxyz, mapeada a REF_*)
    src_holdout = DATASETS / "cssni3.extxyz"
    if src_holdout.exists() and args.holdout > 0:
        frames = read(str(src_holdout), index=":")
        rng = np.random.RandomState(123)
        if len(frames) > args.holdout:
            frames = [frames[int(i)] for i in sorted(rng.permutation(len(frames))[:args.holdout])]
        for at in frames:
            r = at.calc.results if at.calc is not None else {}
            if "energy" in r:
                at.info["REF_energy"] = float(r["energy"])
            if "forces" in r:
                at.arrays["REF_forces"] = np.asarray(r["forces"], float)
            at.info["head"] = "cssni3"
            at.calc = None
        write(str(BUNDLE / "holdout_cssni3.xyz"), frames, format="extxyz")

    # 4) meta para trazabilidad
    import mace
    meta = {"tag": args.tag, "mace_torch": mace.__version__,
            "device": "cuda", "dtype": "float32",
            "hyperparams": {"epochs": args.epochs, "lr": args.lr, "batch": args.batch,
                            "valid_batch": args.valid_batch, "patience": args.patience,
                            "eval_interval": args.eval_interval},
            "heads": {h: {"train": len(read(c["train_file"], index=":")),
                          "valid": len(read(c["valid_file"], index=":"))}
                      for h, c in heads.items()}}
    (BUNDLE / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))

    # 5) tarball
    with tarfile.open(TARBALL, "w:gz") as tar:
        tar.add(BUNDLE, arcname="colab_bundle")
    size_mb = TARBALL.stat().st_size / 1e6

    print(json.dumps(meta, indent=2, ensure_ascii=False))
    print(f"\n→ {TARBALL}  ({size_mb:.1f} MB)")
    print("\nSiguiente:")
    print("  1. Sube el tarball a Google Drive: MyDrive/mlip_colab/")
    print("  2. Abre notebooks/train_mlip_colab.ipynb en Colab (Runtime → GPU)")
    print("  3. Ejecuta las celdas; el modelo queda en MyDrive/mlip_colab/output/")
    print("  4. Baja el .model y corre: scripts/fetch_colab_model.py + eval_mlip.py")


if __name__ == "__main__":
    main()
