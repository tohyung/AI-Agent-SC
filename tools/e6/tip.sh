#!/usr/bin/env bash
# Testnet tip from the newest private-testnet socket (magic 42123).
S=$(ls -t /tmp/testnet-test-*/socket/pool1/sock 2>/dev/null | head -1)
[ -n "$S" ] || exit 1
/home/tohung/stage05-infra/cardano-node-8.9.0/bin/cardano-cli query tip --testnet-magic 42123 --socket-path "$S"
