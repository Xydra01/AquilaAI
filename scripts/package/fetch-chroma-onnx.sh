#!/usr/bin/env bash
# Fetch Chroma all-MiniLM-L6-v2 ONNX assets for Aquila packaging (macOS/Linux).
# Usage: ./scripts/package/fetch-chroma-onnx.sh [DestDir]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEST="${1:-$ROOT/dist/Aquila/runtime/embeddings}"
MODEL="all-MiniLM-L6-v2"
URL="https://chroma-onnx-models.s3.amazonaws.com/all-MiniLM-L6-v2/onnx.tar.gz"
EXPECTED_SHA="913d7300ceae3b2dbc2c50d1de4baacab4be7b9380491c27fab7418616a16ec3"
CACHE="$ROOT/packaging/cache/chroma-onnx/$MODEL"
TAR="$CACHE/onnx.tar.gz"
STAMP_NAME=".aquila-chroma-onnx-stamp"
EXPECTED_STAMP="$MODEL|$EXPECTED_SHA"

mkdir -p "$CACHE" "$DEST"

if [[ -f "$DEST/$MODEL/onnx/model.onnx" && -f "$DEST/$STAMP_NAME" ]]; then
  got="$(tr -d '\r\n' < "$DEST/$STAMP_NAME")"
  if [[ "$got" == "$EXPECTED_STAMP" ]]; then
    echo "Embedding assets already staged at $DEST - skip."
    exit 0
  fi
fi

sha_of() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

if [[ -f "$TAR" ]]; then
  sha="$(sha_of "$TAR")"
  if [[ "$sha" != "$EXPECTED_SHA" ]]; then
    echo "Cached tar SHA mismatch - re-downloading."
    rm -f "$TAR"
  fi
fi

if [[ ! -f "$TAR" ]]; then
  USER_TAR="$HOME/.cache/chroma/onnx_models/$MODEL/onnx.tar.gz"
  if [[ -f "$USER_TAR" ]] && [[ "$(sha_of "$USER_TAR")" == "$EXPECTED_SHA" ]]; then
    echo "Seeding cache from local Chroma download: $USER_TAR"
    cp "$USER_TAR" "$TAR"
  else
    echo "Downloading $URL ..."
    curl -L --fail --retry 3 --retry-delay 2 -o "$TAR" "$URL"
    sha="$(sha_of "$TAR")"
    if [[ "$sha" != "$EXPECTED_SHA" ]]; then
      rm -f "$TAR"
      echo "SHA256 mismatch: got $sha expected $EXPECTED_SHA" >&2
      exit 1
    fi
  fi
fi

rm -rf "$DEST/$MODEL"
mkdir -p "$DEST/$MODEL"
USER_ONNX="$HOME/.cache/chroma/onnx_models/$MODEL/onnx"
if [[ -f "$USER_ONNX/model.onnx" ]]; then
  echo "Copying extracted ONNX assets from local Chroma cache..."
  cp -R "$USER_ONNX" "$DEST/$MODEL/onnx"
else
  echo "Extracting onnx.tar.gz..."
  tar -xzf "$TAR" -C "$DEST/$MODEL"
fi

if [[ ! -f "$DEST/$MODEL/onnx/model.onnx" ]]; then
  echo "Missing model.onnx after staging" >&2
  exit 1
fi
printf '%s\n' "$EXPECTED_STAMP" > "$DEST/$STAMP_NAME"
echo "Bundled embedding ready: $DEST/$MODEL/onnx/model.onnx"
