#!/usr/bin/env bash
set -uo pipefail
DFT=/home/luis-ochoa/Documents/Vscode/py/dft
TXT=$DFT/calculations/top8_r2scan/CsSnI3/06_r2scan/r2scan.txt
YAML=$DFT/configs/default_params.yaml
LOG=$DFT/calculations/top8_r2scan/logs/monitor_r2scan_cssni3.log
WAIT_ITERS=300
DENS_THRESHOLD=-3.5

log() { echo "[$(date -Is)] $*" | tee -a "$LOG"; }
get_iter() { grep "iter:" "$TXT" 2>/dev/null | tail -1 | grep -oP "iter:\s*\K[0-9]+" || echo 0; }
get_best_dens() { grep "iter:" "$TXT" | tail -20 | grep -oP "\|\s*(-[0-9]+\.[0-9]+)c?\s*\|" | grep -oP "-[0-9]+\.[0-9]+" | sort -n | head -1; }

# Espera que la nueva corrida empiece (iter pequeño)
until [ "$(get_iter)" -le 20 ] && [ "$(get_iter)" -gt 0 ]; do sleep 20; done
START_ITER=$(get_iter)
TARGET=$(( START_ITER + WAIT_ITERS ))
log "Baseline iter=$START_ITER — evaluaré en iter=$TARGET (threshold densidad=$DENS_THRESHOLD)"

while true; do
  CUR=$(get_iter)
  [ "$CUR" -ge "$TARGET" ] && break
  sleep 60
done

BEST=$(get_best_dens)
log "Mejor densidad (últimas 20 iters): $BEST"

if python3 -c "import sys; sys.exit(0 if float('${BEST}') < ${DENS_THRESHOLD} else 1)" 2>/dev/null; then
  log "OK — densidad $BEST < $DENS_THRESHOLD. Sin medidas extremas."
  exit 0
fi

log "INSUFICIENTE ($BEST). Aplicando Kerker + lineal: weight=100 beta=0.02 nmaxold=5 width=0.25"
pkill -9 -f "mpirun.*r2scan,soc" 2>/dev/null || true
pkill -9 -f "python.*main.py.*CsSnI3" 2>/dev/null || true
sleep 3

python3 << 'PY'
import re, pathlib
p = pathlib.Path('/home/luis-ochoa/Documents/Vscode/py/dft/configs/default_params.yaml')
txt = p.read_text()
# Patch r2scan block only
block_start = txt.index('\nr2scan:\n')
next_root = re.search(r'\n\S', txt[block_start+1:]).start() + block_start + 1
block = txt[block_start:next_root]
block = re.sub(r'(beta:\s*)[\d.]+', r'\g<1>0.02', block)
block = re.sub(r'(nmaxold:\s*)[\d.]+', r'\g<1>5', block)
block = re.sub(r'(width:\s*)[\d.]+', r'\g<1>0.25', block)
# Add weight if not present
if 'weight:' not in block:
    block = re.sub(r'(nmaxold:\s*\d+)', r'\1\n    weight: 100', block)
p.write_text(txt[:block_start] + block + txt[next_root:])
print("YAML actualizado: Kerker weight=100 beta=0.02 nmaxold=5 width=0.25")
PY

log "Relanzando con Kerker..."
cd "$DFT"
nohup bash -c '
MPI_N=22 PHASES="CsSnI3" STEPS="r2scan,soc_r2scan,effective_masses,score" \
  bash calculations/top8_r2scan/run_top8_r2scan.sh \
  >> calculations/top8_r2scan/logs/r2scan_CsSnI3_master.log 2>&1
' &
log "Relanzado PID: $!"
