#!/usr/bin/env bash
# Download a portable prebuilt Ollama into tools/ollama-turboquant for experiments.
#
# NOTE: full TurboQuant presets (tq3/tq3k) require Ollama built from PR #15505.
# Use install-ollama-turboquant-pr.sh for that. This script just fetches a stock
# prebuilt binary so you can test tq2 / non-TQ portable serving.
#
# Usage (repo root):
#   ./scripts/install-ollama-turboquant.sh [version]
#   ./scripts/ollama-serve-turboquant.sh

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

VERSION="${1:-v0.30.0-rc17}"
INSTALL_DIR="$AQ_REPO_ROOT/tools/ollama-turboquant"
OS="$(aq_os)"
ARCH="$(aq_arch)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "Installing Ollama $VERSION to $INSTALL_DIR ($OS/$ARCH)"

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

OLLAMA_EXE="$(aq_find_ollama ollama-turboquant || true)"
if [ -z "$OLLAMA_EXE" ] || [ ! -f "$OLLAMA_EXE" ]; then
  echo "ERROR: ollama binary not found after extract in $INSTALL_DIR" >&2
  exit 1
fi
chmod +x "$OLLAMA_EXE" 2>/dev/null || true

# Cheap check for TurboQuant preset strings embedded in the binary.
has_tq3="no"; has_tq2="no"
if grep -aq "tq3" "$OLLAMA_EXE" 2>/dev/null; then has_tq3="yes"; fi
if grep -aq "tq2" "$OLLAMA_EXE" 2>/dev/null; then has_tq2="yes"; fi

echo ""
echo "Installed: $OLLAMA_EXE"
"$OLLAMA_EXE" --version || true
echo "Binary includes preset string 'tq2': $has_tq2"
echo "Binary includes preset string 'tq3': $has_tq3"
echo ""
if [ "$has_tq3" != "yes" ]; then
  echo "NOTE: tq3/tq3k need Ollama built from PR #15505 (see scripts/install-ollama-turboquant-pr.sh)."
  echo "You can still try OLLAMA_KV_CACHE_TYPE=tq2 with this build."
fi
echo ""
echo "Next: ./scripts/ollama-serve-turboquant.sh"
