#!/usr/bin/env bash
# Add portable TurboQuant Ollama (tools/ollama-turboquant) to PATH persistently.
# Usage: ./scripts/setup-ollama-turboquant-path.sh

set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

BIN_DIR="$AQ_REPO_ROOT/tools/ollama-turboquant"
if [ ! -f "$BIN_DIR/ollama$(aq_exe)" ]; then
  echo "Missing $BIN_DIR/ollama$(aq_exe) - run install-ollama-turboquant(-pr).sh first." >&2
  exit 1
fi

OS="$(aq_os)"
if [ "$OS" = "windows" ] && command -v setx >/dev/null 2>&1; then
  # Persist to the Windows user PATH (Git Bash). Convert to a native path for setx.
  native="$BIN_DIR"
  if command -v cygpath >/dev/null 2>&1; then native="$(cygpath -w "$BIN_DIR")"; fi
  current="$(powershell -NoProfile -Command '[Environment]::GetEnvironmentVariable("Path","User")' 2>/dev/null || echo "")"
  case ";$current;" in
    *";$native;"*) echo "Already on user PATH: $native" ;;
    *)
      setx PATH "$native;$current" >/dev/null
      echo "Added to user PATH: $native"
      ;;
  esac
  echo "Open a new terminal so PATH refreshes."
else
  # POSIX: append an export to the shell profile if not already present.
  profile="${HOME}/.bashrc"
  [ -n "${ZSH_VERSION:-}" ] && profile="${HOME}/.zshrc"
  line="export PATH=\"$BIN_DIR:\$PATH\""
  if [ -f "$profile" ] && grep -qF "$BIN_DIR" "$profile"; then
    echo "Already referenced in $profile"
  else
    echo "$line" >> "$profile"
    echo "Added to $profile: $line"
  fi
  echo "Run: source \"$profile\"   (or open a new terminal)"
fi

echo ""
echo "Verify: ollama --version"
echo "Serve:  ./scripts/ollama-serve-turboquant-port.sh"
echo "Aquila: OLLAMA_BASE_URL=http://127.0.0.1:11435  OLLAMA_MODEL=aquila-tq-32k|64k|96k"
