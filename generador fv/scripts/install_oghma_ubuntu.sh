#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR_DIR="$REPO_ROOT/vendor/oghma"
DEB_PATH="${1:-$VENDOR_DIR/oghma-8.1.deb}"
DOWNLOAD_URL="https://www.oghma-nano.com/downloads/ubuntu/oghma-8.1.deb"

mkdir -p "$VENDOR_DIR"

if [[ ! -f "$DEB_PATH" ]]; then
  echo "OghmaNano .deb not found at $DEB_PATH; downloading official Ubuntu package."
  if command -v wget >/dev/null 2>&1; then
    wget -O "$DEB_PATH" "$DOWNLOAD_URL"
  elif command -v curl >/dev/null 2>&1; then
    curl -L -o "$DEB_PATH" "$DOWNLOAD_URL"
  else
    echo "Need wget or curl to download OghmaNano." >&2
    exit 127
  fi
fi

echo "Installing OghmaNano from $DEB_PATH"
sudo apt-get update
sudo apt-get install -y "$DEB_PATH"

echo
echo "Detected OghmaNano runner:"
command -v oghma_core || command -v oghma || true
