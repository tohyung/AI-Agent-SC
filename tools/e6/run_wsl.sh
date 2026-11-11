#!/usr/bin/env bash
# E6 runner inside WSL. The private testnet (magic 42123) lives in /tmp; the newest socket is used.
# Usage: bash tools/e6/run_wsl.sh <python module> [args...]
set -euo pipefail
cd /mnt/d/code/marlowe_ai_agent
BUILD=/mnt/d/code/marlowe_ai_agent/tools/marlowe_smt/dist-newstyle/build/x86_64-linux/ghc-9.6.7/marlowe-smt-0.2.0.0/x
export MARLOWE_REFERENCE_BINARY=$BUILD/marlowe-reference/build/marlowe-reference/marlowe-reference
export MARLOWE_SMT_BIN=$BUILD/marlowe-smt/build/marlowe-smt/marlowe-smt
SOCKET=$(ls -t /tmp/testnet-test-*/socket/pool1/sock 2>/dev/null | head -1 || true)
if [[ -z "$SOCKET" ]]; then echo "no private testnet socket under /tmp" >&2; exit 4; fi
export MARLOWE_LEDGER_BINARY=/home/tohung/stage05-infra/bin/marlowe-cli
export MARLOWE_LEDGER_NODE_CLI=/home/tohung/stage05-infra/cardano-node-8.9.0/bin/cardano-cli
export MARLOWE_LEDGER_SOCKET=$SOCKET
export MARLOWE_LEDGER_TEMPLATE=/home/tohung/stage05-infra/roleplay42123/initialized-control-valid.json
export MARLOWE_LEDGER_BINARY_SHA256=464f14957aafeefc86aa868074e200f700aefc070f1ecb32466d999110e58939
export MARLOWE_LEDGER_SOURCE_COMMIT=2c0ad60ad2caabb7865b6dda56f7ec478f8637e7
export MARLOWE_LEDGER_TEMPLATE_SHA256=787355228c090bb5f179d7bb96f5f20327f0ac1cdc92ed5ea61663664349b82c
export MARLOWE_LEDGER_TESTNET_MAGIC=42123
# Key rotation: E6_GEMINI_SLOT=2 uses GEMINI_API_KEY_2 from .env (the driver switches on quota).
if [[ "${E6_GEMINI_SLOT:-1}" == "2" ]]; then
  GEMINI_API_KEY="$(grep -m1 '^GEMINI_API_KEY_2=' .env | cut -d= -f2- | tr -d '\r')"
  export GEMINI_API_KEY
fi
MODULE=$1; shift
exec /home/tohung/stage05-infra/ledger-venv/bin/python -m "$MODULE" "$@"
