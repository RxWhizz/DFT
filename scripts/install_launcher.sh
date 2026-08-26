#!/usr/bin/env bash
# Deja `dft-monitor` disponible como comando y en el menú de aplicaciones.
#
#   bash scripts/install_launcher.sh            # instalar
#   bash scripts/install_launcher.sh --uninstall
#
# Todo va al perfil del usuario (~/.local). No usa sudo ni toca el sistema.
set -euo pipefail

ROOT="$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_ORIGEN="$ROOT/bin/dft-monitor-web"
BIN_DESTINO="$HOME/.local/bin/dft-monitor-web"
DESKTOP_DESTINO="$HOME/.local/share/applications/dft-monitor-web.desktop"

# Nombres anteriores al esquema web/desktop. Se retiran siempre: dejarlos
# convivía con los nuevos y era imposible saber cuál lanzaba qué.
LEGADO=(
  "$HOME/.local/bin/dft-monitor"
  "$HOME/.local/share/applications/dft-monitor.desktop"
)

quitar_legado() {
  local quitados=0
  for viejo in "${LEGADO[@]}"; do
    [ -e "$viejo" ] || [ -L "$viejo" ] || continue
    rm -f "$viejo" && quitados=$((quitados + 1))
  done
  [ "$quitados" -gt 0 ] && echo "Retirados $quitados lanzadores con el nombre antiguo."
  return 0
}

if [ "${1:-}" = "--uninstall" ]; then
  rm -f "$BIN_DESTINO" "$DESKTOP_DESTINO"
  quitar_legado
  rm -f "$HOME/.local/share/applications/dft-monitor-desktop.desktop"
  rm -f "$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")/dft-monitor-desktop.desktop"
  for s in 32 64 128 256 512; do
    rm -f "$HOME/.local/share/icons/hicolor/${s}x${s}/apps/dft-monitor.png"
  done
  rm -rf "$HOME/.local/opt/dft-monitor"
  command -v update-desktop-database >/dev/null 2>&1 &&
    update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
  echo "Desinstalado. El repositorio queda intacto."
  exit 0
fi

[ -x "$BIN_ORIGEN" ] || { echo "No se encuentra $BIN_ORIGEN" >&2; exit 1; }

quitar_legado

# ── App de escritorio (Flutter) ──────────────────────────────────────────────
APP_DIR="$ROOT/apps/dft_monitor_flutter"
APP_BUNDLE="$APP_DIR/build/linux/x64/release/bundle"
APP_DESKTOP="$HOME/.local/share/applications/dft-monitor-desktop.desktop"
ICON_THEME="$HOME/.local/share/icons/hicolor"

# La app se copia fuera del árbol de compilación: build/ y dist/ son symlinks al
# disco externo, y un acceso directo que apunte ahí muere cuando el disco no
# está montado. Además sobrevive a `flutter clean`.
APP_HOME="$HOME/.local/opt/dft-monitor"
APP_EXEC="$APP_HOME/dft_monitor_flutter"

instalar_app() {
  local origen="$1"
  local necesario libre
  necesario=$(du -sk "$origen" | cut -f1)
  libre=$(df -Pk "$HOME" | tail -1 | awk '{print $4}')
  if [ "$libre" -lt $((necesario + 262144)) ]; then
    echo "ERROR: hacen falta ~$((necesario / 1024)) MB en \$HOME y hay $((libre / 1024)) MB." >&2
    return 1
  fi
  rm -rf "$APP_HOME"
  mkdir -p "$(dirname "$APP_HOME")"
  # Sin `-a`: propietario, ACLs y xattrs no aportan nada al instalar, y una
  # compilación llegó a abortar con cp segfaultando sobre ntfs3. Los permisos
  # sí importan —el ejecutable y el motor—, de ahí --preserve=mode.
  if ! cp -R --preserve=mode "$origen" "$APP_HOME" 2>/dev/null; then
    mkdir -p "$APP_HOME"
    (cd "$origen" && tar cf - .) | (cd "$APP_HOME" && tar xf -)
  fi
  chmod +x "$APP_EXEC"
  [ -f "$APP_HOME/engine/dft-monitor-engine" ] && chmod +x "$APP_HOME/engine/dft-monitor-engine"
  echo "App instalada:       $APP_HOME ($((necesario / 1024)) MB)"
}

instalar_iconos() {
  local origen="$APP_DIR/assets/app"
  [ -d "$origen" ] || return 1
  local n=0
  for s in 32 64 128 256 512; do
    [ -f "$origen/app_icon_${s}.png" ] || continue
    mkdir -p "$ICON_THEME/${s}x${s}/apps"
    install -m 644 "$origen/app_icon_${s}.png" "$ICON_THEME/${s}x${s}/apps/dft-monitor.png"
    n=$((n + 1))
  done
  command -v gtk-update-icon-cache >/dev/null 2>&1 &&
    gtk-update-icon-cache -f -t "$ICON_THEME" >/dev/null 2>&1 || true
  echo "Iconos instalados:   $n tamaños en el tema hicolor"
}

# El acceso directo del escritorio: en GNOME hace falta ejecutable + marcado
# como de confianza, o aparece como «Archivo de texto» sin icono.
confiar_en_escritorio() {
  local destino="$1"
  chmod +x "$destino"
  command -v gio >/dev/null 2>&1 &&
    gio set "$destino" metadata::trusted true 2>/dev/null || true
}

mkdir -p "$(dirname "$BIN_DESTINO")" "$(dirname "$DESKTOP_DESTINO")"

# Symlink, no copia: el lanzador resuelve la raíz del repo siguiendo enlaces, y
# así los cambios en el repo se reflejan sin reinstalar.
ln -sfn "$BIN_ORIGEN" "$BIN_DESTINO"
echo "Comando instalado:  $BIN_DESTINO -> $BIN_ORIGEN"

sed "s|__EXEC__|$BIN_ORIGEN|" "$ROOT/packaging/dft-monitor-web.desktop" > "$DESKTOP_DESTINO"
chmod 644 "$DESKTOP_DESTINO"
echo "Entrada de menú:    $DESKTOP_DESTINO"

# ── Entrada de la app de escritorio ─────────────────────────────────────────
if [ -x "$APP_BUNDLE/dft_monitor_flutter" ]; then
  instalar_iconos || echo "Aviso: no se encontraron los iconos en $APP_DIR/assets/app"
  instalar_app "$APP_BUNDLE" || exit 1

  # Si el motor congelado viaja dentro (lo pone build_desktop.sh), el
  # resolutor lo encuentra solo en engine/ y la app es autónoma. Si no, se le
  # señala el lanzador del repo, que necesita el venv.
  if [ -x "$APP_HOME/engine/dft-monitor-engine" ]; then
    ENGINE_REF="$APP_HOME/engine/dft-monitor-engine"
    echo "Motor embebido:      sí (app autónoma)"
  else
    ENGINE_REF="$BIN_ORIGEN"
    echo "Motor embebido:      no — se usará $BIN_ORIGEN (requiere el repo y su venv)"
  fi

  sed -e "s|__EXEC__|$APP_EXEC|" \
      -e "s|__ENGINE__|$ENGINE_REF|" \
      -e "s|__APPDIR__|$APP_HOME|" \
      -e "s|__DATAROOT__|${DFT_DATA_ROOT:-$ROOT}|" \
      "$ROOT/packaging/dft-monitor-desktop.desktop" > "$APP_DESKTOP"
  chmod 644 "$APP_DESKTOP"
  echo "Raíz de datos:       ${DFT_DATA_ROOT:-$ROOT}"
  echo "App de escritorio:   $APP_DESKTOP"

  DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
  if [ -d "$DESKTOP_DIR" ]; then
    cp "$APP_DESKTOP" "$DESKTOP_DIR/dft-monitor-desktop.desktop"
    confiar_en_escritorio "$DESKTOP_DIR/dft-monitor-desktop.desktop"
    echo "Acceso directo:      $DESKTOP_DIR/dft-monitor-desktop.desktop"
  fi
else
  echo "Aviso: sin bundle de Flutter compilado — se omite la app de escritorio."
  echo "       bash scripts/build_desktop.sh   (incluye el motor embebido)"
fi

command -v update-desktop-database >/dev/null 2>&1 &&
  update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

echo
echo "───────────────────────────────────────────────────────────────"
echo "  Monitor DFT              app de escritorio, motor embebido."
echo "                           Icono del escritorio o del menú."
echo "                           Autónoma: sin Python ni repositorio."
echo
echo "  dft-monitor-web          servidor que se abre en el navegador."
echo "                           Para la LAN usa --host 0.0.0.0 (pide token)."
echo "───────────────────────────────────────────────────────────────"

case ":$PATH:" in
  *":$HOME/.local/bin:"*) echo; echo "Listo. Ejecuta:  dft-monitor-web" ;;
  *)
    echo
    echo "~/.local/bin no está en el PATH. Añádelo:"
    echo "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc && source ~/.bashrc"
    echo
    echo "Mientras tanto:  $BIN_ORIGEN"
    ;;
esac
