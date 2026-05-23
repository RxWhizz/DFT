#!/usr/bin/env bash
# status_report.sh — genera STATUS.md con estado de top8_r2scan cada 20 min.
# Uso:
#   bash scripts/status_report.sh --once    # una sola generación
#   bash scripts/status_report.sh --watch   # loop cada 20 min (background)
#   bash scripts/status_report.sh --live    # actualización con efecto cascada en terminal

set -uo pipefail

DFT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKDIR="$DFT_ROOT/calculations/top8_r2scan"
OUTPUT="$WORKDIR/STATUS.md"
EVENTS_LOG="$WORKDIR/logs/monitor_$(date +%Y%m%d).log"
INTERVAL=1200  # 20 minutos

MATERIALS=(MAPbI3 MASnI3 FAPbI3 FASnI3 CsSnI3 CsPbI3 FAPbBr3 FASnBr3)

# ── Helpers de lectura ────────────────────────────────────────────────────────

iter_count() {
  local txt="$1"
  [[ -f "$txt" ]] || { echo 0; return; }
  grep -c "^iter:" "$txt" 2>/dev/null || echo 0
}

last_n_iters() {
  local txt="$1" n="$2"
  [[ -f "$txt" ]] || return
  grep "^iter:" "$txt" 2>/dev/null | tail -"$n"
}

energy_spread() {
  local txt="$1" n="$2"
  [[ -f "$txt" ]] || { echo "--"; return; }
  local vals
  vals=$(grep "^iter:" "$txt" 2>/dev/null | tail -"$n" | awk '{print $4}')
  [[ -z "$vals" ]] && { echo "--"; return; }
  python3 -c "
vals=[float(x) for x in '''$vals'''.split() if x.lstrip('-').replace('.','').isdigit()]
print(f'{max(vals)-min(vals):.2f}') if len(vals)>1 else print('--')
" 2>/dev/null || echo "--"
}

last_iter_num() {
  local txt="$1"
  [[ -f "$txt" ]] || { echo "--"; return; }
  grep "^iter:" "$txt" 2>/dev/null | tail -1 | awk '{print $2}' || echo "--"
}

last_iter_time() {
  local txt="$1"
  [[ -f "$txt" ]] || { echo "--"; return; }
  grep "^iter:" "$txt" 2>/dev/null | tail -1 | awk '{print $3}' || echo "--"
}

bfgs_fmax() {
  local log="$1"
  [[ -f "$log" ]] || { echo "--"; return; }
  grep "^BFGS:" "$log" 2>/dev/null | tail -1 | awk '{print $5}' || echo "--"
}

bfgs_step() {
  local log="$1"
  [[ -f "$log" ]] || { echo 0; return; }
  grep -c "^BFGS:" "$log" 2>/dev/null || echo 0
}

cpu_mem() {
  local mat="$1"
  local pids
  pids=$(pgrep -f "main.py run.*--phase $mat" 2>/dev/null | tr '\n' ' ')
  [[ -z "$pids" ]] && { echo "--"; return; }
  # shellcheck disable=SC2086
  ps -p $pids -o %cpu,rss --no-headers 2>/dev/null \
    | awk '{cpu+=$1; mem+=$2} END {printf "CPU:%.0f%% MEM:%.1fGB", cpu, mem/1048576}' \
    || echo "--"
}

read_json_field() {
  local file="$1" field="$2"
  [[ -f "$file" ]] || { echo "--"; return; }
  python3 -c "
import json, sys
try:
    d = json.load(open('$file'))
    v = d
    for k in '$field'.split('.'):
        v = v[k]
    print(f'{float(v):.3f}' if isinstance(v, (int, float)) else str(v))
except: print('--')
" 2>/dev/null || echo "--"
}

# ── Detectar paso activo ──────────────────────────────────────────────────────

get_active_step() {
  local mat="$1"
  local d="$WORKDIR/$mat"

  [[ ! -f "$d/01_relax_sym/relax_sym.gpw" ]] && \
    [[ -d "$d/01_relax_sym" ]] && { echo "relax_sym"; return; }

  [[ ! -f "$d/06_r2scan/r2scan.gpw" ]] && { echo "r2scan"; return; }

  [[ ! -f "$d/06_r2scan/r2scan_bandgap.json" ]] && { echo "r2scan_post"; return; }

  [[ ! -f "$d/06_r2scan/soc_r2scan_eigenvalues.npy" ]] && { echo "soc_r2scan"; return; }

  [[ ! -f "$d/10_effective_masses/electronic_analysis.json" ]] && { echo "masas_ef"; return; }

  [[ ! -f "$d/12_score/solar_score.json" ]] && { echo "score"; return; }

  echo "listo"
}

is_process_active() {
  local mat="$1"
  local txt="$WORKDIR/$mat/06_r2scan/r2scan.txt"
  local sym_txt="$WORKDIR/$mat/01_relax_sym/relax_sym.txt"
  pgrep -f "main.py run.*--phase $mat" &>/dev/null && return 0
  { [[ -f "$txt" ]] && find "$txt" -mmin -10 -print 2>/dev/null | grep -q .; } && return 0
  { [[ -f "$sym_txt" ]] && find "$sym_txt" -mmin -10 -print 2>/dev/null | grep -q .; } && return 0
  return 1
}

# ── Construir contenido del reporte ──────────────────────────────────────────

build_report() {
  local now next tmp
  now=$(date "+%Y-%m-%d %H:%M %Z")
  next=$(date -d "+20 minutes" "+%H:%M" 2>/dev/null || date -v +20M "+%H:%M" 2>/dev/null || echo "~20min")
  tmp=$(mktemp)

  # ── Encabezado ────────────────────────────────────────────────────────────
  cat >> "$tmp" <<EOF
# top8\_r2scan — Estado de simulacion

**Actualizado:** $now | **Proximo update:** $next

---

## Resumen

| Material | Paso activo | Iter SCF | Spread (eV) | Gap r2SCAN | Score        | Estado    |
|----------|-------------|----------|-------------|------------|--------------|-----------|
EOF

  local done_mats=() active_mats=() queued_mats=()

  for mat in "${MATERIALS[@]}"; do
    local d="$WORKDIR/$mat"
    local step; step=$(get_active_step "$mat")
    local iter_val spread_val gap_val score_val estado

    local bg_json="$d/06_r2scan/r2scan_bandgap.json"
    local score_json="$d/12_score/solar_score.json"
    gap_val=$(read_json_field "$bg_json" "gap_eV")
    local grade; grade=$(read_json_field "$score_json" "grade")
    local score_num; score_num=$(read_json_field "$score_json" "total_score")
    [[ "$grade" != "--" ]] && score_val="$score_num ($grade)" || score_val="--"

    if [[ "$step" == "listo" ]]; then
      estado="Listo"
      iter_val="--"; spread_val="--"
      done_mats+=("$mat")
    elif is_process_active "$mat"; then
      estado="En proceso"
      active_mats+=("$mat")
      local r2_txt="$d/06_r2scan/r2scan.txt"
      local sym_txt="$d/01_relax_sym/relax_sym.txt"
      if [[ "$step" == "relax_sym" ]]; then
        iter_val=$(last_iter_num "$sym_txt")
        spread_val=$(energy_spread "$sym_txt" 10)
        local fmax; fmax=$(bfgs_fmax "$d/01_relax_sym/relax_sym.log")
        [[ "$fmax" != "--" ]] && spread_val="fmax=$fmax"
      else
        iter_val=$(last_iter_num "$r2_txt")
        spread_val=$(energy_spread "$r2_txt" 20)
      fi
    else
      estado="En cola"
      iter_val="--"; spread_val="--"
      queued_mats+=("$mat")
    fi

    printf "| %-8s | %-11s | %-8s | %-11s | %-10s | %-12s | %-9s |\n" \
      "$mat" "$step" "$iter_val" "$spread_val" "$gap_val" "$score_val" "$estado" >> "$tmp"
  done

  # ── Detalle materiales en proceso ─────────────────────────────────────────
  if [[ ${#active_mats[@]} -gt 0 ]]; then
    printf "\n---\n\n## Detalle — materiales en proceso\n" >> "$tmp"

    for mat in "${active_mats[@]}"; do
      local d="$WORKDIR/$mat"
      local step; step=$(get_active_step "$mat")
      local recursos; recursos=$(cpu_mem "$mat")

      printf "\n### %s · %s\n" "$mat" "$step" >> "$tmp"

      if [[ "$step" == "relax_sym" ]]; then
        local sym_log="$d/01_relax_sym/relax_sym.log"
        local sym_txt="$d/01_relax_sym/relax_sym.txt"
        local bstep; bstep=$(bfgs_step "$sym_log")
        local fmax; fmax=$(bfgs_fmax "$sym_log")
        printf "\n**BFGS paso %s | fmax = %s eV/Ang** | %s\n\n\`\`\`\n" \
          "$bstep" "$fmax" "$recursos" >> "$tmp"
        last_n_iters "$sym_txt" 5 >> "$tmp" 2>/dev/null || true
        printf "\`\`\`\n" >> "$tmp"
      else
        local r2_txt="$d/06_r2scan/r2scan.txt"
        local iter_n; iter_n=$(last_iter_num "$r2_txt")
        local t; t=$(last_iter_time "$r2_txt")
        printf "\n**iter %s** @ %s | %s\n\n\`\`\`\n" "$iter_n" "$t" "$recursos" >> "$tmp"
        last_n_iters "$r2_txt" 5 >> "$tmp" 2>/dev/null || true
        printf "\`\`\`\n" >> "$tmp"
      fi
    done
  fi

  # ── Tabla completados ─────────────────────────────────────────────────────
  if [[ ${#done_mats[@]} -gt 0 ]]; then
    printf "\n---\n\n## Completados\n\n" >> "$tmp"
    printf "| Material | Gap (eV) | Tipo     | m_e (m0) | m_h (m0) | Score | Grado |\n" >> "$tmp"
    printf "|----------|----------|----------|----------|----------|-------|-------|\n" >> "$tmp"

    for mat in "${done_mats[@]}"; do
      local d="$WORKDIR/$mat"
      local bg_json="$d/06_r2scan/r2scan_bandgap.json"
      local score_json="$d/12_score/solar_score.json"
      local em_json="$d/10_effective_masses/electronic_analysis.json"

      local gap; gap=$(read_json_field "$bg_json" "gap_eV")
      local gtype; gtype=$(read_json_field "$bg_json" "gap_type")
      local me; me=$(read_json_field "$em_json" "m_e_soc_m0")
      [[ "$me" == "--" ]] && me=$(read_json_field "$em_json" "m_e_m0")
      local mh; mh=$(read_json_field "$em_json" "m_h_soc_m0")
      [[ "$mh" == "--" ]] && mh=$(read_json_field "$em_json" "m_h_m0")
      local score; score=$(read_json_field "$score_json" "total_score")
      local grade; grade=$(read_json_field "$score_json" "grade")

      printf "| %-8s | %-8s | %-8s | %-8s | %-8s | %-5s | %-5s |\n" \
        "$mat" "$gap" "$gtype" "$me" "$mh" "$score" "$grade" >> "$tmp"
    done
  fi

  # ── Eventos recientes del monitor ─────────────────────────────────────────
  if [[ -f "$EVENTS_LOG" ]]; then
    printf "\n---\n\n## Eventos recientes (monitor)\n\n\`\`\`\n" >> "$tmp"
    grep -E "DIVERGE|KILL|Fix|relaunch|Relaunching|DONE|FAILED|started" "$EVENTS_LOG" \
      2>/dev/null | tail -15 | sed 's/\[//;s/\]//' >> "$tmp" || true
    printf "\`\`\`\n" >> "$tmp"
  fi

  printf "\n---\n*Generado por \`scripts/status_report.sh\` · intervalo 20 min*\n" >> "$tmp"

  echo "$tmp"
}

# ── Efecto cascada en terminal ────────────────────────────────────────────────

render_live() {
  local tmp
  tmp=$(build_report)
  local lines
  mapfile -t lines < "$tmp"
  rm -f "$tmp"

  local total=${#lines[@]}
  local cols rows
  cols=$(tput cols 2>/dev/null || echo 120)
  rows=$(tput lines 2>/dev/null || echo 40)

  # Limpiar pantalla y mover cursor al fondo
  tput clear 2>/dev/null || printf '\033[2J'
  tput cup "$rows" 0 2>/dev/null || printf '\033[%d;0H' "$rows"

  # Imprimir lineas de abajo hacia arriba
  local start_row=$(( rows - total ))
  [[ "$start_row" -lt 0 ]] && start_row=0

  local i=0
  for line in "${lines[@]}"; do
    local row=$(( start_row + i ))
    tput cup "$row" 0 2>/dev/null || printf '\033[%d;0H' "$row"
    # Truncar si la linea excede el ancho de la terminal
    printf '%.*s\n' "$cols" "$line"
    sleep 0.03
    (( i++ )) || true
  done
}

# ── Entry point ───────────────────────────────────────────────────────────────
mkdir -p "$WORKDIR/logs"

case "${1:---watch}" in
  --once)
    tmp=$(build_report)
    mv "$tmp" "$OUTPUT"
    echo "STATUS.md generado: $OUTPUT"
    ;;
  --watch)
    echo "Iniciando monitor — actualizacion cada ${INTERVAL}s → $OUTPUT"
    while true; do
      tmp=$(build_report)
      mv "$tmp" "$OUTPUT"
      sleep "$INTERVAL"
    done
    ;;
  --live)
    echo "Modo en vivo — actualizacion cada ${INTERVAL}s (Ctrl+C para salir)"
    while true; do
      render_live
      sleep "$INTERVAL"
    done
    ;;
  *)
    echo "Uso: $0 [--once|--watch|--live]" >&2
    exit 1
    ;;
esac
