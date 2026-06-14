#!/usr/bin/env python3
"""Monitor: espera a que termine el entrenamiento del MLIP y notifica a Telegram.

Vigila el .model final y reports/training fase 2/mlip_metrics.json. Al detectar que el
entrenamiento terminó (o falló), envía un resumen con RMSE_E/RMSE_F y nº de épocas al chat
de Telegram de configs/monitor.local.yaml. Reusa load_telegram/send de notify_bench_done.

Uso (background):
  PYTHONPATH=src .venv/bin/python3 scripts/notify_train_done.py --tag mh_b000
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from notify_bench_done import load_telegram, send  # type: ignore  # noqa: E402

MODELS = ROOT / "models" / "mace_phase2"
METRICS = ROOT / "reports" / "training fase 2" / "mlip_metrics.json"
EPOCH_RE = re.compile(r"Epoch (\d+):.*head: phase2a.*RMSE_E_per_atom=\s*([\d.eE+-]+)\s*meV"
                      r".*RMSE_F=\s*([\d.eE+-]+)\s*meV")


def last_epoch_metrics(tag: str) -> dict | None:
    logs = sorted((MODELS / f"mlip_{tag}" / "logs").glob("*.log"))
    if not logs:
        return None
    best = None
    for line in logs[-1].read_text(errors="replace").splitlines():
        m = EPOCH_RE.search(line)
        if m:
            best = {"epoch": int(m.group(1)), "rmse_e_meV": float(m.group(2)),
                    "rmse_f_meV": float(m.group(3))}
    return best


def train_running() -> bool:
    try:
        import subprocess
        out = subprocess.run(["pgrep", "-f", "mace.cli.run_train"],
                             capture_output=True, text=True)
        return bool(out.stdout.strip())
    except Exception:
        return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="mh_b000")
    ap.add_argument("--poll", type=int, default=120)
    ap.add_argument("--timeout-h", type=float, default=40.0)
    args = ap.parse_args()

    token, chat_id = load_telegram()
    model = MODELS / f"phase2_mlip_{args.tag}.model"
    print(f"Vigilando entrenamiento tag={args.tag} (poll {args.poll}s)…", flush=True)
    t0 = time.time()
    # esperar a que arranque (proceso vivo) y luego a que termine
    time.sleep(10)
    while True:
        if model.exists() and not train_running():
            time.sleep(5)
            break
        if not train_running() and time.time() - t0 > 300:
            # proceso murió sin modelo → fallo
            send(token, chat_id, f"❌ Entrenamiento MLIP <b>{args.tag}</b> terminó SIN modelo "
                                 f"(revisa el log). {datetime.now():%H:%M}")
            return
        if time.time() - t0 > args.timeout_h * 3600:
            send(token, chat_id, f"⚠️ Monitor entrenamiento {args.tag}: timeout.")
            return
        time.sleep(args.poll)

    # resumen
    lines = [f"✅ <b>Entrenamiento MLIP terminado</b> ({args.tag})", ""]
    if METRICS.exists():
        try:
            m = json.loads(METRICS.read_text())
            lines.append(f"modelo: <code>{Path(m.get('model','')).name}</code>")
            lines.append(f"épocas: {m.get('epochs')}  ·  cabezas: {m.get('heads')}")
            lines.append(f"n_train: {m.get('n_train')}")
            if m.get("rmse_e_eV_atom") is not None:
                lines.append(f"RMSE_E (valid phase2a): "
                             f"{m['rmse_e_eV_atom']*1000:.1f} meV/átomo")
            if m.get("rmse_f_eV_A") is not None:
                lines.append(f"RMSE_F (valid phase2a): {m['rmse_f_eV_A']*1000:.1f} meV/Å")
        except Exception as exc:
            lines.append(f"(no pude leer mlip_metrics.json: {exc})")
    le = last_epoch_metrics(args.tag)
    if le:
        lines.append(f"última época {le['epoch']}: RMSE_E={le['rmse_e_meV']:.1f} meV, "
                     f"RMSE_F={le['rmse_f_meV']:.1f} meV/Å")
    lines.append("")
    lines.append("Siguiente: eval_mlip + validate_mlip.")
    lines.append(f"<i>{datetime.now():%Y-%m-%d %H:%M}</i>")
    report = "\n".join(lines)
    print(report, flush=True)
    send(token, chat_id, report)


if __name__ == "__main__":
    main()
