#!/usr/bin/env bash
# monitor_dft_runs.sh — autopilot de salud para runs top8_r2scan.
#
# FULL AUTOPILOT — autorizado por el usuario (2026-05-19):
#   kill de procesos, modificación de parámetros YAML y relaunch
#   sin confirmación, en cualquier momento.
#
# Uso: bash scripts/monitor_dft_runs.sh [--once]
#
# Detecta:
#   1. Oscilación SCF   → kill → escalar mixer Pulay → Broyden → relaunch
#   2. Divergencia SCF  → kill → reducir beta → relaunch
#   3. Proceso muerto   → relaunch directo
#
# Escalación de oscilación (automática, sin intervención):
#   Pulay nmaxold 8 → 10 → 12 → switch Broyden (beta=0.05, nmaxold=8)
#   Broyden beta 0.05 → 0.02 → 0.01 (mínimo)

set -uo pipefail

DFT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKDIR="$DFT_ROOT/calculations/top8_r2scan"
LOG="$WORKDIR/logs/monitor_$(date +%Y%m%d).log"
mkdir -p "$WORKDIR/logs"

mlog() { echo "[$(date -Is)] $*" | tee -a "$LOG"; }

# ── Parámetros de detección ──────────────────────────────────────────────────
SCF_STALL_ITERS=30      # iters sin mejorar densidad → divergencia
SCF_STALL_WINDOW=20     # ventana de iters para evaluar mejora
ENERGY_SPREAD_THR=5.0   # eV — spread máx en ventana antes de flag divergencia

OSC_WINDOW=15           # ventana de iters para detección de oscilación
OSC_REVERSALS_THR=5     # cambios de dirección mínimos en (OSC_WINDOW-1) pasos
OSC_SPREAD_THR=0.15     # eV — spread mínimo para considerar oscilación no trivial
OSC_MIN_ITERS=20        # buffer de arranque: no evaluar antes de este número

# ── Helpers ──────────────────────────────────────────────────────────────────
pids_for_phase() {
  local phase="$1"
  pgrep -f "main.py run.*--phase $phase" 2>/dev/null || true
}

kill_phase() {
  local phase="$1"
  local pids
  pids=$(pids_for_phase "$phase")
  if [[ -n "$pids" ]]; then
    mlog "KILL: $phase PIDs $pids"
    # shellcheck disable=SC2086
    kill $pids 2>/dev/null || true
    sleep 3
    kill -9 $pids 2>/dev/null || true
  fi
  # kill parent mpirun too
  pkill -f "mpirun.*$phase" 2>/dev/null || true
}

last_n_energies() {
  # Extract last N energy values from a GPAW txt log
  local txt="$1" n="$2"
  grep -oP 'iter:\s+\d+ \S+ +\K-?\d+\.\d+' "$txt" 2>/dev/null | tail -"$n"
}

energy_spread() {
  local txt="$1" n="$2"
  local vals
  vals=$(last_n_energies "$txt" "$n")
  [[ -z "$vals" ]] && echo 0 && return
  python3 -c "
vals=[float(x) for x in '''$vals'''.split()]
print(max(vals)-min(vals)) if vals else print(0)
" 2>/dev/null || echo 0
}

iter_count() {
  local txt="$1"
  grep -c "^iter:" "$txt" 2>/dev/null || echo 0
}

# ── Diagnose r2scan txt ──────────────────────────────────────────────────────
check_r2scan_scf() {
  local mat="$1"
  local txt="$WORKDIR/$mat/06_r2scan/r2scan.txt"
  local gpw="$WORKDIR/$mat/06_r2scan/r2scan.gpw"

  # Already done
  [[ -f "$gpw" ]] && return 0

  # Not started yet
  [[ ! -f "$txt" ]] && return 0

  local iters spread
  iters=$(iter_count "$txt")
  spread=$(energy_spread "$txt" "$SCF_STALL_WINDOW")

  mlog "$mat r2scan: iter=$iters energy_spread=${spread} eV (window=$SCF_STALL_WINDOW)"

  # Flag divergence: spread > threshold AND enough iters to judge
  if (( iters > SCF_STALL_ITERS )) && python3 -c "exit(0 if float('$spread') > $ENERGY_SPREAD_THR else 1)" 2>/dev/null; then
    mlog "DIVERGENCE detected in $mat r2scan (spread=${spread} eV > ${ENERGY_SPREAD_THR}). Killing and fixing."
    return 1
  fi
  return 0
}

# ── Detectar oscilación SCF ───────────────────────────────────────────────────
check_r2scan_oscillation() {
  local mat="$1"
  local txt="$WORKDIR/$mat/06_r2scan/r2scan.txt"
  local gpw="$WORKDIR/$mat/06_r2scan/r2scan.gpw"

  [[ -f "$gpw" ]] && return 0
  [[ ! -f "$txt" ]] && return 0

  local iters; iters=$(iter_count "$txt")
  (( iters < OSC_MIN_ITERS )) && return 0

  local result
  result=$(python3 - <<PYEOF 2>/dev/null
import re
txt = open('$txt').read()
energies = [float(m.group(1))
            for m in re.finditer(r'^iter:\s+\d+ \S+ +([-\d.]+)', txt, re.MULTILINE)]
energies = energies[-$OSC_WINDOW:]
if len(energies) < $OSC_WINDOW:
    print('ok')
else:
    spread = max(energies) - min(energies)
    diffs = [energies[i+1] - energies[i] for i in range(len(energies) - 1)]
    reversals = sum(1 for i in range(len(diffs) - 1) if diffs[i] * diffs[i+1] < 0)
    if spread > $OSC_SPREAD_THR and reversals >= $OSC_REVERSALS_THR:
        print(f'osc spread={spread:.3f}eV reversals={reversals}/{len(diffs)}')
    else:
        print('ok')
PYEOF
  )

  if [[ "$result" != "ok" ]]; then
    mlog "OSCILLATION detected in $mat r2scan ($result)"
    return 1
  fi
  return 0
}

# ── Fix: aumentar nmaxold → escalar a Broyden cuando Pulay se agota ─────────
fix_r2scan_oscillation() {
  local mat="$1"

  local current_backend current_nmaxold
  current_backend=$(python3 -c "
import yaml
with open('$DFT_ROOT/configs/default_params.yaml') as f:
    c = yaml.safe_load(f)
print(c.get('r2scan', {}).get('mixer', {}).get('backend', 'pulay'))
" 2>/dev/null || echo 'pulay')

  current_nmaxold=$(python3 -c "
import yaml
with open('$DFT_ROOT/configs/default_params.yaml') as f:
    c = yaml.safe_load(f)
print(c.get('r2scan', {}).get('mixer', {}).get('nmaxold', 8))
" 2>/dev/null || echo 8)

  if [[ "$current_backend" == "broyden" ]]; then
    # Broyden ya activo — reducir beta
    fix_r2scan_broyden_beta "$mat"
    return
  fi

  # Backend pulay: escalar nmaxold o saltar a Broyden
  if python3 -c "exit(0 if int('$current_nmaxold') >= 12 else 1)" 2>/dev/null; then
    mlog "Fix $mat oscillation: Pulay nmaxold=$current_nmaxold (máx 12) — escalando a Broyden"
    fix_r2scan_switch_broyden "$mat"
    return
  fi

  local new_nmaxold
  new_nmaxold=$(python3 -c "print(min(int('$current_nmaxold') + 2, 12))" 2>/dev/null || echo 10)
  mlog "Fix $mat oscillation: Pulay nmaxold $current_nmaxold → $new_nmaxold"

  python3 - <<PYEOF
import re, pathlib
p = pathlib.Path('$DFT_ROOT/configs/default_params.yaml')
txt = p.read_text()
txt = re.sub(
    r'(r2scan:.*?mixer:.*?nmaxold:\s*)\S+',
    lambda m: m.group(1) + str($new_nmaxold),
    txt, count=1, flags=re.DOTALL)
p.write_text(txt)
print(f'YAML patched: r2scan.mixer.nmaxold = $new_nmaxold')
PYEOF

  rm -f "$WORKDIR/$mat/06_r2scan/r2scan.txt"
  mlog "Removed r2scan.txt for $mat"
}

# ── Fix: cambiar backend a Broyden (más robusto ante respuestas no lineales) ──
fix_r2scan_switch_broyden() {
  local mat="$1"
  mlog "Fix $mat: switching mixer Pulay → Broyden (beta=0.05, nmaxold=8, weight=100)"

  python3 - <<PYEOF
import re, pathlib
p = pathlib.Path('$DFT_ROOT/configs/default_params.yaml')
txt = p.read_text()
# Replace entire r2scan mixer block
new_mixer = "  mixer:\n    backend: broyden\n    beta: 0.05\n    nmaxold: 8\n    weight: 100.0\n"
txt = re.sub(
    r'(r2scan:(?:.*?\n)*?)(  mixer:\n(?:    \S[^\n]*\n)+)',
    lambda m: m.group(1) + new_mixer,
    txt, count=1)
p.write_text(txt)
print('YAML patched: r2scan mixer → broyden (beta=0.05, nmaxold=8, weight=100)')
PYEOF

  rm -f "$WORKDIR/$mat/06_r2scan/r2scan.txt"
  mlog "Removed r2scan.txt for $mat (Broyden escalation)"
}

# ── Fix: reducir beta en Broyden cuando sigue oscilando ──────────────────────
fix_r2scan_broyden_beta() {
  local mat="$1"
  local current_beta
  current_beta=$(python3 -c "
import yaml
with open('$DFT_ROOT/configs/default_params.yaml') as f:
    c = yaml.safe_load(f)
print(c.get('r2scan', {}).get('mixer', {}).get('beta', 0.05))
" 2>/dev/null || echo 0.05)

  local new_beta
  new_beta=$(python3 -c "b=float('$current_beta'); print(round(max(b*0.5, 0.01), 3))" 2>/dev/null || echo 0.02)

  if python3 -c "exit(0 if float('$current_beta') <= 0.01 else 1)" 2>/dev/null; then
    mlog "Fix $mat: Broyden beta ya en mínimo ($current_beta). Activar preconvergencia PBE si disponible."
    rm -f "$WORKDIR/$mat/06_r2scan/r2scan.txt"
    return
  fi

  mlog "Fix $mat: Broyden beta $current_beta → $new_beta"
  python3 - <<PYEOF
import re, pathlib
p = pathlib.Path('$DFT_ROOT/configs/default_params.yaml')
txt = p.read_text()
txt = re.sub(
    r'(r2scan:.*?mixer:.*?beta:\s*)\S+',
    lambda m: m.group(1) + str($new_beta),
    txt, count=1, flags=re.DOTALL)
p.write_text(txt)
print(f'YAML patched: r2scan Broyden beta = $new_beta')
PYEOF

  rm -f "$WORKDIR/$mat/06_r2scan/r2scan.txt"
  mlog "Removed r2scan.txt for $mat (Broyden beta reduced)"
}

# ── Fix: tighten mixer for r2scan ────────────────────────────────────────────
fix_r2scan_mixer() {
  local mat="$1"
  # Reduce beta further in YAML if current beta >= 0.05
  local current_beta
  current_beta=$(python3 -c "
import yaml
with open('$DFT_ROOT/configs/default_params.yaml') as f:
    c = yaml.safe_load(f)
print(c.get('r2scan', {}).get('mixer', {}).get('beta', 0.05))
" 2>/dev/null || echo 0.05)

  local new_beta
  new_beta=$(python3 -c "b=float('$current_beta'); print(round(max(b*0.5, 0.01), 3))" 2>/dev/null || echo 0.02)

  mlog "Fix $mat: reducing r2scan mixer beta $current_beta → $new_beta"

  # Patch beta in-place with sed to preserve comments and formatting
  sed -i "/^r2scan:/,/^[^ ]/ s/^\(  mixer:\)/\1/" "$DFT_ROOT/configs/default_params.yaml" || true
  python3 - <<PYEOF
import re, pathlib
p = pathlib.Path('$DFT_ROOT/configs/default_params.yaml')
txt = p.read_text()
# Replace beta value only inside the r2scan block's mixer section
txt = re.sub(
    r'(r2scan:.*?mixer:.*?beta:\s*)\S+',
    lambda m: m.group(1) + str($new_beta),
    txt, count=1, flags=re.DOTALL
)
p.write_text(txt)
print("YAML patched: r2scan.mixer.beta =", $new_beta)
PYEOF

  # Remove incomplete output
  rm -f "$WORKDIR/$mat/06_r2scan/r2scan.txt" \
        "$WORKDIR/$mat/06_r2scan/r2scan.gpw"
  mlog "Removed incomplete r2scan output for $mat"
}

# ── Relaunch helpers ─────────────────────────────────────────────────────────
relaunch_sn() {
  mlog "Relaunching MASnI3 CsSnI3 r2scan+..."
  cd "$DFT_ROOT"
  MPI_N=7 PHASES="MASnI3 CsSnI3" \
  STEPS="r2scan,soc_r2scan,effective_masses,score" \
  bash calculations/top8_r2scan/run_top8_r2scan.sh \
    >> "$WORKDIR/logs/sn_relaunch_$(date +%Y%m%d_%H%M%S).log" 2>&1 &
  mlog "Sn run relaunched PID $!"
}

relaunch_fa() {
  local remaining_phases=""
  for mat in FAPbI3 FAPbBr3 FASnI3 FASnBr3; do
    [[ ! -f "$WORKDIR/$mat/12_score/solar_score.json" ]] && remaining_phases="$remaining_phases $mat"
  done
  remaining_phases="${remaining_phases# }"  # trim leading space
  [[ -z "$remaining_phases" ]] && { mlog "All FA materials done, no relaunch needed"; return; }
  mlog "Relaunching FA: $remaining_phases"
  cd "$DFT_ROOT"
  MPI_N=7 PHASES="$remaining_phases" \
  STEPS="relax_sym,r2scan,soc_r2scan,effective_masses,score" \
  bash calculations/top8_r2scan/run_top8_r2scan.sh \
    >> "$WORKDIR/logs/fa_relaunch_$(date +%Y%m%d_%H%M%S).log" 2>&1 &
  mlog "FA run relaunched PID $!"
}

# ── Main check loop ──────────────────────────────────────────────────────────
run_checks() {
  mlog "=== Monitor check ==="

  # --- Sn materials (r²SCAN+U) ---
  local sn_action=0
  for mat in MASnI3 CsSnI3; do
    if ! check_r2scan_scf "$mat"; then
      kill_phase "$mat"
      fix_r2scan_mixer "$mat"
      sn_action=1
    elif ! check_r2scan_oscillation "$mat"; then
      kill_phase "$mat"
      fix_r2scan_oscillation "$mat"
      sn_action=1
    fi
  done

  # Relaunch Sn only if no Sn MPI active and some Sn material incomplete
  if [[ "$sn_action" -eq 1 ]]; then
    local sn_mpi_active=0
    for mat in MASnI3 CsSnI3; do
      local score_json="$WORKDIR/$mat/12_score/solar_score.json"
      [[ -f "$score_json" ]] && continue
      if pgrep -f "main.py run.*$mat" &>/dev/null; then
        sn_mpi_active=1; break
      fi
      if find "$WORKDIR/$mat" -maxdepth 3 -newer "$WORKDIR/$mat" -mmin -30 \
           -not -name "*.log" -print 2>/dev/null | grep -q .; then
        sn_mpi_active=1; break
      fi
    done
    [[ "$sn_mpi_active" -eq 0 ]] && relaunch_sn
  fi

  # --- FA materials: check r2scan SCF health, relaunch only if truly idle ---
  local fa_action=0
  for mat in FAPbI3 FAPbBr3 FASnI3 FASnBr3; do
    if ! check_r2scan_scf "$mat"; then
      kill_phase "$mat"
      fix_r2scan_mixer "$mat"
      fa_action=1
    elif ! check_r2scan_oscillation "$mat"; then
      kill_phase "$mat"
      fix_r2scan_oscillation "$mat"
      fa_action=1
    fi
  done

  # Relaunch only if: no FA MPI processes running AND some materials incomplete.
  # Use pgrep as primary signal; fallback to any recent file write in the mat dir
  # (30-min window covers r2scan → soc_r2scan transition where r2scan.txt goes stale).
  local fa_mpi_active=0
  for mat in FAPbI3 FAPbBr3 FASnI3 FASnBr3; do
    local score_json="$WORKDIR/$mat/12_score/solar_score.json"
    [[ -f "$score_json" ]] && continue  # fully done
    # Primary: process still alive
    if pgrep -f "main.py run.*$mat" &>/dev/null; then
      fa_mpi_active=1; break
    fi
    # Secondary: any file in the material dir modified in last 30 min
    if find "$WORKDIR/$mat" -maxdepth 3 -newer "$WORKDIR/$mat" -mmin -30 \
         -not -name "*.log" -print 2>/dev/null | grep -q .; then
      fa_mpi_active=1; break
    fi
  done

  if [[ "$fa_action" -eq 1 ]] || [[ "$fa_mpi_active" -eq 0 ]]; then
    local all_fa_done=1
    for mat in FAPbI3 FAPbBr3 FASnI3 FASnBr3; do
      [[ ! -f "$WORKDIR/$mat/12_score/solar_score.json" ]] && all_fa_done=0
    done
    if [[ "$all_fa_done" -eq 0 ]]; then
      [[ "$fa_mpi_active" -eq 0 ]] && mlog "No active FA MPI processes and materials incomplete — relaunching"
      relaunch_fa
    fi
  fi

  # --- Summary ---
  mlog "Done files:"
  for mat in MAPbI3 MASnI3 FAPbI3 FASnI3 CsSnI3 CsPbI3 FAPbBr3 FASnBr3; do
    local score="$WORKDIR/$mat/12_score/solar_score.json"
    local r2gpw="$WORKDIR/$mat/06_r2scan/r2scan.gpw"
    local sym="$WORKDIR/$mat/01_relax_sym/relax_sym.gpw"
    local status=""
    [[ -f "$score" ]]  && status="score✓"  || status="score✗"
    [[ -f "$r2gpw" ]]  && status="r2scan✓ $status" || status="r2scan✗ $status"
    [[ -f "$sym" ]]    && status="sym✓ $status"
    mlog "  $mat: $status"
  done
  mlog "=== End check ==="
}

# ── Entry point ──────────────────────────────────────────────────────────────
if [[ "${1:-}" == "--once" ]]; then
  run_checks
else
  while true; do
    run_checks
    mlog "Next check in 1800s"
    sleep 1800
  done
fi
