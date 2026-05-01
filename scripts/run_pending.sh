#!/usr/bin/env bash
# Executes the three pending GPAW steps in the optimal order:
#   loto → phonons (Δ=0.02, LO-TO corrected) → hse06
# Run from the project root: bash scripts/run_pending.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export GPAW_SETUP_PATH="${HOME}/.gpaw/gpaw-setups-24.11.0"
export GPAW_CONFIG="${ROOT}/siteconfig.py"
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1

PYTHON=".venv/bin/python3"
N=7

log() { echo "[$(date '+%H:%M:%S')] $*"; }

# ── Step 1: LOTO (Born charges + dielectric tensor) ─────────────────────────
log "=== LOTO: Born charges ==="
mpirun -n $N "$PYTHON" main.py run --phase alpha --steps loto
log "LOTO done."

# ── Step 2: Phonons Δ=0.02 Å (LO-TO correction applied automatically) ───────
log "=== Phonons: clearing Δ=0.05 cache, running Δ=0.02 ==="
rm -rf calculations/alpha/07_vibrational/phonons/phonon/
rm -f  calculations/alpha/07_vibrational/phonons/phonon_frequencies.npy
mpirun -n $N "$PYTHON" main.py run --phase alpha --steps phonons
log "Phonons done."

# ── Step 3: HSE06 ────────────────────────────────────────────────────────────
log "=== HSE06 ==="
mpirun -n $N "$PYTHON" main.py run --phase alpha --steps hse06
log "HSE06 done."

log "=== All pending steps complete ==="
log "Outputs:"
log "  08_loto/born_charges.npy"
log "  08_loto/dielectric_tensor.npy"
log "  07_vibrational/phonons/phonon_frequencies.npy  (LO-TO corrected)"
log "  06_hse06/hse06.gpw"
