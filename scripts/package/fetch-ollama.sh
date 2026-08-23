#!/usr/bin/env bash
# Fetch portable stock Ollama into a packaging staging directory.
# Usage: ./scripts/package/fetch-ollama.sh <dest_dir> [version] [arch]
#   arch: amd64 (default) | arm64  (Windows ARM64 / Copilot+)
#
# Caches archives under packaging/cache/ollama/<version>/ so rebuilds skip
# the multi-GB GitHub download. Set AQUILA_OLLAMA_FORCE_REFRESH=1 to re-download.

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../_common.sh"

DEST="${1:?dest directory required}"
VERSION="${2:-v0.31.1}"
ARCH="${3:-$(aq_arch)}"
OS="$(aq_os)"
FORCE_REFRESH="${AQUILA_OLLAMA_FORCE_REFRESH:-0}"
MIN_BYTES=$((500 * 1024 * 1024))
STAMP_NAME=".aquila-ollama-stamp"

base="https://github.com/ollama/ollama/releases/download/$VERSION"
case "$OS" in
  windows)
    if [ "$ARCH" = "arm64" ]; then
      asset="ollama-windows-arm64.zip"
    else
      asset="ollama-windows-amd64.zip"
    fi
    ;;
  linux)
    asset="ollama-linux-$ARCH.tgz"
    ;;
  macos)
    asset="ollama-darwin.tgz"
    ;;
  *)
    echo "Unsupported OS: $OS" >&2
    exit 1
    ;;
esac

CACHE_DIR="$AQ_REPO_ROOT/packaging/cache/ollama/$VERSION"
mkdir -p "$CACHE_DIR"
CACHED="$CACHE_DIR/$asset"
EXPECTED_STAMP="${VERSION}|${ARCH}|${asset}"

dest_ready() {
  local suffix exe stamp
  suffix="$(aq_exe)"
  if [ -f "$DEST/ollama$suffix" ]; then
    exe="$DEST/ollama$suffix"
  else
    exe="$(find "$DEST" -name "ollama$suffix" -type f 2>/dev/null | head -1 || true)"
  fi
  [ -n "$exe" ] && [ -f "$exe" ] || return 1
  [ -f "$DEST/$STAMP_NAME" ] || return 1
  [ "$(tr -d '\r\n' < "$DEST/$STAMP_NAME")" = "$EXPECTED_STAMP" ]
}

if [ "$FORCE_REFRESH" != "1" ] && dest_ready; then
  echo "Ollama $VERSION ($OS/$ARCH) already staged at $DEST - skipping download/extract."
  suffix="$(aq_exe)"
  if [ -f "$DEST/ollama$suffix" ]; then
    OLLAMA_EXE="$DEST/ollama$suffix"
  else
    OLLAMA_EXE="$(find "$DEST" -name "ollama$suffix" -type f 2>/dev/null | head -1)"
  fi
  echo "OK: $OLLAMA_EXE"
  "$OLLAMA_EXE" --version || true
  exit 0
fi

if [ "$FORCE_REFRESH" = "1" ] || [ ! -f "$CACHED" ] || [ "$(wc -c < "$CACHED")" -lt "$MIN_BYTES" ]; then
  echo "Fetching stock Ollama $VERSION ($OS/$ARCH)"
  echo "Cache miss - downloading once to $CACHED (reuse on later builds)."
  partial="$CACHED.partial"
  rm -f "$partial"
  aq_download "$base/$asset" "$partial"
  sz="$(wc -c < "$partial")"
  if [ "$sz" -lt "$MIN_BYTES" ]; then
    rm -f "$partial"
    echo "ERROR: downloaded archive too small ($sz bytes)" >&2
    exit 1
  fi
  mv -f "$partial" "$CACHED"
  echo "Cached ($sz bytes): $CACHED"
else
  echo "Using cached Ollama archive: $CACHED"
fi

mkdir -p "$DEST"
rm -rf "$DEST"/*
echo "Extracting $CACHED -> $DEST ..."
case "$asset" in
  *.zip) aq_extract_zip "$CACHED" "$DEST" ;;
  *.tgz|*.tar.gz) tar -xzf "$CACHED" -C "$DEST" ;;
  *) echo "ERROR: unknown archive type: $asset" >&2; exit 1 ;;
esac
printf '%s\n' "$EXPECTED_STAMP" > "$DEST/$STAMP_NAME"

suffix="$(aq_exe)"
if [ -f "$DEST/ollama$suffix" ]; then
  OLLAMA_EXE="$DEST/ollama$suffix"
else
  OLLAMA_EXE="$(find "$DEST" -name "ollama$suffix" -type f 2>/dev/null | head -1)"
fi
if [ -z "$OLLAMA_EXE" ] || [ ! -f "$OLLAMA_EXE" ]; then
  echo "ERROR: ollama binary not found in $DEST" >&2
  exit 1
fi
chmod +x "$OLLAMA_EXE" 2>/dev/null || true
echo "OK: $OLLAMA_EXE"
"$OLLAMA_EXE" --version || true
