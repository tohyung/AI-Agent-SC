#!/usr/bin/env bash
# Private Babbage testnet for ledger size checks (magic 42123); workspace in /tmp.
set -euo pipefail
cd /tmp
export TMPDIR=/tmp
export CARDANO_NODE=/home/tohung/stage05-infra/cardano-node-8.9.0/bin/cardano-node
export CARDANO_CLI=/home/tohung/stage05-infra/cardano-node-8.9.0/bin/cardano-cli
export PATH=/home/tohung/stage05-infra/cardano-node-8.9.0/bin:/usr/local/bin:/usr/bin:/bin
exec cardano-testnet cardano --num-pool-nodes 3 --testnet-magic 42123 --babbage-era \
  --epoch-length 100000 --slot-length 1 --active-slots-coeff 0.1
