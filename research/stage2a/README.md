# Stage 2A research foundation

This directory contains **draft candidate annotations**, not approved ground truth.
No file here is imported by the production agent. Human approval is required
before the evaluation split can be frozen or used for promotion decisions.

From the repository root:

```bash
python research/stage2a/foundation.py validate
python research/stage2a/foundation.py stats
python research/stage2a/foundation.py review --output research/stage2a/review_queue.md
python -m pytest research/stage2a/test_foundation.py -q
```

`review_queue.md` is generated deterministically and lists an approve/edit/reject
decision for each case. Editing that checklist alone does not change annotation
status or establish ground truth; an adjudication pass must update and version the
corpus after reviewing the underlying claims and behavior.

The reference executor uses the existing pinned Haskell semantics in
`tools/marlowe_smt/upstream/marlowe`, not the Python Node 3 diagnostic mapper.
Inside the WSL/Linux environment with Cabal available:

```bash
cd tools/marlowe_smt
cabal build exe:marlowe-reference
cabal list-bin exe:marlowe-reference
python3 -m unittest tests/test_reference.py -v
```

`tools/marlowe_smt/run_reference.py` accepts one JSON request on stdin and
prints one JSON result. The request must contain `contract`, explicit `state`
(`accounts`, `choices`, `boundValues`, `minTime`), and a `transactions` array.
Each transaction has an `interval` (`from`, `to`) and an `inputs` array. Time
values are POSIX milliseconds; inputs use the existing SMT counterexample
shape. The wrapper accepts `--binary` or `MARLOWE_REFERENCE_BIN` and
`--hard-timeout`; it never launches a shell.

The response has `status`, `meta.upstream_commit`,
`meta.reference_driver_version`, `steps`, and, when execution was parsed,
`final_state` and `final_contract`. A successful step includes structured
warnings, payments, state and full continuation. On transaction error the trace
stops at that step and the final state/contract remain the last committed ones.
Merkleized continuations are explicitly `Unsupported` for this research tool.

See [protocol.md](protocol.md) for annotation semantics, metrics and evidence
limits. The reference tool is **not** Cardano ledger or deployment validation.
