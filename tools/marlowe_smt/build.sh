#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "$ROOT"

echo "ghc: $(ghc --numeric-version)"
echo "cabal: $(cabal --numeric-version)"
echo "z3: $(z3 --version)"
"$ROOT/fetch_upstream.sh"
echo "upstream: $(git -C upstream/marlowe rev-parse HEAD)"
cabal build exe:marlowe-smt
BIN=$(cabal list-bin exe:marlowe-smt)
echo "binary: $BIN"
