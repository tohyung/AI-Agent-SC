#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
UPSTREAM_DIR="$ROOT/upstream/marlowe"
UPSTREAM_URL="https://github.com/marlowe-lang/marlowe.git"
UPSTREAM_COMMIT="7b5b1e900ec53a8eb18747992bec73470704dfcb"

if [[ ! -d "$UPSTREAM_DIR/.git" ]]; then
  mkdir -p "$(dirname "$UPSTREAM_DIR")"
  git init "$UPSTREAM_DIR"
  git -C "$UPSTREAM_DIR" remote add origin "$UPSTREAM_URL"
fi

if ! git -C "$UPSTREAM_DIR" cat-file -e "$UPSTREAM_COMMIT^{commit}" 2>/dev/null; then
  git -C "$UPSTREAM_DIR" fetch --depth 1 origin "$UPSTREAM_COMMIT"
fi

git -C "$UPSTREAM_DIR" checkout --detach --force "$UPSTREAM_COMMIT"
test "$(git -C "$UPSTREAM_DIR" rev-parse HEAD)" = "$UPSTREAM_COMMIT"
"$ROOT/verify_upstream.sh"
