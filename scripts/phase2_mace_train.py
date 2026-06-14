#!/usr/bin/env python3
"""Fine-tuning de MACE con los datos DFT de Fase 2A (capa 2), entre batches.

Curriculum de 2 capas:
  capa 1 — subconjunto ABX3-haluro de MPtrj (E+F+stress, mismo nivel que MACE-MP-0);
           se usa como REPLAY (anti-olvido) mezclado con nuestros datos.
  capa 2 — nuestros single-points PBE rattled (local_runs/phase2_force/batch_*).

Recolecta frames de jobs converged/partial, normaliza claves a REF_* (robusto para
mace_run_train), separa train/valid por candidate_id (hash estable), añade replay de
capa 1 si existe, y lanza fine-tuning naive (multihead OFF) desde el foundation o desde
el último checkpoint propio. Al final evalúa RMSE en valid y anexa a la curva de
aprendizaje (mismo patrón que el surrogate de Fase 1).

Uso:
  PYTHONPATH=src .venv/bin/python3 scripts/phase2_mace_train.py [--smoke] [--tag b000]
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ase.io import read, write  # noqa: E402

from buho.phase2_force.common import split_for_candidate  # noqa: E402

RUNS = ROOT / "local_runs" / "phase2_force"
MODELS = ROOT / "models" / "mace_phase2"
LAYER1_DEFAULT = Path("/media/luis-ochoa/Nuevo vol/dft/datasets/mptrj_abx3_halides.extxyz")
CURVE_CSV = MODELS / "learning_curve.csv"
METRICS_JSON = ROOT / "reports" / "training fase 2" / "mace_phase2_metrics.json"


def collect_phase2_frames(include_running: bool = False) -> tuple[list, list]:
    """Devuelve (train, valid) de frames con claves REF_* desde los batches locales."""
    train, valid = [], []
    for st_path in sorted(RUNS.glob("batch_*/*/status.json")):
        try:
            st = json.loads(st_path.read_text())
        except Exception:
            continue
        ok = st.get("status") in {"converged", "partial"}
        if include_running:
            ok = ok or st.get("status") == "running"
        if not ok:
            continue
        job = st_path.parent
        xyz = job / "pbe" / "label.extxyz"
        if not xyz.exists() or xyz.stat().st_size == 0:
            continue
        cid = st.get("candidate_id") or job.name
        bucket = valid if split_for_candidate(cid) == "test" else train
        try:
            frames = read(str(xyz), index=":")
        except Exception:
            continue
        for at in frames:
            res = at.calc.results if at.calc is not None else {}
            e = res.get("energy", at.info.get("energy"))
            f = res.get("forces")
            if e is None or f is None:
                continue
            at.info["REF_energy"] = float(e)
            at.arrays["REF_forces"] = np.asarray(f, dtype=float)
            s = res.get("stress", at.info.get("stress"))
            if s is not None:
                at.info["REF_stress"] = np.asarray(s, dtype=float)
            at.info["config_type"] = "phase2_dft"
            at.calc = None
            bucket.append(at)
    return train, valid


def load_layer1_replay(path: Path, n_max: int, seed: int = 42) -> list:
    """Submuestra frames de capa 1 (ya traen energy/forces/stress en el header)."""
    if not path.exists() or n_max <= 0:
        return []
    frames = read(str(path), index=":")
    rng = np.random.RandomState(seed)
    idx = rng.permutation(len(frames))[:n_max]
    out = []
    for i in idx:
        at = frames[int(i)]
        res = at.calc.results if at.calc is not None else {}
        e = res.get("energy", at.info.get("energy"))
        f = res.get("forces")
        if e is None or f is None:
            continue
        at.info["REF_energy"] = float(e)
        at.arrays["REF_forces"] = np.asarray(f, dtype=float)
        s = res.get("stress", at.info.get("stress"))
        if s is not None:
            at.info["REF_stress"] = np.asarray(s, dtype=float)
        at.info["config_type"] = "mptrj_replay"
        at.calc = None
        out.append(at)
    return out


def latest_own_checkpoint() -> Path | None:
    cands = sorted(MODELS.glob("phase2_ft_*.model"), key=lambda p: p.stat().st_mtime)
    return cands[-1] if cands else None


def evaluate(model: Path, frames: list, workdir: Path) -> dict:
    """RMSE E/átomo y F con mace_eval_configs sobre el set de validación."""
    if not frames:
        return {}
    xyz = workdir / "eval_in.extxyz"
    out = workdir / "eval_out.extxyz"
    write(str(xyz), frames, format="extxyz")
    # python -m: los entry-points del venv tienen shebang roto (venv movido de ruta)
    cmd = [str(ROOT / ".venv/bin/python3"), "-m", "mace.cli.eval_configs",
           "--configs", str(xyz), "--model", str(model), "--output", str(out),
           "--device", "cpu", "--default_dtype", "float64", "--batch_size", "4"]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    preds = read(str(out), index=":")
    de, df = [], []
    for ref, pr in zip(frames, preds):
        n = len(ref)
        e_pred = pr.info.get("MACE_energy", pr.calc.results.get("energy") if pr.calc else None)
        f_pred = pr.arrays.get("MACE_forces", pr.calc.results.get("forces") if pr.calc else None)
        if e_pred is None or f_pred is None:
            continue
        de.append((float(e_pred) - ref.info["REF_energy"]) / n)
        df.append(np.asarray(f_pred, float) - ref.arrays["REF_forces"])
    if not de:
        return {}
    rmse_e = float(np.sqrt(np.mean(np.square(de))))
    rmse_f = float(np.sqrt(np.mean(np.concatenate([d.ravel() for d in df]) ** 2)))
    return {"rmse_e_eV_atom": round(rmse_e, 5), "rmse_f_eV_A": round(rmse_f, 4),
            "n_valid_frames": len(de)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default=datetime.now().strftime("%Y%m%dT%H%M"))
    ap.add_argument("--layer1", default=str(LAYER1_DEFAULT))
    ap.add_argument("--layer1-max", type=int, default=2000,
                    help="frames de replay capa 1 (0 = sin replay)")
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--threads", type=int, default=6)
    ap.add_argument("--from-foundation", action="store_true",
                    help="ignora checkpoints propios y parte del foundation 'small'")
    ap.add_argument("--include-running", action="store_true")
    ap.add_argument("--smoke", action="store_true", help="2 epochs, sin replay, validación de plumbing")
    args = ap.parse_args()

    os.environ.setdefault("OMP_NUM_THREADS", str(args.threads))
    os.environ.setdefault("MKL_NUM_THREADS", str(args.threads))
    import torch
    torch.set_num_threads(args.threads)

    MODELS.mkdir(parents=True, exist_ok=True)
    work = MODELS / f"run_{args.tag}"
    work.mkdir(parents=True, exist_ok=True)

    train, valid = collect_phase2_frames(include_running=args.include_running or args.smoke)
    print(f"capa 2: {len(train)} train / {len(valid)} valid frames", flush=True)
    if len(train) < (1 if args.smoke else 40):
        raise SystemExit("Pocos frames de capa 2 — espera a que converjan más jobs.")
    if not valid:                       # en smoke puede no haber split test aún
        valid = train[-1:]

    replay = [] if args.smoke else load_layer1_replay(Path(args.layer1), args.layer1_max)
    if replay:
        print(f"capa 1 (replay): {len(replay)} frames de {args.layer1}", flush=True)

    train_xyz = work / "train.extxyz"
    valid_xyz = work / "valid.extxyz"
    write(str(train_xyz), train + replay, format="extxyz")
    write(str(valid_xyz), valid, format="extxyz")

    start_model = None if args.from_foundation else latest_own_checkpoint()
    epochs = 2 if args.smoke else args.epochs
    name = f"phase2_ft_{args.tag}"
    cmd = [
        str(ROOT / ".venv/bin/python3"), "-m", "mace.cli.run_train",
        "--name", name,
        "--train_file", str(train_xyz),
        "--valid_file", str(valid_xyz),
        "--energy_key", "REF_energy", "--forces_key", "REF_forces",
        "--E0s", "foundation",
        "--loss", "weighted", "--energy_weight", "1.0", "--forces_weight", "100.0",
        "--lr", str(args.lr), "--max_num_epochs", str(epochs),
        "--batch_size", "2", "--valid_batch_size", "4",
        "--device", "cpu", "--default_dtype", "float64",
        "--ema", "--ema_decay", "0.99", "--patience", "25",
        "--seed", "42",
        "--model_dir", str(work), "--log_dir", str(work / "logs"),
        "--checkpoints_dir", str(work / "checkpoints"), "--results_dir", str(work / "results"),
        "--save_cpu",
    ]
    if start_model is not None:
        print(f"continuando desde checkpoint propio: {start_model.name}", flush=True)
        cmd += ["--foundation_model", str(start_model), "--multiheads_finetuning", "False"]
    else:
        print("fine-tuning naive desde foundation MACE-MP-0 small", flush=True)
        cmd += ["--foundation_model", "small", "--multiheads_finetuning", "False"]
    if any("REF_stress" in at.info for at in train[:5]):
        cmd += ["--compute_stress", "True", "--stress_key", "REF_stress",
                "--stress_weight", "1.0"]

    print(" ".join(cmd), flush=True)
    res = subprocess.run(cmd, cwd=str(work), text=True,
                         stdout=open(work / "train_stdout.log", "w"),
                         stderr=subprocess.STDOUT)
    if res.returncode != 0:
        tail = (work / "train_stdout.log").read_text()[-2000:]
        raise SystemExit(f"mace_run_train falló (rc={res.returncode}):\n{tail}")

    produced = sorted(work.glob("*.model"), key=lambda p: p.stat().st_mtime)
    if not produced:
        raise SystemExit("entrenó pero no se encontró .model en " + str(work))
    final = MODELS / f"{name}.model"
    final.write_bytes(produced[-1].read_bytes())
    print(f"modelo: {final}", flush=True)

    metrics = evaluate(final, valid, work)
    row = {"tag": args.tag, "n_train": len(train), "n_replay": len(replay),
           "n_valid": len(valid), "epochs": epochs,
           "from": (start_model.name if start_model else "foundation_small"),
           **metrics, "finished_at": datetime.now(timezone.utc).isoformat()}
    new_file = not CURVE_CSV.exists()
    with CURVE_CSV.open("a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(row.keys()))
        if new_file:
            w.writeheader()
        w.writerow(row)
    METRICS_JSON.write_text(json.dumps({
        "status": "trained", "model": str(final), **row}, indent=2))
    print(json.dumps(row, indent=2))


if __name__ == "__main__":
    main()
