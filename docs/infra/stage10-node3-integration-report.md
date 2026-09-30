# Stage 1.0: Live Node 3 integration

Baseline: `5281f063e621a24887de9c198522451c06cfda1c`.

## Production architecture

Structural validator -> Node 2 semantic verification -> deterministic Node 3 lint ->
Marlowe SMT -> Node3Result decision policy.

The live pipeline no longer calls `LogicGraphVerifier.verify()` for Node 3. Its
full semantic/path core remains available for regression and the old side of
offline replay. `LogicGraphVerifier.lint()` retains static structural and draft
consistency checks, graph construction, and nonblocking warnings. Symbolic
business warnings now come from Marlowe SMT. The critical
`11-infeasible-if-partial-pay` corpus item is rejected by the old full verifier,
accepted by lint, and reported `Valid`/pass by real SMT/Node 3.

## Decision and retry

Blocking lint errors skip SMT and enter the existing Node 1 repair flow.
Counterexamples also enter repair using rendered Vietnamese findings; a
regenerated draft still runs through structural validation and Node 2 before
Node 3. Timeout and Indeterminate get one same-contract SMT retry, with no LLM
call, new iteration, or stall count between attempts. A second inconclusive
attempt blocks with `logic_inconclusive`. Unavailable, InvalidInput, and Valid
with analysis notes block immediately. In particular, incomplete Merkleized
analysis does not become `done`.

Stall fingerprints for counterexamples use canonical contract and sorted
structured warnings, excluding solver timing, raw stdout, and stderr. Lint
failure fingerprints use canonical contract and sorted blocking lint errors.
Trace key `node_3_logic_graph_verification`, result field
`logic_verification`, and `findings`/`errors`/`warnings` remain compatible;
SMT-specific fields are additive. The sample result is regenerated from a
deterministic test backend because its exact JSON snapshot includes Node 3.

## Infrastructure and limits

The production adapter calls the repository wrapper with the current Python
interpreter and an absolute path. It has a process-wide two-job semaphore and
60,000 ms solver / 90 s hard timeout defaults. It never invokes WSL from
Windows. Windows Python without a native solver returns Unavailable; run the
agent inside WSL/Linux with the built driver or set `MARLOWE_SMT_BIN` to a
compatible binary in that same environment. The WSL acceptance used this
override because the non-login WSL process did not have `cabal` on PATH.
Fake benchmark mode injects its own deterministic backend and never launches
the solver.

This verifier does not replace ledger/on-chain validation. Merkleized
continuations are not completely analyzed and remain inconclusive when the
driver reports that limitation.

## Acceptance

Real driver: valid escrow pass/Valid; unfunded Pay fail/Counterexample with a
rendered partial-pay error; minimal live pipeline with FakeReasoner and real
SMT done/ok. Replay: 7 evaluable audit rows both_correct, 3 missing contracts
ground_truth_unavailable; semantic CSV fields unchanged from baseline when
excluding volatile `smt_seconds`. Driver regression: 12 tests passed and
upstream verification passed. Python suite and lint results are recorded in
`stage10-command-log.md`.
