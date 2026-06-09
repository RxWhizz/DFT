#!/bin/bash
# Relanza el loop de active learning BUHO tras apagón/reinicio.
# Idempotente: si ya hay monitor corriendo, no duplica.
# Sin sudo: corre como el usuario (apto para crontab @reboot).
set -u
PROJ="/home/luis-ochoa/Documents/Vscode/py/dft"
PY="$PROJ/.venv/bin/python3"
RUNS_ROOT="${DFT_RUNS_ROOT:-/media/luis-ochoa/Nuevo vol/dft/runs}"
cd "$PROJ" || exit 1

LOG="$RUNS_ROOT/batches/autostart.log"
mkdir -p "$RUNS_ROOT/batches"
echo "[$(date '+%F %T')] buho_autostart: iniciando recuperación" >> "$LOG"

# 1. Resetear jobs 'running' huérfanos → pending (sus procesos murieron en el apagón).
#    En arranque limpio no hay procesos vivos, así que todos los 'running' son huérfanos.
"$PY" - <<'PY' >> "$LOG" 2>&1
import json, glob, os
from pathlib import Path
root = Path(os.environ.get('DFT_RUNS_ROOT', '/media/luis-ochoa/Nuevo vol/dft/runs'))
n = 0
for f in glob.glob(str(root / 'batches' / 'batch_*' / '*' / 'status.json')) + glob.glob(str(root / 'relax_basic' / '*' / 'status.json')):
    try:
        s = json.load(open(f))
    except Exception:
        continue
    # 'running' = procesos muertos en el apagón; 'failed' = muerte abrupta → reintentar
    if s.get('status') in ('running', 'failed'):
        d = os.path.dirname(f)
        cid = os.path.basename(d)
        for x in ('error.txt', 'r2scan.txt'):
            p = os.path.join(d, x)
            if os.path.exists(p):
                os.remove(p)
        json.dump({'status': 'pending', 'candidate_id': cid,
                   'formula': s.get('formula', '?')}, open(f, 'w'), indent=2)
        n += 1
print(f'reset {n} running/failed-huerfanos -> pending')
PY

# 2. Arrancar el monitor FastAPI (gestiona runner 5×8 + encadena batches + dispara
#    el orquestador de retraining). Solo si no hay uno vivo ya.
if pgrep -f "start_monitor.py" > /dev/null; then
    echo "[$(date '+%F %T')] monitor ya corriendo — no se duplica" >> "$LOG"
else
    setsid "$PY" scripts/start_monitor.py --host 127.0.0.1 --port 8000 --log-level info \
        >> "$RUNS_ROOT/batches/monitor.log" 2>&1 < /dev/null &
    echo "[$(date '+%F %T')] monitor lanzado (PID $!)" >> "$LOG"
fi
