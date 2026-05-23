#!/usr/bin/env bash
set -euo pipefail

WORKDIR="${WORKDIR:-/home/luis-ochoa/Documents/Vscode/py/dft/calculations/top8_pbe}"
CONFIG="${CONFIG:-configs/default_params.yaml}"
COMPOSITION_CONFIG="${COMPOSITION_CONFIG:-configs/top8_pbe.yaml}"
STEPS="${STEPS:-relax,scf,bands,dos,soc,effective_masses,score}"
DRY_RUN="${DRY_RUN:-0}"
PYTHON="${PYTHON:-.venv/bin/python}"
PHASES=(MAPbI3 MASnI3 FAPbI3 FASnI3 CsSnI3 CsPbI3 FAPbBr3 FASnBr3)

if [[ ! -x "$PYTHON" ]]; then
  PYTHON=python3
fi

for phase in "${PHASES[@]}"; do
  echo "== PBE Top 8: $phase =="
  args=(
    main.py run
    --phase "$phase"
    --config "$CONFIG"
    --composition-config "$COMPOSITION_CONFIG"
    --workdir "$WORKDIR"
    --steps "$STEPS"
  )
  if [[ "$DRY_RUN" == "1" ]]; then
    args+=(--dry-run)
  fi
  "$PYTHON" "${args[@]}"
done

"$PYTHON" scripts/setup_top8_pbe.py --collect-only --workdir "$WORKDIR"
