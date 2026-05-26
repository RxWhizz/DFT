#!/bin/bash
# Pipeline secuencial G0W0: groundstate → G0W0 → SOC por material
# Uso: bash scripts/run_g0w0_pipeline.sh [MAT1 MAT2 ...]
# Default: los 4 Pb-based
set -euo pipefail

cd "$(dirname "$0")/.."
VENV=".venv/bin"
WORKDIR="calculations/top8_r2scan"
NRANKS="${NRANKS:-22}"
NBANDS="${NBANDS:-600}"
ECUT_GW="${ECUT_GW:-100}"

MATS=("${@:-CsPbI3 MAPbI3 FAPbI3 FAPbBr3}")
[ "$#" -eq 0 ] && MATS=(CsPbI3 MAPbI3 FAPbI3 FAPbBr3)

run_step() {
    local label="$1"; shift
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "[pipeline] $label"
    echo "[pipeline] $(date)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    "$@"
    echo "[pipeline] ✓ $label completado — $(date)"
}

for MAT in "${MATS[@]}"; do
    GW_DIR="$WORKDIR/$MAT/06_r2scan/g0w0"
    mkdir -p "$GW_DIR"

    GPW="$GW_DIR/g0w0_pbe.gpw"
    SUMM="$GW_DIR/g0w0_summary.json"
    SOC="$GW_DIR/g0w0_soc.json"

    echo ""
    echo "════════════════════════════════════════"
    echo "  MATERIAL: $MAT"
    echo "════════════════════════════════════════"

    # Paso 1: groundstate (skip si GPW ya existe y es grande)
    if [ -f "$GPW" ] && [ "$(stat -c%s "$GPW" 2>/dev/null)" -gt 100000000 ]; then
        echo "[pipeline] $MAT groundstate: GPW existente ($(du -h "$GPW" | cut -f1)) — skip"
    else
        run_step "$MAT groundstate ($NBANDS bandas, $NRANKS ranks)" \
            mpirun -n "$NRANKS" "$VENV/python3" scripts/g0w0_groundstate.py \
                --mat "$MAT" --nbands "$NBANDS" \
                2>&1 | tee "$GW_DIR/g0w0_pbe.txt"
    fi

    # Paso 2: G0W0 (skip si summary ya existe)
    if [ -f "$SUMM" ]; then
        echo "[pipeline] $MAT G0W0: summary existente — skip"
        cat "$SUMM"
    else
        run_step "$MAT G0W0 (ecut=${ECUT_GW} eV, $NRANKS ranks)" \
            mpirun -n "$NRANKS" "$VENV/python3" scripts/g0w0_run.py \
                --mat "$MAT" --ecut "$ECUT_GW" \
                2>&1 | tee "$GW_DIR/g0w0_run.log"
    fi

    # Paso 3: SOC (serial, rápido)
    if [ -f "$SOC" ]; then
        echo "[pipeline] $MAT SOC: resultado existente — skip"
        cat "$SOC"
    else
        run_step "$MAT SOC (perturbativo, serial)" \
            "$VENV/python3" scripts/g0w0_soc.py --mat "$MAT" \
                2>&1 | tee "$GW_DIR/g0w0_soc.log"
    fi

    echo "[pipeline] ✓✓✓ $MAT COMPLETO"
done

echo ""
echo "════════════════════════════════════════"
echo "  PIPELINE COMPLETO — $(date)"
echo "════════════════════════════════════════"
echo ""
echo "Resultados:"
for MAT in "${MATS[@]}"; do
    SOC="$WORKDIR/$MAT/06_r2scan/g0w0/g0w0_soc.json"
    if [ -f "$SOC" ]; then
        GAP=$(python3 -c "import json; d=json.load(open('$SOC')); print(f\"{d['gap_gw_soc_eV']:.3f}\")")
        echo "  $MAT  gap_GW+SOC = $GAP eV"
    fi
done
