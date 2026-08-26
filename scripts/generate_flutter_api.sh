#!/usr/bin/env bash
# Generates a Dart client from the monitor OpenAPI schema when the Java-based
# OpenAPI generator is available.
set -euo pipefail

ROOT="$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ -d "/media/luis-ochoa/Nuevo vol" ]; then
  DFT_WORK_ROOT="${DFT_WORK_ROOT:-/media/luis-ochoa/Nuevo vol/DFT-work}"
  mkdir -p "$DFT_WORK_ROOT/tmp" "$DFT_WORK_ROOT/npm-cache"
  export DFT_WORK_ROOT
  export TMPDIR="${TMPDIR:-$DFT_WORK_ROOT/tmp}"
  export npm_config_cache="${npm_config_cache:-$DFT_WORK_ROOT/npm-cache}"
fi

PY="${PYTHON:-$ROOT/.venv/bin/python}"
if [ ! -x "$PY" ]; then
  PY="$(command -v python3 || command -v python || true)"
fi
[ -n "$PY" ] || { echo "ERROR: Python not found" >&2; exit 1; }

PYTHONPATH="$ROOT/src" "$PY" scripts/dump_openapi.py

OUT="$ROOT/apps/dft_monitor_flutter/packages/monitor_api_client"
mkdir -p "$(dirname "$OUT")"

if ! command -v java >/dev/null 2>&1; then
  echo "ERROR: Java 11+ not found in PATH. Set JAVA_HOME/PATH before generating the Dart client." >&2
  exit 1
fi

JAVA_VERSION="$(java -version 2>&1 | sed -n '1p')"
if [[ "$JAVA_VERSION" =~ \"1\.([0-9]+) ]]; then
  JAVA_MAJOR="${BASH_REMATCH[1]}"
elif [[ "$JAVA_VERSION" =~ \"([0-9]+) ]]; then
  JAVA_MAJOR="${BASH_REMATCH[1]}"
else
  JAVA_MAJOR=0
fi
if [ "$JAVA_MAJOR" -lt 11 ]; then
  echo "ERROR: Java 11+ is required by the configured OpenAPI generator; found: $JAVA_VERSION" >&2
  exit 1
fi

OPENAPI_GENERATOR_NPM="${OPENAPI_GENERATOR_NPM:-@openapitools/openapi-generator-cli@2.15.3}"
if command -v openapi-generator-cli >/dev/null 2>&1; then
  openapi-generator-cli generate \
    -i "$ROOT/src/monitor_api/openapi.json" \
    -g dart-dio \
    -o "$OUT" \
    --additional-properties=pubName=monitor_api_client,serializationLibrary=json_serializable
elif command -v npx >/dev/null 2>&1; then
  npx --yes "$OPENAPI_GENERATOR_NPM" generate \
    -i "$ROOT/src/monitor_api/openapi.json" \
    -g dart-dio \
    -o "$OUT" \
    --additional-properties=pubName=monitor_api_client,serializationLibrary=json_serializable
else
  echo "ERROR: install openapi-generator-cli or npx to generate dart-dio client" >&2
  exit 1
fi

if [ -f "$OUT/pubspec.yaml" ]; then
  sed -i \
    -e "s/sdk: '>=3\\.5\\.0 <4\\.0\\.0'/sdk: '>=3.8.0 <4.0.0'/" \
    -e "s/json_annotation: '\\^4\\.9\\.0'/json_annotation: '^4.12.0'/" \
    "$OUT/pubspec.yaml"
fi
if [ -f "$OUT/analysis_options.yaml" ] && ! grep -q "unused_import:" "$OUT/analysis_options.yaml"; then
  sed -i "/deprecated_member_use_from_same_package: ignore/a\\    unused_import: ignore" \
    "$OUT/analysis_options.yaml"
fi
