#!/usr/bin/env bash
# launching terminal

set -euo pipefail

DFT_ROOT="${DFT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
WORKDIR="${WORKDIR:-$DFT_ROOT/calculations/top8_pbe}"
LOG_DIR="${LOG_DIR:-$WORKDIR/logs}"
RUNNER="${RUNNER:-$DFT_ROOT/scripts/run_top8_auto.sh}"
UNIT_FILE="${UNIT_FILE:-$WORKDIR/top8_auto.unit}"
PID_FILE="${PID_FILE:-$WORKDIR/top8_auto.pid}"
UNIT_PREFIX="${UNIT_PREFIX:-top8-dft}"
MPI_N="${MPI_N:-7}"
STOP_ON_ERROR="${STOP_ON_ERROR:-0}"
RUN_DFT="${RUN_DFT:-1}"
RUN_AI="${RUN_AI:-1}"
DRY_RUN="${DRY_RUN:-0}"
LINES="${LINES:-80}"

mkdir -p "$WORKDIR" "$LOG_DIR"

usage() {
  cat <<'USAGE'
Usage: scripts/supervise_top8_auto.sh [start|status|logs|phase-log|calc-log|follow|stop]

Environment:
  MPI_N=7              MPI ranks for DFT runs (default: 7)
  STOP_ON_ERROR=0      Keep running remaining candidates after failures
  RUN_DFT=1 RUN_AI=1   Enable DFT and/or AI stages
  DRY_RUN=0            Use 1 for a smoke run
  PHASES="MAPbI3 ..."  Optional candidate subset
  LINES=80             Lines shown by logs/phase-log
USAGE
}

current_unit() {
  [[ -s "$UNIT_FILE" ]] && tr -d '[:space:]' < "$UNIT_FILE"
}

have_systemd_user() {
  command -v systemd-run >/dev/null 2>&1 && command -v systemctl >/dev/null 2>&1
}

unit_is_active() {
  local unit="${1:-}"
  [[ -n "$unit" ]] && systemctl --user is-active --quiet "$unit"
}

show_status() {
  local unit
  unit="$(current_unit || true)"
  if have_systemd_user && [[ -n "$unit" ]]; then
    systemctl --user --no-pager --full status "$unit" || true
  elif [[ -s "$PID_FILE" ]]; then
    ps -o pid,ppid,stat,pcpu,pmem,etime,cmd -p "$(cat "$PID_FILE")" || true
  else
    echo "No Top 8 background run recorded."
  fi

  pgrep -af 'mpirun|main.py run --phase|run_top8_auto' || true
}

show_latest_log() {
  local pattern="$1"
  local latest
  latest="$(ls -t "$LOG_DIR"/$pattern 2>/dev/null | head -1 || true)"
  if [[ -z "$latest" ]]; then
    echo "No logs found in $LOG_DIR matching $pattern"
    return 0
  fi
  echo "==> $latest"
  tail -n "$LINES" "$latest"
}

show_latest_calc_log() {
  local latest
  latest="$(
    find "$WORKDIR" -path "$LOG_DIR" -prune -o -type f -name '*.txt' -printf '%T@ %p\n' 2>/dev/null \
      | sort -nr \
      | head -1 \
      | cut -d' ' -f2-
  )"
  if [[ -z "$latest" ]]; then
    echo "No calculation logs found under $WORKDIR"
    return 0
  fi
  echo "==> $latest"
  tail -n "$LINES" "$latest"
}

start_systemd() {
  local existing unit
  existing="$(current_unit || true)"
  if unit_is_active "$existing"; then
    echo "Top 8 is already running as $existing"
    show_status
    return 0
  fi

  unit="$UNIT_PREFIX-$(date +%Y%m%d-%H%M%S)"
  env_args=(
    "MPI_N=$MPI_N"
    "STOP_ON_ERROR=$STOP_ON_ERROR"
    "RUN_DFT=$RUN_DFT"
    "RUN_AI=$RUN_AI"
    "DRY_RUN=$DRY_RUN"
    "WORKDIR=$WORKDIR"
    "LOG_DIR=$LOG_DIR"
  )
  [[ -n "${AI_ROOT:-}" ]] && env_args+=("AI_ROOT=$AI_ROOT")
  [[ -n "${PHASES:-}" ]] && env_args+=("PHASES=$PHASES")
  [[ -n "${DFT_STEPS:-}" ]] && env_args+=("DFT_STEPS=$DFT_STEPS")
  [[ -n "${PYTHON:-}" ]] && env_args+=("PYTHON=$PYTHON")

  systemd-run --user --unit="$unit" --collect \
    --working-directory="$DFT_ROOT" \
    env "${env_args[@]}" "$RUNNER"
  echo "$unit" > "$UNIT_FILE"
  echo "Started Top 8 background run as $unit with MPI_N=$MPI_N"
}

start_nohup() {
  if [[ -s "$PID_FILE" ]] && ps -p "$(cat "$PID_FILE")" >/dev/null 2>&1; then
    echo "Top 8 is already running with PID $(cat "$PID_FILE")"
    show_status
    return 0
  fi

  local supervisor_log
  supervisor_log="$LOG_DIR/supervisor_$(date +%Y%m%d_%H%M%S).log"
  nohup env \
    MPI_N="$MPI_N" \
    STOP_ON_ERROR="$STOP_ON_ERROR" \
    RUN_DFT="$RUN_DFT" \
    RUN_AI="$RUN_AI" \
    DRY_RUN="$DRY_RUN" \
    WORKDIR="$WORKDIR" \
    LOG_DIR="$LOG_DIR" \
    "$RUNNER" >"$supervisor_log" 2>&1 &
  echo "$!" > "$PID_FILE"
  echo "Started Top 8 background run with PID $(cat "$PID_FILE") and MPI_N=$MPI_N"
  echo "Supervisor log: $supervisor_log"
}

stop_run() {
  local unit
  unit="$(current_unit || true)"
  if have_systemd_user && [[ -n "$unit" ]]; then
    systemctl --user stop "$unit" || true
    echo "Stopped $unit"
    return 0
  fi

  if [[ -s "$PID_FILE" ]]; then
    kill "$(cat "$PID_FILE")" || true
    echo "Stopped PID $(cat "$PID_FILE")"
  else
    echo "No Top 8 background run recorded."
  fi
}

action="${1:-status}"
case "$action" in
  start)
    if have_systemd_user; then
      start_systemd
    else
      start_nohup
    fi
    show_status
    ;;
  status)
    show_status
    ;;
  logs)
    show_latest_log 'top8_auto_*.log'
    ;;
  phase-log)
    show_latest_log 'dft_*.log'
    ;;
  calc-log)
    show_latest_calc_log
    ;;
  follow)
    unit="$(current_unit || true)"
    if have_systemd_user && [[ -n "$unit" ]]; then
      journalctl --user -u "$unit" -f
    else
      show_latest_log 'top8_auto_*.log'
    fi
    ;;
  stop)
    stop_run
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage
    exit 2
    ;;
esac
