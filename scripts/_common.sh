#!/usr/bin/env bash
# Shared helpers for Aquila Ollama / tooling scripts.
# Cross-platform: Git Bash (Windows), macOS, Linux.
#
# Source from another script:
#   source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

# Resolve scripts/ and repo root from THIS file's location (works when sourced).
AQ_SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AQ_REPO_ROOT="$(cd "$AQ_SCRIPTS_DIR/.." && pwd)"
export AQ_SCRIPTS_DIR AQ_REPO_ROOT

aq_os() {
  case "$(uname -s)" in
    Linux*)               echo "linux" ;;
    Darwin*)              echo "macos" ;;
    MINGW*|MSYS*|CYGWIN*) echo "windows" ;;
    *)                    echo "unknown" ;;
  esac
}

aq_arch() {
  case "$(uname -m)" in
    x86_64|amd64)  echo "amd64" ;;
    arm64|aarch64) echo "arm64" ;;
    *)             echo "amd64" ;;
  esac
}

# Executable suffix (".exe" on Windows, empty elsewhere).
aq_exe() {
  if [ "$(aq_os)" = "windows" ]; then echo ".exe"; else echo ""; fi
}

# Find an ollama binary. Order: $OLLAMA_BIN, preferred tools/<dir>, then PATH.
# Usage: aq_find_ollama [preferred_subdir]   -> prints path, returns 0/1
aq_find_ollama() {
  local preferred="${1:-}"
  local suffix
  suffix="$(aq_exe)"
  if [ -n "${OLLAMA_BIN:-}" ] && { [ -x "$OLLAMA_BIN" ] || [ -f "$OLLAMA_BIN" ]; }; then
    echo "$OLLAMA_BIN"
    return 0
  fi
  if [ -n "$preferred" ]; then
    local c="$AQ_REPO_ROOT/tools/$preferred/ollama$suffix"
    if [ -f "$c" ]; then
      echo "$c"
      return 0
    fi
  fi
  if command -v ollama >/dev/null 2>&1; then
    command -v ollama
    return 0
  fi
  return 1
}

# Like aq_find_ollama but errors out (non-zero) with a helpful message.
aq_require_ollama() {
  local bin
  if ! bin="$(aq_find_ollama "${1:-}")"; then
    echo "ERROR: ollama binary not found." >&2
    echo "  Set OLLAMA_BIN, install into tools/, or put 'ollama' on PATH." >&2
    return 1
  fi
  echo "$bin"
}

# Probe an Ollama server. Usage: aq_probe <base_url>  -> 0 if reachable.
aq_probe() {
  local base="${1%/}"
  curl -fsS --max-time 3 "$base/api/tags" >/dev/null 2>&1
}

# Download a URL to a file (curl or wget). Usage: aq_download <url> <out>
aq_download() {
  local url="$1" out="$2"
  if command -v curl >/dev/null 2>&1; then
    curl -fL --retry 3 -o "$out" "$url"
  elif command -v wget >/dev/null 2>&1; then
    wget -O "$out" "$url"
  else
    echo "ERROR: need curl or wget to download $url" >&2
    return 1
  fi
}

# Extract a .zip into a directory (unzip, else python zipfile fallback for Git Bash).
aq_extract_zip() {
  local zip="$1" dest="$2"
  mkdir -p "$dest"
  if command -v unzip >/dev/null 2>&1; then
    unzip -o "$zip" -d "$dest"
  else
    "$(aq_python)" -c "import sys,zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" "$zip" "$dest"
  fi
}

# Resolve a Python interpreter (project venv first, then python3/python).
aq_python() {
  if [ -x "$AQ_REPO_ROOT/ai-agent-env/Scripts/python.exe" ]; then
    echo "$AQ_REPO_ROOT/ai-agent-env/Scripts/python.exe"
  elif [ -x "$AQ_REPO_ROOT/ai-agent-env/bin/python" ]; then
    echo "$AQ_REPO_ROOT/ai-agent-env/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    command -v python3
  else
    echo "python"
  fi
}

# Normalize a base URL: ensure http(s):// prefix, strip trailing slash.
aq_normalize_url() {
  local url="${1%/}"
  case "$url" in
    http://*|https://*) echo "$url" ;;
    *) echo "http://$url" ;;
  esac
}
