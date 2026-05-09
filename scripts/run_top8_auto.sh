#!/usr/bin/env bash
# Runner automatico Top 8: DFT PBE + union AI.
# Default: primer plano, reanudable.
# CSV se refresca tras cada material; fallos se registran.
# Sigue con siguiente candidato si STOP_ON_ERROR=0.

set -uo pipefail

DFT_ROOT="${DFT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
AI_ROOT="${AI_ROOT:-$(cd "$DFT_ROOT/.." && pwd)/AI}"
PYTHON="${PYTHON:-$DFT_ROOT/.venv/bin/python}"

if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3 || true)"
fi
if [[ -z "$PYTHON" ]]; then
  echo "ERROR: no hay interprete Python. Define PYTHON=/path/to/python." >&2
  exit 127
fi

export GPAW_SETUP_PATH="${GPAW_SETUP_PATH:-$HOME/.gpaw/gpaw-setups-24.11.0}"
export GPAW_CONFIG="${GPAW_CONFIG:-$DFT_ROOT/siteconfig.py}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"

WORKDIR="${WORKDIR:-$DFT_ROOT/calculations/top8_pbe}"
STRUCTURES_DIR="${STRUCTURES_DIR:-$DFT_ROOT/structures/top8}"
DFT_CONFIG="${DFT_CONFIG:-$DFT_ROOT/configs/default_params.yaml}"
DFT_COMPOSITION_CONFIG="${DFT_COMPOSITION_CONFIG:-$DFT_ROOT/configs/top8_pbe.yaml}"
DFT_STEPS="${DFT_STEPS:-relax,scf,bands,dos,soc,effective_masses,score}"
MPI_N="${MPI_N:-1}"
SCORE_MPI_N="${SCORE_MPI_N:-1}"
DRY_RUN="${DRY_RUN:-0}"
RUN_DFT="${RUN_DFT:-1}"
RUN_AI="${RUN_AI:-1}"
AI_BACKEND="${AI_BACKEND:-auto}"
AI_MODE="${AI_MODE:-atomistic}"
AI_RUN_PHONONS="${AI_RUN_PHONONS:-0}"
STOP_ON_ERROR="${STOP_ON_ERROR:-0}"

PHASES_RAW="${PHASES:-MAPbI3 MASnI3 FAPbI3 FASnI3 CsSnI3 CsPbI3 FAPbBr3 FASnBr3}"
read -r -a PHASES_ARRAY <<< "$PHASES_RAW"

LOG_DIR="${LOG_DIR:-$WORKDIR/logs}"
STATUS_CSV="$WORKDIR/top8_auto_status.csv"
MASTER_LOG="$LOG_DIR/top8_auto_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$LOG_DIR" "$WORKDIR"

log() {
  local msg
  msg="[$(date -Is)] $*"
  echo "$msg" >> "$MASTER_LOG"
  echo "$msg"
}

run_cmd() {
  local log_file="$1"
  shift
  log "CMD: $*"
  "$@" >"$log_file" 2>&1
}

run_python_module() {
  local log_file="$1"
  shift
  if [[ "$MPI_N" =~ ^[0-9]+$ && "$MPI_N" -gt 1 ]]; then
    run_cmd "$log_file" mpirun -n "$MPI_N" "$PYTHON" "$@"
  else
    run_cmd "$log_file" "$PYTHON" "$@"
  fi
}

run_python_module_serial() {
  local log_file="$1"
  shift
  if [[ "$SCORE_MPI_N" =~ ^[0-9]+$ && "$SCORE_MPI_N" -gt 1 ]]; then
    run_cmd "$log_file" mpirun -n "$SCORE_MPI_N" "$PYTHON" "$@"
  else
    run_cmd "$log_file" "$PYTHON" "$@"
  fi
}

split_score_steps() {
  local raw_steps="$1"
  local step
  SCORE_REQUESTED=0
  NON_SCORE_STEPS_ARRAY=()
  IFS=',' read -r -a _split_steps <<< "$raw_steps"
  for step in "${_split_steps[@]}"; do
    step="${step//[[:space:]]/}"
    [[ -z "$step" ]] && continue
    if [[ "$step" == "score" ]]; then
      SCORE_REQUESTED=1
    else
      NON_SCORE_STEPS_ARRAY+=("$step")
    fi
  done
}

join_steps() {
  local IFS=,
  echo "$*"
}

refresh_dft_csv() {
  "$PYTHON" "$DFT_ROOT/scripts/setup_top8_pbe.py" \
    --collect-only \
    --workdir "$WORKDIR" \
    --structures-dir "$STRUCTURES_DIR" >>"$MASTER_LOG" 2>&1
}

record_status() {
  local phase="$1"
  local status="$2"
  local exit_code="$3"
  local log_file="$4"
  if [[ ! -f "$STATUS_CSV" ]]; then
    echo "timestamp,phase,status,exit_code,log_file" > "$STATUS_CSV"
  fi
  printf '%s,%s,%s,%s,%s\n' "$(date -Is)" "$phase" "$status" "$exit_code" "$log_file" >> "$STATUS_CSV"
}

log "Corrida automatica Top 8 iniciada"
log "DFT_ROOT=$DFT_ROOT"
log "AI_ROOT=$AI_ROOT"
log "WORKDIR=$WORKDIR"
log "DFT_STEPS=$DFT_STEPS"
log "MPI_N=$MPI_N SCORE_MPI_N=$SCORE_MPI_N DRY_RUN=$DRY_RUN RUN_DFT=$RUN_DFT RUN_AI=$RUN_AI"

log "Preparando workspace DFT Top 8"
"$PYTHON" "$DFT_ROOT/scripts/setup_top8_pbe.py" \
  --workdir "$WORKDIR" \
  --structures-dir "$STRUCTURES_DIR" >>"$MASTER_LOG" 2>&1

if [[ "$RUN_DFT" == "1" ]]; then
  for phase in "${PHASES_ARRAY[@]}"; do
    phase_log="$LOG_DIR/dft_${phase}_$(date +%Y%m%d_%H%M%S).log"
    split_score_steps "$DFT_STEPS"
    code=0
    status_log="$phase_log"

    if [[ "${#NON_SCORE_STEPS_ARRAY[@]}" -gt 0 ]]; then
      non_score_steps="$(join_steps "${NON_SCORE_STEPS_ARRAY[@]}")"
      log "Inicia DFT PBE phase=$phase steps=$non_score_steps log=$phase_log"
      args=(
        "$DFT_ROOT/main.py" run
        --phase "$phase"
        --config "$DFT_CONFIG"
        --composition-config "$DFT_COMPOSITION_CONFIG"
        --workdir "$WORKDIR"
        --steps "$non_score_steps"
      )
      if [[ "$DRY_RUN" == "1" ]]; then
        args+=(--dry-run)
      fi

      run_python_module "$phase_log" "${args[@]}"
      code=$?
    else
      log "Sin pasos DFT MPI para phase=$phase antes de score"
    fi

    if [[ "$code" -eq 0 && "$SCORE_REQUESTED" == "1" ]]; then
      score_log="$LOG_DIR/dft_${phase}_score_$(date +%Y%m%d_%H%M%S).log"
      status_log="$score_log"
      log "Inicia score DFT serial phase=$phase log=$score_log"
      score_args=(
        "$DFT_ROOT/main.py" run
        --phase "$phase"
        --config "$DFT_CONFIG"
        --composition-config "$DFT_COMPOSITION_CONFIG"
        --workdir "$WORKDIR"
        --steps score
      )
      if [[ "$DRY_RUN" == "1" ]]; then
        score_args+=(--dry-run)
      fi
      run_python_module_serial "$score_log" "${score_args[@]}"
      code=$?
    fi

    if [[ "$code" -eq 0 ]]; then
      log "DFT phase=$phase terminado"
      if [[ "$DRY_RUN" == "1" ]]; then
        record_status "$phase" "dft_dry_run_done" "$code" "$status_log"
      else
        record_status "$phase" "dft_done" "$code" "$status_log"
      fi
    else
      log "DFT phase=$phase fallo exit_code=$code"
      record_status "$phase" "dft_failed" "$code" "$status_log"
      if [[ "$STOP_ON_ERROR" == "1" ]]; then
        refresh_dft_csv || true
        exit "$code"
      fi
    fi
    refresh_dft_csv || log "ALERTA: fallo refresco CSV DFT tras $phase"
  done
else
  log "RUN_DFT=0: omite ejecucion DFT"
  refresh_dft_csv || log "ALERTA: fallo refresco CSV DFT"
fi

if [[ "$RUN_AI" == "1" ]]; then
  if [[ ! -d "$AI_ROOT" ]]; then
    log "ALERTA: AI_ROOT no existe: $AI_ROOT"
  else
    ai_log="$LOG_DIR/ai_top8_$(date +%Y%m%d_%H%M%S).log"
    log "Inicia corrida AI Top 8 log=$ai_log"
    ai_args=(
      "$AI_ROOT/scripts/run_top8_ai.py"
      --artifacts-dir "$AI_ROOT/atomistic_runs/top8"
      --structures-dir "$AI_ROOT/atomistic_runs/top8/structures"
      --dft-pbe-csv "$WORKDIR/top8_pbe_comparison.csv"
      --backend "$AI_BACKEND"
      --mode "$AI_MODE"
    )
    if [[ "$AI_RUN_PHONONS" == "1" ]]; then
      ai_args+=(--run-phonons)
    else
      ai_args+=(--no-run-phonons)
    fi
    if [[ "$DRY_RUN" == "1" ]]; then
      ai_args+=(--dry-run)
    fi

    (cd "$AI_ROOT" && run_cmd "$ai_log" "$PYTHON" "${ai_args[@]}")
    code=$?
    if [[ "$code" -eq 0 ]]; then
      log "AI Top 8 terminado"
      if [[ "$DRY_RUN" == "1" ]]; then
        record_status "AI_TOP8" "ai_dry_run_done" "$code" "$ai_log"
      else
        record_status "AI_TOP8" "ai_done" "$code" "$ai_log"
      fi
    else
      log "AI Top 8 fallo exit_code=$code"
      record_status "AI_TOP8" "ai_failed" "$code" "$ai_log"
      if [[ "$STOP_ON_ERROR" == "1" ]]; then
        exit "$code"
      fi
    fi
  fi
else
  log "RUN_AI=0: omite ejecucion AI"
fi

log "Corrida automatica Top 8 terminada"
log "Status CSV: $STATUS_CSV"
log "Log maestro: $MASTER_LOG"
