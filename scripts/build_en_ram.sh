#!/usr/bin/env bash
# Redirige los directorios de compilación a tmpfs (/dev/shm).
#
# Por qué existe esto: `build/`, `dist/` y el build de Flutter son symlinks a un
# disco NTFS montado con el driver `ntfs3` del kernel. Una compilación son
# millones de operaciones sobre archivos pequeños y borrados masivos, que es
# justo lo que peor lleva ese driver: una compilación se atascó con `cmake` en
# estado D —espera de E/S ininterrumpible— bloqueado en `vfs_unlink`, y el
# kworker del driver colgado 34 minutos. No se destrabó sin reiniciar. Antes, un
# `cp` había terminado en Segmentation fault en el mismo árbol.
#
# tmpfs vive en RAM: no toca disco, es mucho más rápido, y los intermedios de
# compilación son desechables por definición. El disco local no sirve de
# alternativa porque está al 96 %.
#
# tmpfs se vacía al reiniciar. Vuelve a ejecutar este script antes de compilar.
#
#   bash scripts/build_en_ram.sh              # activa
#   bash scripts/build_en_ram.sh --restore    # devuelve los symlinks al disco
#   bash scripts/build_en_ram.sh --status     # dónde apunta cada uno
set -euo pipefail

ROOT="$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RAM_ROOT="${DFT_RAM_BUILD_ROOT:-/dev/shm/dft-build}"
ESTADO="$ROOT/.build-ram-state"

# Directorios a redirigir: ruta relativa en el repo → subdirectorio en tmpfs.
ENLACES=(
  "build:pyinstaller"
  "dist:dist"
  "apps/dft_monitor_flutter/build:flutter"
)

# Espacio mínimo razonable: motor congelado + bundle + tarballs, con holgura.
MIN_LIBRE_MB=6000

estado() {
  for par in "${ENLACES[@]}"; do
    local rel="${par%%:*}" destino="—"
    [ -L "$ROOT/$rel" ] && destino="$(readlink "$ROOT/$rel")"
    if [ "${destino#$RAM_ROOT}" != "$destino" ]; then
      printf "  %-34s RAM   %s\n" "$rel" "$destino"
    else
      printf "  %-34s disco %s\n" "$rel" "$destino"
    fi
  done
}

case "${1:-}" in
  --status)
    echo "Directorios de compilación:"; estado; exit 0 ;;

  --restore)
    [ -f "$ESTADO" ] || { echo "No hay estado guardado: nada que restaurar." >&2; exit 1; }
    while IFS='|' read -r rel anterior; do
      [ -n "$rel" ] || continue
      rm -f "$ROOT/$rel"
      ln -sfn "$anterior" "$ROOT/$rel"
      echo "  $rel -> $anterior"
    done < "$ESTADO"
    rm -f "$ESTADO"
    echo "Symlinks devueltos al disco. Los intermedios en RAM siguen en $RAM_ROOT."
    exit 0 ;;

  ""|--activar) ;;
  *) echo "Uso: $0 [--status|--restore]" >&2; exit 2 ;;
esac

# ── Comprobar que hay sitio ──────────────────────────────────────────────────
LIBRE_MB=$(df -Pm /dev/shm | awk 'NR==2{print $4}')
if [ "$LIBRE_MB" -lt "$MIN_LIBRE_MB" ]; then
  echo "Solo hay ${LIBRE_MB} MB libres en /dev/shm; hacen falta ~${MIN_LIBRE_MB}." >&2
  echo "Libera memoria o amplía el tmpfs:" >&2
  echo "  sudo mount -o remount,size=16G /dev/shm" >&2
  exit 1
fi

# ── Redirigir ────────────────────────────────────────────────────────────────
# El estado solo se escribe la primera vez: si ya está activo, los targets
# actuales apuntan a RAM y guardarlos perdería los originales para siempre.
GUARDAR=true
[ -f "$ESTADO" ] && GUARDAR=false

for par in "${ENLACES[@]}"; do
  rel="${par%%:*}"; sub="${par##*:}"
  ram="$RAM_ROOT/$sub"
  mkdir -p "$ram"

  if [ -L "$ROOT/$rel" ]; then
    anterior="$(readlink "$ROOT/$rel")"
    [ "$anterior" = "$ram" ] && { echo "  $rel ya está en RAM"; continue; }
    $GUARDAR && echo "$rel|$anterior" >> "$ESTADO"
    rm -f "$ROOT/$rel"
  elif [ -d "$ROOT/$rel" ]; then
    echo "  aviso: $rel es un directorio real, no un symlink — se deja intacto" >&2
    continue
  fi

  mkdir -p "$(dirname "$ROOT/$rel")"
  ln -sfn "$ram" "$ROOT/$rel"
  echo "  $rel -> $ram"
done

echo
echo "Compilación en RAM activa. $(df -Ph /dev/shm | awk 'NR==2{print $4}') libres en /dev/shm."
echo
echo "  bash scripts/build_desktop.sh"
echo "  bash scripts/build_web.sh"
echo
echo "Los .tar.gz quedarán en dist/ (en RAM): cópialos a un sitio persistente"
echo "antes de reiniciar, o se pierden."
