#!/usr/bin/env bash
# Install portable stock Ollama to tools/ollama-stock (does NOT touch ollama-turboquant).
#
# Usage (repo root):
#   ./scripts/install-ollama-stock.sh [version]
#   ./scripts/ollama-serve-stock.sh

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

VERSION="${1:-v0.30.0-rc23}"
INSTALL_DIR="$AQ_REPO_ROOT/tools/ollama-stock"
OS="$(aq_os)"
ARCH="$(aq_arch)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "Installing stock Ollama $VERSION to $INSTALL_DIR ($OS/$ARCH)"

rm -rf "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR"

base="https://github.com/ollama/ollama/releases/download/$VERSION"
case "$OS" in
  windows)
    asset="ollama-windows-amd64.zip"
    aq_download "$base/$asset" "$TMP/$asset"
    aq_extract_zip "$TMP/$asset" "$INSTALL_DIR"
    ;;
  linux)
    asset="ollama-linux-$ARCH.tgz"
    aq_download "$base/$asset" "$TMP/$asset"
    tar -xzf "$TMP/$asset" -C "$INSTALL_DIR"
    ;;
  macos)
    asset="ollama-darwin.tgz"
    aq_download "$base/$asset" "$TMP/$asset"
    tar -xzf "$TMP/$asset" -C "$INSTALL_DIR"
    ;;
  *)
    echo "Unsupported OS: $OS" >&2; exit 1 ;;
esac

OLLAMA_EXE="$(aq_find_ollama ollama-stock || true)"
if [ -z "$OLLAMA_EXE" ] || [ ! -f "$OLLAMA_EXE" ]; then
  echo "ERROR: ollama binary not found after extract in $INSTALL_DIR" >&2
  exit 1
fi
chmod +x "$OLLAMA_EXE" 2>/dev/null || true

echo ""
echo "Installed: $OLLAMA_EXE"
"$OLLAMA_EXE" --version || true
echo ""
echo "Next:"
echo "  1. Quit any system-tray Ollama on 11434 if running"
echo "  2. ./scripts/ollama-serve-stock.sh"
echo "  3. ./scripts/ollama-create-qwopus.sh"
echo "  4. (optional) ./scripts/ollama-create-heretic.sh"
echo "  5. .env: OLLAMA_BASE_URL=http://127.0.0.1:11434  OLLAMA_MODEL=aquila_qwopus"
