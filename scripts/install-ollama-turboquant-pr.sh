#!/usr/bin/env bash
# Build Ollama from PR #15505 (full TurboQuant: tq3, tq3k, ...) into tools/ollama-turboquant.
#
# Cross-platform notes:
#   * Linux/macOS: standard ollama build (cmake generate/build + go build). Needs
#     go, cmake, and a C/C++ toolchain; CUDA is auto-used if the CUDA toolkit is
#     present on PATH.
#   * Windows: the GPU build requires the MSVC Developer Shell + NVIDIA nvcc,
#     which is PowerShell-specific. This script delegates to
#     install-ollama-turboquant-pr.ps1 (kept intact) via powershell.
#
# Usage:
#   ./scripts/install-ollama-turboquant-pr.sh

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

OS="$(aq_os)"
INSTALL_DIR="$AQ_REPO_ROOT/tools/ollama-turboquant"
SRC_DIR="$AQ_REPO_ROOT/tools/ollama-pr15505-src"
PR_URL="https://github.com/ollama/ollama/archive/refs/pull/15505/head.zip"

if [ "$OS" = "windows" ]; then
  echo "Windows detected: delegating to PowerShell build (MSVC + nvcc required)."
  ps1="$AQ_SCRIPTS_DIR/install-ollama-turboquant-pr.ps1"
  if [ ! -f "$ps1" ]; then
    echo "ERROR: $ps1 not found." >&2
    exit 1
  fi
  if command -v powershell >/dev/null 2>&1; then
    exec powershell -NoProfile -ExecutionPolicy Bypass -File "$ps1" "$@"
  elif command -v pwsh >/dev/null 2>&1; then
    exec pwsh -NoProfile -ExecutionPolicy Bypass -File "$ps1" "$@"
  fi
  echo "ERROR: PowerShell not found to run the Windows GPU build." >&2
  exit 1
fi

for cmd in go cmake; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing build dependency: $cmd" >&2
    exit 1
  fi
done

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

if [ ! -d "$SRC_DIR" ]; then
  echo "Downloading PR #15505 source..."
  aq_download "$PR_URL" "$TMP/pr15505.zip"
  aq_extract_zip "$TMP/pr15505.zip" "$TMP/src"
  extracted="$(find "$TMP/src" -maxdepth 1 -type d -name 'ollama-*15505*' | head -n1)"
  if [ -z "$extracted" ]; then
    echo "ERROR: could not locate extracted PR source" >&2
    exit 1
  fi
  mkdir -p "$(dirname "$SRC_DIR")"
  mv "$extracted" "$SRC_DIR"
fi

echo "Building ollama from $SRC_DIR ..."
(
  cd "$SRC_DIR"
  export VERSION="pr15505-turboquant"
  export CGO_ENABLED=1
  # Generate native libs (CPU + CUDA if toolkit present), then build the Go binary.
  if [ -f CMakeLists.txt ]; then
    cmake -B build >/dev/null
    cmake --build build --parallel "$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)"
  fi
  go build -trimpath -o "ollama$(aq_exe)" .
)

rm -rf "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
cp "$SRC_DIR/ollama$(aq_exe)" "$INSTALL_DIR/"
if [ -d "$SRC_DIR/build/lib" ]; then
  cp -R "$SRC_DIR/build/lib" "$INSTALL_DIR/lib"
fi
chmod +x "$INSTALL_DIR/ollama$(aq_exe)" 2>/dev/null || true

echo ""
echo "Deployed to $INSTALL_DIR"
"$INSTALL_DIR/ollama$(aq_exe)" --version || true
echo ""
echo "Next: ./scripts/ollama-serve-turboquant-port.sh"
