#!/usr/bin/env bash
# resume_pipeline.sh — Recupera el pipeline DFT tras apagón o reinicio.
#
# Uso:
#   bash scripts/resume_pipeline.sh          # detecta y reanuda
#   bash scripts/resume_pipeline.sh --force  # mata y relanza todo aunque esté corriendo
#
# Qué hace:
#   1. Respeta el monitor vivo (o lo reinicia con --force).
#   2. Encuentra el batch activo (centinela + jobs pending/running).
#   3. Si el runner no corre para ese batch, lo relanza.
#   4. Arranca el monitor en background.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

FORCE=""
RUNNER_ONLY=""
for arg in "$@"; do
    case "$arg" in
        --force)       FORCE=1 ;;
        --runner-only) RUNNER_ONLY=1 ;;
    esac
done
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"

PY="${ROOT}/.venv/bin/python3"
[ -x "$PY" ] || PY="$(command -v python3)"

# ── 1. Leer config (slots, cores, puerto) ─────────────────────────────────────
SLOTS=$("$PY" -c "
import yaml, sys
c = yaml.safe_load(open('configs/monitor.yaml'))
m = c.get('monitor', {})
# merge local
import pathlib
lc = pathlib.Path('configs/monitor.local.yaml')
if lc.exists():
    lc_data = yaml.safe_load(lc.read_text()) or {}
    for k, v in lc_data.items():
        if isinstance(v, dict) and isinstance(m, dict):
            m.update(v)
print(m.get('runner_slots', 5))
")

CORES=$("$PY" -c "
import yaml, pathlib
c = yaml.safe_load(open('configs/monitor.yaml'))
m = c.get('monitor', {})
lc = pathlib.Path('configs/monitor.local.yaml')
if lc.exists():
    for k,v in (yaml.safe_load(lc.read_text()) or {}).items():
        if isinstance(v,dict): m.update(v)
print(m.get('runner_cores', 8))
")

PORT=$("$PY" -c "
import yaml
c = yaml.safe_load(open('configs/monitor.yaml'))
print(c.get('api', {}).get('port', 8000))
")

BATCHES_DIR=$("$PY" - <<'PY'
import pathlib, yaml
root = pathlib.Path('.').resolve()
c = yaml.safe_load(open('configs/monitor.yaml')) or {}
m = c.get('monitor', {})
lc = pathlib.Path('configs/monitor.local.yaml')
if lc.exists():
    local = yaml.safe_load(lc.read_text()) or {}
    m.update(local.get('monitor', {}))
p = pathlib.Path(m.get('batches_dir', 'runs/batches'))
print(p if p.is_absolute() else root / p)
PY
)

echo "[$(date '+%F %T')] === resume_pipeline.sh ==="
echo "  PY=$PY  SLOTS=$SLOTS  CORES=$CORES  PORT=$PORT"
echo "  BATCHES_DIR=$BATCHES_DIR"

# ── 2. Monitor: no duplicar ni matar salvo --force ────────────────────────────
MONITOR_RUNNING=""
if [ -z "$RUNNER_ONLY" ]; then
    MONITOR_RUNNING=$(pgrep -f "scripts/start_monitor.py.*--port $PORT" 2>/dev/null || true)
    if [ -n "$MONITOR_RUNNING" ] && [ -z "$FORCE" ]; then
        echo "  Monitor ya corriendo (PID $MONITOR_RUNNING) — no se relanza"
    elif [ -n "$FORCE" ]; then
        pkill -f "scripts/start_monitor.py" 2>/dev/null || true
        sleep 2
        MONITOR_RUNNING=""
    fi
fi

# ── 3. Encontrar batch activo ─────────────────────────────────────────────────
ACTIVE_BATCH=$(BATCHES_DIR="$BATCHES_DIR" "$PY" - <<'PYEOF'
import json, sys
import os
from pathlib import Path

batches_dir = Path(os.environ["BATCHES_DIR"])
if not batches_dir.exists():
    sys.exit(0)

candidates = sorted(
    (d for d in batches_dir.iterdir()
     if d.is_dir() and (d / ".runner_launched").exists()),
    key=lambda d: int("".join(filter(str.isdigit, d.name)) or "0"),
    reverse=True,
)
for batch_dir in candidates:
    for j in batch_dir.iterdir():
        if not j.is_dir(): continue
        s = j / "status.json"
        if s.exists() and json.loads(s.read_text()).get("status") in ("pending", "running"):
            print(batch_dir)
            sys.exit(0)
PYEOF
)

if [ -z "$ACTIVE_BATCH" ]; then
    echo "  No hay batch activo con jobs pendientes."
else
    echo "  Batch activo: $ACTIVE_BATCH"

    # ── 4. Rearrancar runner si no está corriendo ─────────────────────────────
    RUNNER_RUNNING=$(ACTIVE_BATCH="$ACTIVE_BATCH" "$PY" - <<'PY'
import os
from pathlib import Path

active = Path(os.environ["ACTIVE_BATCH"]).resolve()
matches = []
for proc in Path("/proc").iterdir():
    if not proc.name.isdigit():
        continue
    try:
        parts = (proc / "cmdline").read_bytes().decode(errors="replace").split("\0")
    except Exception:
        continue
    if not any(part.endswith("buho_relax_runner.py") for part in parts):
        continue
    if "--relax-dir" not in parts:
        continue
    try:
        relax = Path(parts[parts.index("--relax-dir") + 1]).resolve()
    except Exception:
        continue
    if relax == active:
        matches.append(proc.name)
print(" ".join(matches))
PY
)

    if [ -n "$RUNNER_RUNNING" ] && [ -z "$FORCE" ]; then
        echo "  Runner ya corriendo (PID $RUNNER_RUNNING) — no se relanza"
    else
        [ -n "$FORCE" ] && pkill -f "buho_relax_runner" 2>/dev/null || true
        sleep 1
        RUNNER_LOG="$LOG_DIR/runner_$(basename "$ACTIVE_BATCH").log"
        echo "  Lanzando runner → $RUNNER_LOG"
        setsid "$PY" scripts/buho_relax_runner.py \
            --relax-dir "$ACTIVE_BATCH" \
            --slots "$SLOTS" \
            --cores "$CORES" \
            >> "$RUNNER_LOG" 2>&1 < /dev/null &
        echo "  Runner PID: $!"
    fi
fi

# ── 5. Arrancar monitor (solo si no es --runner-only) ────────────────────────
if [ -z "$RUNNER_ONLY" ] && [ -z "$MONITOR_RUNNING" ]; then
    MONITOR_LOG="$LOG_DIR/monitor.log"
    echo "  Lanzando monitor → $MONITOR_LOG"
    setsid "$PY" scripts/start_monitor.py \
        --port "$PORT" \
        --log-level info \
        >> "$MONITOR_LOG" 2>&1 < /dev/null &
    MONITOR_PID=$!
    echo "  Monitor PID: $MONITOR_PID"

    sleep 3
    if kill -0 "$MONITOR_PID" 2>/dev/null; then
        echo "  Monitor arriba ✓  http://localhost:$PORT/api/summary"
    else
        echo "  ERROR: monitor murió, revisa $MONITOR_LOG"
        tail -20 "$MONITOR_LOG"
        exit 1
    fi
fi
echo "[$(date '+%F %T')] Pipeline reanudado"
