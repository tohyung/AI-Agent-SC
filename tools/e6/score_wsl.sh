#!/usr/bin/env bash
# Machine scoring inside WSL (needs only the pinned reference binary, no testnet).
# Usage: bash tools/e6/score_wsl.sh <python module> [args...]
set -euo pipefail
cd /mnt/d/code/marlowe_ai_agent
BUILD=/mnt/d/code/marlowe_ai_agent/tools/marlowe_smt/dist-newstyle/build/x86_64-linux/ghc-9.6.7/marlowe-smt-0.2.0.0/x
export MARLOWE_REFERENCE_BINARY=$BUILD/marlowe-reference/build/marlowe-reference/marlowe-reference
MODULE=$1; shift
exec /home/tohung/stage05-infra/ledger-venv/bin/python -m "$MODULE" "$@"
