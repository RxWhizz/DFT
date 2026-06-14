#!/usr/bin/env python3
"""Construye el set de entrenamiento multi-cabeza del MLIP a partir de:

  cabeza 'phase2a'   — nuestros 812 frames DFT PBE (local_runs/phase2_force), dominio objetivo
  cabeza 'cssni3'    — data/mlip_datasets/cssni3.extxyz   (breadth, FHI-aims all-electron)
  cabeza 'perovsiap' — data/mlip_datasets/perovsiap.extxyz (breadth, VASP PBE)

Cada cabeza tiene su propia referencia de energía (E0s="average", ajuste de energías de
átomo aislado por mínimos cuadrados sobre los datos de esa cabeza) — así se combinan
fuentes con referencias absolutas distintas (all-electron vs PAW). Las fuerzas/stress se
comparten en el cuerpo del modelo.

Salida en data/mlip_datasets/build/:
  <head>_train.xyz, <head>_valid.xyz  (claves REF_energy/REF_forces/REF_stress, head=<head>)
  heads.json   — config para mace.cli.run_train (--heads)
  manifest.json — conteos por cabeza, procedencia, split

Uso:
  PYTHONPATH=src .venv/bin/python3 scripts/build_mlip_training.py [--smoke] [--valid-frac 0.2]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from ase.io import read, write  # noqa: E402

from phase2_mace_train import collect_phase2_frames  # type: ignore  # noqa: E402

DATASETS = ROOT / "data" / "mlip_datasets"
BUILD = DATASETS / "build"

PUBLIC_HEADS = {
    "cssni3": DATASETS / "cssni3.extxyz",
    "perovsiap": DATASETS / "perovsiap.extxyz",
}


def in_valid(key: str, valid_frac: float) -> bool:
    digest = int(hashlib.sha1(key.encode()).hexdigest()[:8], 16)
    return (digest % 100) < (valid_frac * 100)


def load_public_head(path: Path, head: str, valid_frac: float, smoke: bool):
    """Lee un extxyz público (con SinglePointCalculator) → (train, valid) con REF_*."""
    frames = read(str(path), index=":")
    train, valid = [], []
    for i, at in enumerate(frames):
        res = at.calc.results if at.calc is not None else {}
        e, f = res.get("energy"), res.get("forces")
        if e is None or f is None:
            continue
        at.info["REF_energy"] = float(e)
        at.arrays["REF_forces"] = np.asarray(f, dtype=float)
        s = res.get("stress")
        if s is not None:
            at.info["REF_stress"] = np.asarray(s, dtype=float)
        at.info["head"] = head
        at.calc = None
        # split estable por nombre de estructura si existe, si no por hash de energía
        key = str(at.info.get("struct_name") or f"{head}:{round(float(e), 5)}:{i}")
        (valid if in_valid(key, valid_frac) else train).append(at)
        if smoke and (len(train) + len(valid)) >= 100:
            break
    return train, valid


def tag_phase2a(frames: list, head: str = "phase2a") -> list:
    for at in frames:
        at.info["head"] = head
    return frames


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--valid-frac", type=float, default=0.2)
    ap.add_argument("--smoke", action="store_true",
                    help="≤100 frames/cabeza para validar plumbing")
    args = ap.parse_args()

    BUILD.mkdir(parents=True, exist_ok=True)
    heads_cfg: dict = {}
    manifest: dict = {"valid_frac": args.valid_frac, "smoke": args.smoke, "heads": {}}

    # ── cabeza target: phase2a (nuestros frames) ──
    p2_train, p2_valid = collect_phase2_frames()
    if args.smoke:
        p2_train, p2_valid = p2_train[:80], (p2_valid[:20] or p2_train[-20:])
    tag_phase2a(p2_train)
    tag_phase2a(p2_valid)
    tp = BUILD / "phase2a_train.xyz"
    vp = BUILD / "phase2a_valid.xyz"
    write(str(tp), p2_train, format="extxyz")
    write(str(vp), p2_valid, format="extxyz")
    heads_cfg["phase2a"] = {"train_file": str(tp), "valid_file": str(vp), "E0s": "average"}
    manifest["heads"]["phase2a"] = {"train": len(p2_train), "valid": len(p2_valid),
                                    "source": "local_runs/phase2_force (PBE GPAW)"}
    print(f"phase2a: {len(p2_train)} train / {len(p2_valid)} valid", flush=True)

    # ── cabezas breadth: cssni3, perovsiap ──
    for head, path in PUBLIC_HEADS.items():
        if not path.exists():
            print(f"  AVISO: {path} no existe — omito cabeza '{head}'", flush=True)
            continue
        tr, va = load_public_head(path, head, args.valid_frac, args.smoke)
        if not va:                       # garantizar valid no vacío
            va = tr[-max(1, len(tr) // 10):]
        tp = BUILD / f"{head}_train.xyz"
        vp = BUILD / f"{head}_valid.xyz"
        write(str(tp), tr, format="extxyz")
        write(str(vp), va, format="extxyz")
        heads_cfg[head] = {"train_file": str(tp), "valid_file": str(vp), "E0s": "average"}
        stats = json.loads((path.with_name(path.stem + "_stats.json")).read_text()) \
            if (path.with_name(path.stem + "_stats.json")).exists() else {}
        manifest["heads"][head] = {"train": len(tr), "valid": len(va),
                                   "dft_level": stats.get("head") and stats.get(
                                       "frames_written") and stats.get("source"),
                                   "source": str(path.name)}
        print(f"{head}: {len(tr)} train / {len(va)} valid", flush=True)

    (BUILD / "heads.json").write_text(json.dumps(heads_cfg, indent=2))
    manifest["total_train"] = sum(h["train"] for h in manifest["heads"].values())
    manifest["total_valid"] = sum(h["valid"] for h in manifest["heads"].values())
    (BUILD / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"\n→ {BUILD}/heads.json  ({len(heads_cfg)} cabezas)")


if __name__ == "__main__":
    main()
