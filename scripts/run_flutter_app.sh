#!/usr/bin/env bash
# Launches the Flutter desktop app with the local Python engine.
set -euo pipefail

ROOT="$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$ROOT/apps/dft_monitor_flutter"

if [ -d "/media/luis-ochoa/Nuevo vol" ]; then
  DFT_WORK_ROOT="${DFT_WORK_ROOT:-/media/luis-ochoa/Nuevo vol/DFT-work}"
else
  DFT_WORK_ROOT="${DFT_WORK_ROOT:-$ROOT/.dft-work}"
fi

mkdir -p "$DFT_WORK_ROOT/tmp" "$DFT_WORK_ROOT/runtime/config" "$DFT_WORK_ROOT/logs"
export DFT_WORK_ROOT
export TMPDIR="${TMPDIR:-$DFT_WORK_ROOT/tmp}"
export DFT_MONITOR_CONFIG_DIR="${DFT_MONITOR_CONFIG_DIR:-$DFT_WORK_ROOT/runtime/config}"
export DFT_MONITOR_ENGINE="${DFT_MONITOR_ENGINE:-$ROOT/bin/dft-monitor-web}"

BUNDLE_EXE="$APP/build/linux/x64/release/bundle/dft_monitor_flutter"
if [ -x "$BUNDLE_EXE" ]; then
  exec "$BUNDLE_EXE"
fi

cd "$APP"
exec flutter run -d linux
