#!/usr/bin/env bash
# Builds the Flutter desktop app with the embedded Python engine for the host OS.
# Run this script on Linux to produce Linux, and on Windows to produce Windows.
set -euo pipefail

ROOT="$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Copia un árbol con reintento.
#
# Una compilación abortó con `cp -a` terminando en Segmentation fault sobre
# ntfs3, que es donde vive este repositorio vía symlinks al disco externo. No se
# ha podido reproducir después —ni con `-a` ni sin él—, así que la causa real
# queda sin confirmar: probablemente el driver ntfs3, que es intermitente.
#
# Lo que sí es seguro es que con `set -e` ese fallo tiraba la compilación entera
# tras veinte minutos de trabajo. Se prescinde de `-a` (propietario, ACLs y
# xattrs no aportan nada aquí; los permisos sí) y se añade un camino de
# recuperación con tar, que no comparte implementación con cp.
copiar_arbol() {
  local origen="$1" destino="$2"
  mkdir -p "$destino"
  if ! cp -R --preserve=mode "$origen"/. "$destino"/; then
    echo "  aviso: cp falló copiando $origen — reintentando con tar" >&2
    (cd "$origen" && tar cf - .) | (cd "$destino" && tar xf -)
  fi
}

APP="$ROOT/apps/dft_monitor_flutter"
cd "$ROOT"

if [ -d "/media/luis-ochoa/Nuevo vol" ]; then
  DFT_WORK_ROOT="${DFT_WORK_ROOT:-/media/luis-ochoa/Nuevo vol/DFT-work}"
  mkdir -p "$DFT_WORK_ROOT/tmp" "$DFT_WORK_ROOT/pyinstaller-cache"
  export DFT_WORK_ROOT
  export TMPDIR="${TMPDIR:-$DFT_WORK_ROOT/tmp}"
  export PYINSTALLER_CONFIG_DIR="${PYINSTALLER_CONFIG_DIR:-$DFT_WORK_ROOT/pyinstaller-cache}"
fi

if ! command -v flutter >/dev/null 2>&1; then
  for sdk in \
    "${FLUTTER_HOME:-}" \
    "$HOME/flutter" \
    "/media/luis-ochoa/Nuevo vol/flutter"
  do
    if [ -n "$sdk" ] && [ -x "$sdk/bin/flutter" ]; then
      export PATH="$sdk/bin:$PATH"
      break
    fi
  done
fi
command -v flutter >/dev/null 2>&1 || {
  echo "ERROR: Flutter SDK not found in PATH" >&2
  exit 1
}

PY="${PYTHON:-$ROOT/.venv/bin/python}"
if [ ! -x "$PY" ]; then
  PY="$(command -v python3 || command -v python || true)"
fi
[ -n "$PY" ] || { echo "ERROR: Python not found" >&2; exit 1; }

VERSION="$("$PY" -c "import sys; sys.path.insert(0,'src'); import monitor_api; print(monitor_api.__version__)")"

case "$(uname -s)" in
  Linux)
    PLATFORM="linux-$(uname -m)"
    FLUTTER_TARGET="linux"
    BUNDLE="$APP/build/linux/x64/release/bundle"
    ARCHIVE_EXT="tar.gz"
    ;;
  MINGW*|MSYS*|CYGWIN*)
    PLATFORM="windows-x64"
    FLUTTER_TARGET="windows"
    BUNDLE="$APP/build/windows/x64/runner/Release"
    ARCHIVE_EXT="zip"
    ;;
  *)
    echo "ERROR: unsupported host OS for this v1 script" >&2
    exit 1
    ;;
esac

echo "▸ Preparing structures"
PYTHONPATH="$ROOT/src" "$PY" scripts/pregenerate_structures.py --out build/structures --clean >/dev/null

echo "▸ Building embedded engine"
rm -rf build/dft-monitor-engine dist/dft-monitor-engine
"$PY" -m PyInstaller packaging/dft-monitor-engine.spec --noconfirm --log-level WARN

ENGINE_SRC="$ROOT/dist/dft-monitor-engine"
[ -d "$ENGINE_SRC" ] || { echo "ERROR: engine build missing: $ENGINE_SRC" >&2; exit 1; }

echo "▸ Staging engine resources"
rm -rf "$APP/assets/engine"
mkdir -p "$APP/assets/engine"
printf 'Engine is copied next to the Flutter executable during packaging.\n' > "$APP/assets/engine/README.txt"

echo "▸ Building Flutter $FLUTTER_TARGET"
(
  cd "$APP"
  flutter pub get

  # Flutter 3.47 referencia `build/native_assets/<plataforma>` desde su
  # cmake_install.cmake, pero no lo crea cuando el proyecto no declara assets
  # nativos. Con un `build/` virgen —CI, tras `flutter clean`, o al mover el
  # directorio a tmpfs— la instalación aborta con «file INSTALL cannot find».
  # Hasta ahora esto pasaba inadvertido porque el directorio sobrevivía de
  # compilaciones anteriores: la build no era reproducible desde cero.
  mkdir -p "build/native_assets/$FLUTTER_TARGET"

  flutter build "$FLUTTER_TARGET" --release
)

rm -rf "$BUNDLE/engine"
mkdir -p "$BUNDLE/engine"
copiar_arbol "$ENGINE_SRC" "$BUNDLE/engine"
if [ "$FLUTTER_TARGET" = "linux" ]; then
  chmod +x "$BUNDLE/engine/dft-monitor-engine"
fi

OUT_NAME="dft-monitor-desktop-${VERSION}-${PLATFORM}"
OUT_DIR="$ROOT/dist/$OUT_NAME"
rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"
copiar_arbol "$BUNDLE" "$OUT_DIR"

echo "▸ Smoke testing engine contract"
ENGINE_BIN="$OUT_DIR/engine/dft-monitor-engine"
if [ "$FLUTTER_TARGET" = "windows" ]; then
  ENGINE_BIN="$OUT_DIR/engine/dft-monitor-engine.exe"
fi
[ -x "$ENGINE_BIN" ] || [ -f "$ENGINE_BIN" ] || {
  echo "ERROR: embedded engine binary missing at $ENGINE_BIN" >&2
  exit 1
}
if [ "$FLUTTER_TARGET" = "linux" ]; then
  chmod +x "$ENGINE_BIN"
fi

SMOKE="$(mktemp -d)"
SMOKE_PID=""
cleanup() {
  [ -n "$SMOKE_PID" ] && kill "$SMOKE_PID" 2>/dev/null || true
  rm -rf "$SMOKE"
}
trap cleanup EXIT
mkdir -p "$SMOKE/cfg" "$SMOKE/data/local_runs"
DFT_MONITOR_CONFIG_DIR="$SMOKE/cfg" "$ENGINE_BIN" \
  --engine --port 0 --print-ready-json --data-root "$SMOKE/data" \
  > "$SMOKE/ready.jsonl" 2> "$SMOKE/engine.log" &
SMOKE_PID=$!

for _ in $(seq 1 90); do
  if [ -s "$SMOKE/ready.jsonl" ]; then
    break
  fi
  sleep 0.5
done

"$PY" - "$SMOKE/ready.jsonl" <<'PYCHECK'
import json, sys, urllib.request
payload = None
for line in open(sys.argv[1], encoding="utf-8", errors="replace"):
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        continue
    if data.get("event") == "ready":
        payload = data
        break
if payload is None:
    raise SystemExit("ready JSON not found in engine stdout")
assert payload["base_url"].startswith("http://127.0.0.1:")
with urllib.request.urlopen(payload["base_url"] + "/api/health", timeout=10) as r:
    health = json.load(r)
assert "version" in health
PYCHECK
kill "$SMOKE_PID" 2>/dev/null || true
SMOKE_PID=""

echo "▸ Packaging"
cd "$ROOT/dist"
if [ "$ARCHIVE_EXT" = "zip" ]; then
  rm -f "$OUT_NAME.zip"
  "$PY" -c "import shutil,sys; shutil.make_archive(sys.argv[1], 'zip', '.', sys.argv[1])" "$OUT_NAME"
  ARTEFACTO="$OUT_NAME.zip"
else
  rm -f "$OUT_NAME.tar.gz"
  tar czf "$OUT_NAME.tar.gz" "$OUT_NAME"
  ARTEFACTO="$OUT_NAME.tar.gz"
fi

if command -v sha256sum >/dev/null 2>&1; then
  sha256sum "$ARTEFACTO" > "$ARTEFACTO.sha256"
fi

echo
echo "  artefacto: dist/$ARTEFACTO"
