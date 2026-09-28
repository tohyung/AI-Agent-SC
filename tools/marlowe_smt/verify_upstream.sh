#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
UPSTREAM_DIR="$ROOT/upstream/marlowe"
UPSTREAM_COMMIT="7b5b1e900ec53a8eb18747992bec73470704dfcb"
FILES=(
  haskell/src/Language/Marlowe/Pretty.hs
  haskell/src/Language/Marlowe/Deserialisation.hs
  haskell/src/Language/Marlowe/Semantics.hs
  haskell/src/Language/Marlowe/Semantics/Deserialisation.hs
  haskell/src/Language/Marlowe/Semantics/Types.hs
  haskell/src/Language/Marlowe/Analysis/FSSemanticsFastVerbose.hs
)

test -d "$UPSTREAM_DIR/.git"
test "$(git -C "$UPSTREAM_DIR" rev-parse HEAD)" = "$UPSTREAM_COMMIT"

for file in "${FILES[@]}"; do
  expected=$(git -C "$UPSTREAM_DIR" show "$UPSTREAM_COMMIT:$file" | sha256sum | cut -d' ' -f1)
  actual=$(sha256sum "$UPSTREAM_DIR/$file" | cut -d' ' -f1)
  if [[ "$expected" != "$actual" ]]; then
    echo "checksum mismatch: $file expected=$expected actual=$actual" >&2
    exit 1
  fi
  echo "$actual  $file"
done

if [[ -n "$(git -C "$UPSTREAM_DIR" status --short --untracked-files=no)" ]]; then
  echo "upstream tracked files are modified" >&2
  git -C "$UPSTREAM_DIR" status --short --untracked-files=no >&2
  exit 1
fi

echo "verified upstream commit $UPSTREAM_COMMIT; no patches"
