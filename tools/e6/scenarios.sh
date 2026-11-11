#!/usr/bin/env bash
# Run expectation scenarios one by one on the generated contract; stop at the first that is not
# delivered. bash tools/e6/scenarios.sh N INTENT_ID CONTRACT_ID scenario.json...
N=$1; CID=$2; KID=$3; shift 3
for f in "$@"; do
  echo "== $f"
  out=$(bash tools/e6/pipe.sh "$N" --review-candidate-id "$CID" --replay-contract-id "$KID" \
        --expectation-file "$f" --answers-file tools/e6/confirm.json)
  echo "$out" | grep -E "^case |^attempt|DIAG|step (semantic_comparison|ledger_validation|exploration|oracle)"
  echo "$out" | grep -q "SIMULATED_LEDGER_SIZE_CHECKED" || { echo "STOPPED at $f"; exit 1; }
done
echo "ALL SCENARIOS DELIVERED"
