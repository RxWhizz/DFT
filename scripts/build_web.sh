#!/usr/bin/env bash
# Construye el artefacto distribuible del monitor DFT.
#
#   bash scripts/build_web.sh              # build completo
#   bash scripts/build_web.sh --skip-npm   # reutiliza el SPA ya compilado
#
# Produce dist/dft-monitor-web-<version>-<plataforma>.tar.gz (o .zip en Windows)
# junto a su SHA256.
set -euo pipefail

ROOT="$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# El venv del repo si existe; si no, lo que haya en el PATH. En los runners de
# Windows solo existe `python`, no `python3`.
PY="${PYTHON:-$ROOT/.venv/bin/python}"
if [ ! -x "$PY" ]; then
  PY="$(command -v python3 || command -v python || true)"
fi
[ -n "$PY" ] || { echo "ERROR: no se encontró Python" >&2; exit 1; }

VERSION="$("$PY" -c "import sys; sys.path.insert(0,'src'); import monitor_api; print(monitor_api.__version__)")"

case "$(uname -s)" in
  Linux)  PLATAFORMA="linux-$(uname -m)" ;;
  Darwin) PLATAFORMA="macos-$(uname -m)" ;;
  MINGW*|MSYS*|CYGWIN*) PLATAFORMA="windows-x64" ;;
  *)      PLATAFORMA="$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m)" ;;
esac

NOMBRE="dft-monitor-web-${VERSION}-${PLATAFORMA}"
echo "▸ ${NOMBRE}"

# ── 1. Frontend ──────────────────────────────────────────────────────────────
if [ "${1:-}" != "--skip-npm" ]; then
  echo "▸ Compilando el frontend…"
  ( cd frontend && npm ci --no-audit --no-fund >/dev/null 2>&1 || npm install --no-audit --no-fund >/dev/null
    npm run build >/dev/null )
fi
[ -f src/monitor_api/static/index.html ] || { echo "ERROR: falta el SPA compilado" >&2; exit 1; }

# ── 2. Estructuras preconvertidas (quita la dependencia de ASE) ─────────────
echo "▸ Preparando estructuras…"
PYTHONPATH="$ROOT/src" "$PY" scripts/pregenerate_structures.py --out build/structures --clean >/dev/null

# ── 3. PyInstaller ───────────────────────────────────────────────────────────
echo "▸ Congelando…"
rm -rf build/dft-monitor-web dist/dft-monitor-web
"$PY" -m PyInstaller packaging/dft-monitor-web.spec --noconfirm --log-level WARN

[ -x dist/dft-monitor-web/dft-monitor-web ] || [ -f dist/dft-monitor-web/dft-monitor-web.exe ] || {
  echo "ERROR: PyInstaller no produjo el ejecutable" >&2; exit 1; }

# ── 4. Smoke test ────────────────────────────────────────────────────────────
# Se prueba el artefacto antes de empaquetarlo: un fallo de import o un recurso
# que no viajó solo se ve ejecutándolo de verdad.
echo "▸ Probando el binario…"
BIN="$ROOT/dist/dft-monitor-web/dft-monitor-web"
[ -x "$BIN" ] || BIN="$ROOT/dist/dft-monitor-web/dft-monitor-web.exe"

SMOKE="$(mktemp -d)"
trap 'rm -rf "$SMOKE"; [ -n "${SMOKE_PID:-}" ] && kill "$SMOKE_PID" 2>/dev/null || true' EXIT
mkdir -p "$SMOKE/cfg" "$SMOKE/datos/local_runs"

DFT_MONITOR_CONFIG_DIR="$SMOKE/cfg" "$BIN" \
  --data-root "$SMOKE/datos" --port 8899 --no-browser > "$SMOKE/salida.log" 2>&1 &
SMOKE_PID=$!

for _ in $(seq 1 90); do
  curl -sf http://127.0.0.1:8899/api/health >/dev/null 2>&1 && break
  sleep 0.5
done

fallo() { echo "ERROR: $1" >&2; echo "--- salida ---" >&2; cat "$SMOKE/salida.log" >&2; exit 1; }

curl -sf http://127.0.0.1:8899/api/health >/dev/null 2>&1 || fallo "no responde /api/health"

"$PY" - "$VERSION" <<'PYCHECK' || fallo "el smoke test no pasó"
import json, sys, urllib.request

def get(ruta):
    with urllib.request.urlopen(f"http://127.0.0.1:8899{ruta}", timeout=10) as r:
        return json.load(r)

salud = get("/api/health")
assert salud["version"] == sys.argv[1], f"versión {salud['version']} != {sys.argv[1]}"
assert salud["paths"]["frozen"] is True, "el binario no se reconoce como congelado"

with urllib.request.urlopen("http://127.0.0.1:8899/", timeout=10) as r:
    assert b'id="root"' in r.read(), "el SPA no se sirve"

assert get("/api/structures")["items"], "no hay estructuras empaquetadas"

datos = json.dumps({"A": "Cs", "B": "Pb", "X": "I"}).encode()
req = urllib.request.Request(
    "http://127.0.0.1:8899/api/ml/predict", data=datos,
    headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=60) as r:
    eg = json.load(r)["bandgap_pred"]
assert 1.0 < eg < 2.5, f"predicción fuera de rango: {eg}"

print(f"  health ok · SPA ok · estructuras ok · CsPbI3 = {eg:.3f} eV")
PYCHECK

kill "$SMOKE_PID" 2>/dev/null || true
SMOKE_PID=""

# ── 5. Comprimir ─────────────────────────────────────────────────────────────
echo "▸ Comprimiendo…"
cd dist
if [ "$PLATAFORMA" = "windows-x64" ]; then
  ARTEFACTO="${NOMBRE}.zip"
  rm -f "$ARTEFACTO"
  "$PY" -c "import shutil,sys; shutil.make_archive(sys.argv[1], 'zip', '.', 'dft-monitor-web')" "$NOMBRE"
else
  ARTEFACTO="${NOMBRE}.tar.gz"
  rm -f "$ARTEFACTO"
  tar czf "$ARTEFACTO" dft-monitor-web
fi

if command -v sha256sum >/dev/null 2>&1; then
  sha256sum "$ARTEFACTO" > "${ARTEFACTO}.sha256"
else
  "$PY" -c "
import hashlib,sys
h=hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest()
open(sys.argv[1]+'.sha256','w').write(f'{h}  {sys.argv[1]}\n')" "$ARTEFACTO"
fi

cd "$ROOT"
echo
echo "  artefacto:   dist/${ARTEFACTO}"
echo "  comprimido:  $(du -h "dist/${ARTEFACTO}" | cut -f1)"
echo "  extraído:    $(du -sh dist/dft-monitor-web | cut -f1)"
echo "  sha256:      $(cut -d' ' -f1 "dist/${ARTEFACTO}.sha256")"
