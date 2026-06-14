#!/usr/bin/env python3
"""Watcher: entrena MACE automáticamente cuando se completa cada batch de Fase 2A.

Cada 10 min revisa local_runs/phase2_force/batch_*: un batch está "completo" cuando no
le quedan jobs pending/running (skipped_duplicate cuenta como terminal) y tiene ≥1
converged. Si el conjunto de batches completos creció desde el último entrenamiento,
lanza scripts/phase2_mace_train.py (hilos limitados — convive con el DFT del batch
siguiente). Estado en models/mace_phase2/cycle_state.json.

Uso (background): nohup .venv/bin/python3 scripts/phase2_mace_cycle.py &
"""
from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "local_runs" / "phase2_force"
STATE = ROOT / "models" / "mace_phase2" / "cycle_state.json"
POLL_S = 600
TRAIN_THREADS = 6

TERMINAL = {"converged", "partial", "failed", "skipped_duplicate"}


def batch_complete(batch_dir: Path) -> bool:
    statuses = []
    for st_path in batch_dir.glob("*/status.json"):
        try:
            statuses.append(json.loads(st_path.read_text()).get("status"))
        except Exception:
            return False
    if not statuses:
        return False
    if any(s not in TERMINAL for s in statuses):
        return False
    return any(s in {"converged", "partial"} for s in statuses)


def load_state() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text())
        except Exception:
            pass
    return {"trained_for": []}


def main() -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    print(f"[{datetime.now():%F %T}] mace-cycle iniciado (poll {POLL_S}s)", flush=True)
    while True:
        state = load_state()
        done = sorted(b.name for b in RUNS.glob("batch_*") if batch_complete(b))
        new = [b for b in done if b not in state["trained_for"]]
        if new:
            tag = new[-1].replace("batch_", "b")
            print(f"[{datetime.now():%F %T}] batches nuevos completos: {new} → "
                  f"entrenando (tag={tag})", flush=True)
            cmd = ["env", f"OMP_NUM_THREADS={TRAIN_THREADS}",
                   str(ROOT / ".venv/bin/python3"),
                   str(ROOT / "scripts/phase2_mace_train.py"),
                   "--tag", tag, "--threads", str(TRAIN_THREADS)]
            res = subprocess.run(cmd, cwd=str(ROOT), text=True,
                                 env=None, capture_output=True)
            log = ROOT / "logs" / f"mace_train_{tag}.log"
            log.write_text((res.stdout or "") + "\n--- stderr ---\n" + (res.stderr or ""))
            if res.returncode == 0:
                state["trained_for"] = sorted(set(state["trained_for"]) | set(done))
                state["last_train"] = {"tag": tag,
                                       "at": datetime.now(timezone.utc).isoformat()}
                STATE.write_text(json.dumps(state, indent=2))
                print(f"[{datetime.now():%F %T}] entrenamiento {tag} OK → {log}", flush=True)
            else:
                print(f"[{datetime.now():%F %T}] entrenamiento {tag} FALLÓ "
                      f"(rc={res.returncode}) → {log}; reintento en el próximo poll",
                      flush=True)
        time.sleep(POLL_S)


if __name__ == "__main__":
    main()
