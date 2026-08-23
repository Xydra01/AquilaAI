#!/usr/bin/env bash
# Build Aquila macOS .app (onedir) and optional DMG.
# Prints per-step timing and a rough ETA (learns from packaging/.build-timings-macos.json).
# Compatible with macOS system bash 3.2 (no associative arrays).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
VERSION="${1:-3.5.0}"
OLLAMA_VER="${2:-v0.31.1}"
TIMINGS="$ROOT/packaging/.build-timings-macos.json"
BUILD_START=$(date +%s)

EST_pip=120
EST_pyinstaller=300
EST_ollama=120
EST_embeddings=30
EST_dmg=90
ACT_pip=
ACT_pyinstaller=
ACT_ollama=
ACT_embeddings=
ACT_dmg=

fmt_dur() {
  local s=$1
  if [ "$s" -lt 0 ]; then s=0; fi
  if [ "$s" -lt 60 ]; then
    printf "%ss" "$s"
  elif [ "$s" -lt 3600 ]; then
    printf "%dm %02ds" $((s / 60)) $((s % 60))
  else
    printf "%dh %dm %02ds" $((s / 3600)) $(((s % 3600) / 60)) $((s % 60))
  fi
}

est_get() {
  case "$1" in
    pip) echo "$EST_pip" ;;
    pyinstaller) echo "$EST_pyinstaller" ;;
    ollama) echo "$EST_ollama" ;;
    embeddings) echo "$EST_embeddings" ;;
    dmg) echo "$EST_dmg" ;;
    *) echo 60 ;;
  esac
}

est_set() {
  case "$1" in
    pip) EST_pip=$2 ;;
    pyinstaller) EST_pyinstaller=$2 ;;
    ollama) EST_ollama=$2 ;;
    embeddings) EST_embeddings=$2 ;;
    dmg) EST_dmg=$2 ;;
  esac
}

act_set() {
  case "$1" in
    pip) ACT_pip=$2 ;;
    pyinstaller) ACT_pyinstaller=$2 ;;
    ollama) ACT_ollama=$2 ;;
    embeddings) ACT_embeddings=$2 ;;
    dmg) ACT_dmg=$2 ;;
  esac
}

load_estimates() {
  if [ -f "$TIMINGS" ] && command -v python3 >/dev/null 2>&1; then
    eval "$(python3 - "$TIMINGS" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
try:
    data = json.loads(p.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(0)
for k in ("pip", "pyinstaller", "ollama", "embeddings", "dmg"):
    if k in data:
        try:
            print(f'est_set {k} {float(data[k]):.0f}')
        except Exception:
            pass
PY
)"
  fi
}

save_timings() {
  command -v python3 >/dev/null 2>&1 || return 0
  AQUILA_BUILD_ACTUALS="pip=${ACT_pip:-},pyinstaller=${ACT_pyinstaller:-},ollama=${ACT_ollama:-},embeddings=${ACT_embeddings:-},dmg=${ACT_dmg:-}" \
  python3 - "$TIMINGS" <<'PY'
import json, os, sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
prev = {}
if path.is_file():
    try:
        prev = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        prev = {}
actuals = {}
for part in os.environ.get("AQUILA_BUILD_ACTUALS", "").split(","):
    if "=" not in part:
        continue
    k, v = part.split("=", 1)
    v = v.strip()
    if not v:
        continue
    try:
        actuals[k] = float(v)
    except ValueError:
        pass
defaults = {"pip": 120, "pyinstaller": 300, "ollama": 120, "embeddings": 30, "dmg": 90}
out = {"updated": datetime.now(timezone.utc).isoformat()}
for k, default in defaults.items():
    prev_v = float(prev.get(k, default))
    if k in actuals:
        out[k] = round(0.4 * prev_v + 0.6 * actuals[k], 1)
    else:
        out[k] = round(prev_v, 1)
path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
print(path)
PY
}

sum_eta() {
  local total=0
  local sid
  for sid in "$@"; do
    total=$((total + $(est_get "$sid")))
  done
  echo "$total"
}

step_start() {
  local id="$1"
  local label="$2"
  shift 2
  STEP_ID="$id"
  STEP_START=$(date +%s)
  local elapsed=$((STEP_START - BUILD_START))
  local step_eta
  step_eta=$(est_get "$id")
  local remain
  remain=$(sum_eta "$@")
  echo ""
  echo ">>> [$id] $label"
  echo "    Elapsed $(fmt_dur "$elapsed") | Step ETA ~$(fmt_dur "$step_eta") | Build ETA remaining ~$(fmt_dur "$remain")"
}

step_done() {
  local id="$1"
  local now end
  now=$(date +%s)
  end=$((now - STEP_START))
  act_set "$id" "$end"
  echo "<<< [$id] done in $(fmt_dur "$end")"
}

drop_remain() {
  local id="$1"
  local next=""
  local x
  for x in $REMAIN; do
    if [ "$x" != "$id" ]; then
      next="$next $x"
    fi
  done
  REMAIN=$(echo "$next" | xargs)
}

load_estimates

if [ -x "$ROOT/ai-agent-env/bin/python" ]; then
  PY="$ROOT/ai-agent-env/bin/python"
else
  PY=python3
fi

REMAIN="pip pyinstaller ollama embeddings"
if command -v hdiutil >/dev/null 2>&1; then
  REMAIN="$REMAIN dmg"
fi

total=$(sum_eta $REMAIN)
echo ""
echo "=== Aquila macOS build ==="
echo "Plan (~$(fmt_dur "$total") total ETA from prior runs / defaults):"
i=1
for sid in $REMAIN; do
  case "$sid" in
    pip) label="pip install (core + packaging)" ;;
    pyinstaller) label="PyInstaller (Aquila onedir)" ;;
    ollama) label="Fetch / bundle Ollama" ;;
    embeddings) label="Fetch / bundle MiniLM ONNX embeddings" ;;
    dmg) label="Create DMG" ;;
    *) label="$sid" ;;
  esac
  echo "  $i. $label  (~$(fmt_dur "$(est_get "$sid")"))"
  i=$((i + 1))
done
echo ""

step_start pip "pip install (core + packaging)" $REMAIN
"$PY" -m pip install -r requirements-core.txt -r requirements-packaging.txt
step_done pip
drop_remain pip

step_start pyinstaller "PyInstaller (Aquila onedir)" $REMAIN
"$PY" -m PyInstaller packaging/aquila.spec
step_done pyinstaller
drop_remain pyinstaller

DIST="$ROOT/dist/Aquila"
OLLAMA_DEST="$DIST/runtime/ollama"
mkdir -p "$OLLAMA_DEST"

step_start ollama "Fetch / bundle Ollama" $REMAIN
bash "$ROOT/scripts/package/fetch-ollama.sh" "$OLLAMA_DEST" "$OLLAMA_VER"
if ! find "$OLLAMA_DEST" -name 'ollama' -type f | head -1 | grep -q .; then
  echo "ERROR: ollama binary not found under $OLLAMA_DEST after fetch" >&2
  exit 1
fi
echo "Ollama bundled under $OLLAMA_DEST"
step_done ollama
drop_remain ollama

EMB_DEST="$DIST/runtime/embeddings"
step_start embeddings "Fetch / bundle MiniLM ONNX embeddings" $REMAIN
bash "$ROOT/scripts/package/fetch-chroma-onnx.sh" "$EMB_DEST"
if [ ! -f "$EMB_DEST/all-MiniLM-L6-v2/onnx/model.onnx" ]; then
  echo "ERROR: embedding model not found under $EMB_DEST after fetch" >&2
  exit 1
fi
echo "Embeddings bundled under $EMB_DEST"
step_done embeddings
drop_remain embeddings

APP_NAME="Aquila"
if [ -d "$DIST/Aquila.app" ]; then
  echo "App bundle: $DIST/Aquila.app"
else
  echo "Onedir build: $DIST (codesign/notarize for distribution)"
fi

if command -v hdiutil >/dev/null 2>&1; then
  step_start dmg "Create DMG" $REMAIN
  DMG="$ROOT/dist/Aquila-$VERSION-mac.dmg"
  rm -f "$DMG"
  hdiutil create -volname "$APP_NAME" -srcfolder "$DIST" -ov -format UDZO "$DMG"
  echo "DMG: $DMG"
  step_done dmg
  drop_remain dmg
fi

save_timings >/dev/null || true

TOTAL=$(( $(date +%s) - BUILD_START ))
echo ""
echo "=== Build finished in $(fmt_dur "$TOTAL") ==="
echo "Timing history updated: $TIMINGS"
