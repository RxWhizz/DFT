#!/usr/bin/env bash
# Run r²SCAN DFT for all top-8 photovoltaic perovskite candidates with MPI.
#
# Prerequisites:
#   python scripts/setup_top8_r2scan.py   # creates symlinks and output dirs
#
# Default: 7 MPI processes (leave 1 core for the OS).
# Materials run sequentially; each material uses all MPI cores.
# Score step runs serial (pure Python, no GPAW).
#
# Environment overrides:
#   MPI_N=4 ./run_top8_r2scan.sh           # use 4 cores instead
#   STEPS="r2scan,r2scan_bands" ./...      # run subset of steps
#   DRY_RUN=1 ./run_top8_r2scan.sh         # dry run (no GPAW calls)
#   PHASES="CsPbI3 MAPbI3" ./...           # run subset of materials

set -uo pipefail

# ── Paths ──────────────────────────────────────────────────────────────────
DFT_ROOT="${DFT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
PYTHON="${PYTHON:-$DFT_ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3 || true)"
fi
if [[ -z "$PYTHON" ]]; then
  echo "ERROR: no Python interpreter found. Set PYTHON=/path/to/python." >&2
  exit 127
fi

# ── GPAW environment ────────────────────────────────────────────────────────
export GPAW_SETUP_PATH="${GPAW_SETUP_PATH:-$HOME/.gpaw/gpaw-setups-24.11.0}"
export GPAW_CONFIG="${GPAW_CONFIG:-$DFT_ROOT/siteconfig.py}"
export OMP_NUM_THREADS=1          # no threading inside MPI ranks
export OPENBLAS_NUM_THREADS=1

# ── Run parameters ──────────────────────────────────────────────────────────
WORKDIR="${WORKDIR:-$DFT_ROOT/calculations/top8_r2scan}"
CONFIG="${CONFIG:-$DFT_ROOT/configs/default_params.yaml}"
COMPOSITION_CONFIG="${COMPOSITION_CONFIG:-$DFT_ROOT/configs/top8_r2scan.yaml}"
STEPS="${STEPS:-r2scan,soc_r2scan,effective_masses,score}"
MPI_N="${MPI_N:-7}"               # 7 MPI cores, 1 left for OS
DRY_RUN="${DRY_RUN:-0}"
STOP_ON_ERROR="${STOP_ON_ERROR:-0}"

PHASES_RAW="${PHASES:-MAPbI3 MASnI3 FAPbI3 FASnI3 CsSnI3 CsPbI3 FAPbBr3 FASnBr3}"
read -r -a PHASES_ARRAY <<< "$PHASES_RAW"

# ── Logging ─────────────────────────────────────────────────────────────────
LOG_DIR="${LOG_DIR:-$WORKDIR/logs}"
STATUS_CSV="$WORKDIR/top8_r2scan_status.csv"
MASTER_LOG="$LOG_DIR/top8_r2scan_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$LOG_DIR" "$WORKDIR"

log() {
  local msg="[$(date -Is)] $*"
  echo "$msg" | tee -a "$MASTER_LOG"
}

run_mpi() {
  local log_file="$1"; shift
  log "CMD (MPI n=$MPI_N): $*"
  mpirun -n "$MPI_N" "$@" >"$log_file" 2>&1
}

run_serial() {
  local log_file="$1"; shift
  log "CMD (serial): $*"
  "$@" >"$log_file" 2>&1
}

record_status() {
  local phase="$1" status="$2" code="$3" log_file="$4"
  if [[ ! -f "$STATUS_CSV" ]]; then
    echo "timestamp,phase,status,exit_code,log_file" > "$STATUS_CSV"
  fi
  printf '%s,%s,%s,%s,%s\n' "$(date -Is)" "$phase" "$status" "$code" "$log_file" >> "$STATUS_CSV"
}

# ── Split score from MPI steps ───────────────────────────────────────────────
# score step is pure Python (reads files); run serial to avoid MPI overhead
split_steps() {
  local raw="$1"
  SCORE_REQUESTED=0
  MPI_STEPS_ARRAY=()
  IFS=',' read -r -a _all <<< "$raw"
  for s in "${_all[@]}"; do
    s="${s//[[:space:]]/}"
    [[ -z "$s" ]] && continue
    if [[ "$s" == "score" ]]; then
      SCORE_REQUESTED=1
    else
      MPI_STEPS_ARRAY+=("$s")
    fi
  done
}

join_steps() { local IFS=,; echo "$*"; }

# ── Main ─────────────────────────────────────────────────────────────────────
log "=== r²SCAN Top 8 started ==="
log "DFT_ROOT=$DFT_ROOT  WORKDIR=$WORKDIR"
log "STEPS=$STEPS  MPI_N=$MPI_N  DRY_RUN=$DRY_RUN"
log "PHASES: ${PHASES_ARRAY[*]}"

split_steps "$STEPS"

for phase in "${PHASES_ARRAY[@]}"; do
  phase_log="$LOG_DIR/r2scan_${phase}_$(date +%Y%m%d_%H%M%S).log"
  code=0

  # ── MPI steps (r2scan, soc_r2scan, r2scan_bands, effective_masses) ────────
  if [[ "${#MPI_STEPS_ARRAY[@]}" -gt 0 ]]; then
    mpi_steps="$(join_steps "${MPI_STEPS_ARRAY[@]}")"
    log "--- $phase: MPI steps [$mpi_steps] ---"
    args=(
      "$PYTHON" "$DFT_ROOT/main.py" run
      --phase "$phase"
      --config "$CONFIG"
      --composition-config "$COMPOSITION_CONFIG"
      --workdir "$WORKDIR"
      --steps "$mpi_steps"
    )
    [[ "$DRY_RUN" == "1" ]] && args+=(--dry-run)

    run_mpi "$phase_log" "${args[@]}"
    code=$?
  fi

  # ── Score step (serial, reads files only) ─────────────────────────────────
  if [[ "$code" -eq 0 && "$SCORE_REQUESTED" == "1" ]]; then
    score_log="$LOG_DIR/r2scan_${phase}_score_$(date +%Y%m%d_%H%M%S).log"
    log "--- $phase: score (serial) ---"
    score_args=(
      "$PYTHON" "$DFT_ROOT/main.py" run
      --phase "$phase"
      --config "$CONFIG"
      --composition-config "$COMPOSITION_CONFIG"
      --workdir "$WORKDIR"
      --steps score
    )
    [[ "$DRY_RUN" == "1" ]] && score_args+=(--dry-run)

    run_serial "$score_log" "${score_args[@]}"
    code=$?
    phase_log="$score_log"
  fi

  # ── Record outcome ─────────────────────────────────────────────────────────
  if [[ "$code" -eq 0 ]]; then
    log "=== $phase: DONE ==="
    record_status "$phase" "$([[ "$DRY_RUN" == "1" ]] && echo dry_run_done || echo done)" "$code" "$phase_log"
  else
    log "=== $phase: FAILED (exit $code) — see $phase_log ==="
    record_status "$phase" "failed" "$code" "$phase_log"
    if [[ "$STOP_ON_ERROR" == "1" ]]; then
      log "STOP_ON_ERROR=1 — aborting"
      exit "$code"
    fi
  fi
done

log "=== r²SCAN Top 8 finished ==="
log "Status: $STATUS_CSV"
log "Logs:   $LOG_DIR/"
