#!/usr/bin/env python3
"""Trae el modelo MLIP entrenado en Colab al repo local, listo para eval/validate.

Copia el .model (bajado de Drive) a models/mace_phase2/phase2_mlip_<tag>.model y escribe un
stub en reports/training fase 2/mlip_metrics.json. Si junto al modelo hay logs de MACE,
también los copia a models/mace_phase2/mlip_<tag>/logs para que eval_mlip.py pueda dibujar
las curvas de aprendizaje.

Uso:
  python scripts/fetch_colab_model.py --model ~/Downloads/phase2_mlip_mh_b000.model --tag mh_b000
  # o apuntando a la carpeta de salida de Drive:
  python scripts/fetch_colab_model.py --from-dir ~/Drive/mlip_colab/output --tag mh_b000
"""
from __future__ import annotations

import argparse
import glob
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models" / "mace_phase2"
METRICS = ROOT / "reports" / "training fase 2" / "mlip_metrics.json"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="mh_b000")
    ap.add_argument("--model", help="ruta al .model bajado de Drive")
    ap.add_argument("--from-dir", help="carpeta de salida de Colab (busca el .model y logs)")
    args = ap.parse_args()

    # localizar el modelo
    if args.model:
        src = Path(args.model).expanduser()
    elif args.from_dir:
        d = Path(args.from_dir).expanduser()
        cands = [m for m in d.glob("*.model") if "compiled" not in m.name]
        if not cands:
            raise SystemExit(f"No hay .model (no-compiled) en {d}")
        src = max(cands, key=lambda p: p.stat().st_mtime)
    else:
        raise SystemExit("Da --model <archivo> o --from-dir <carpeta>")
    if not src.exists():
        raise SystemExit(f"No existe {src}")

    MODELS.mkdir(parents=True, exist_ok=True)
    dst = MODELS / f"phase2_mlip_{args.tag}.model"
    shutil.copy2(src, dst)
    print(f"modelo → {dst}  ({dst.stat().st_size/1e6:.1f} MB)")

    # logs (para curvas de aprendizaje en eval_mlip.py)
    logs_src = []
    if args.from_dir:
        logs_src = glob.glob(str(Path(args.from_dir).expanduser() / "*.log"))
    if logs_src:
        logdir = MODELS / f"mlip_{args.tag}" / "logs"
        logdir.mkdir(parents=True, exist_ok=True)
        for lg in logs_src:
            shutil.copy2(lg, logdir)
        print(f"logs → {logdir} ({len(logs_src)} archivos)")

    # stub de métricas
    METRICS.parent.mkdir(parents=True, exist_ok=True)
    METRICS.write_text(json.dumps({
        "status": "fetched_from_colab", "tag": args.tag, "model": str(dst),
        "dtype": "float32", "trained_on": "colab_gpu",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2, ensure_ascii=False))
    print(f"metrics stub → {METRICS}")
    print(f"\nSiguiente:\n"
          f"  PYTHONPATH=src .venv/bin/python3 scripts/eval_mlip.py --tag {args.tag} --dtype float32 --baseline\n"
          f"  PYTHONPATH=src .venv/bin/python3 scripts/validate_mlip.py --tag {args.tag} --dtype float32")


if __name__ == "__main__":
    main()
