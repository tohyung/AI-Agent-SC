# Standalone Marlowe SMT driver

This package runs the Marlowe reference SMT warning analysis without
`cardano-node`. It pins upstream `marlowe-lang/marlowe` commit
`7b5b1e900ec53a8eb18747992bec73470704dfcb`, verifies the exact source files by
SHA-256, and compiles only the modules needed by
`FSSemanticsFastVerbose`. No upstream source is patched.

Requirements: GHC 9.6.7, cabal-install 3.10.3.0, Z3 4.13.3, Git, and Python 3.

```bash
./build.sh
./run_tests.sh
```

The executable reads either a bare Core V1 contract or
`{"contract": ..., "state": ...}` from stdin. State uses the canonical Core V1
association-list representation: `accounts` is `[[[party, token], amount]]`,
`choices` is `[[choiceId, chosenNumber]]`, `boundValues` is
`[[valueId, value]]`, and `minTime` is an integer POSIX millisecond value.

```bash
cabal run exe:marlowe-smt -- --solver-timeout-ms 60000 < contract.json
python3 run_smt.py --hard-timeout 90 --solver-timeout-ms 60000 < contract.json
```

Stdout is exactly one JSON object with `status`, structured `warnings`,
`counterexample`, `analysis_notes`, and `meta`. Invalid input also produces JSON
but exits nonzero. The Python wrapper adds the distinct `Timeout` status when a
hard subprocess deadline is exceeded.

Known limits:

- A `MerkleizedCase` continuation is a hash, not an available contract; its
  continuation is not analyzed and the output records this in `analysis_notes`.
- Addresses, currency symbols, token names, and merkleization hashes are opaque
  UTF-8 strings. Equality is preserved, but on-chain encoding/validity and
  ledger limits are not checked.
- This reference engine has no `SlotLength` parameter. It is a business-warning
  analyzer, not the separate ledger-limit check.
- Use one subprocess per job and enforce a hard timeout. A timeout is never a
  `Valid` result.
- The measured operating defaults are a 60-second solver timeout and a
  90-second hard subprocess deadline. Stage 0.7b found a 42.2-second median for
  the hardest completed n=64 Valid-side configuration; the original 5/30-second
  limits only reflected Counterexample-side startup-dominated measurements.
  See `bench/stress-valid-summary.csv` and the Stage 0.7b report.
- `bench/valid-corpus/` retains canonical representatives with SHA-256 values
  and measured statuses in `MANIFEST.csv`. Recreate it with
  `python3 bench/select_valid_corpus.py`; `run_tests.sh` verifies byte-for-byte
  regeneration and reruns the smallest representatives.
- On the measured 16-logical-core, 7-GiB WSL2 host, cap execution at two jobs
  and 2 GiB per job. `Indeterminate` and `Timeout` mean “not concluded”, not
  “invalid”; simplify or escalate the contract instead of treating either as a
  failed proof.
