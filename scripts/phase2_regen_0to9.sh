#!/bin/bash
# Regenera batches 0-9 de Fase 2A con el pipeline nuevo (MACE prerelax + PBE single-point E+F).
set -u
cd /home/luis-ochoa/Documents/Vscode/py/dft || exit 1
export PYTHONPATH=src
for b in 0 1 2 3 4 5 6 7 8 9; do
  echo "=== preparando batch $b ($(date +%F\ %H:%M:%S)) ==="
  .venv/bin/python3 -m buho.phase2_force.prepare --batch-id "$b" --cores 8 \
      --runs-dir runs/phase2_force 2>&1 | grep -E '"n_prepared"|"n_planned"|error' | head -3
done
echo "=== REGEN COMPLETA $(date +%F\ %H:%M:%S) ==="
