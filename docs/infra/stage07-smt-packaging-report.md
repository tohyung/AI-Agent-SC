# Stage 0.7 — packaged standalone Marlowe SMT analysis

Date: 2026-09-29.

## Decision

**đủ với hạn chế nhánh merkleized không được mở rộng, dữ liệu địa chỉ/hash không
được xác thực on-chain, không kiểm giới hạn ledger, và chưa chứng minh tương
đương cho mọi `SlotLength`.**

The packaged analyzer is reliable enough for Node 3 as a business-warning
gate, provided Node 3 treats `Indeterminate`, `InvalidInput`, and `Timeout` as
non-success outcomes. It is not a ledger validator or a proof that a contract
can be submitted on-chain.

## Reproducible package and provenance

The package is under `tools/marlowe_smt/`. `build.sh` fetches only pinned
upstream commit `7b5b1e900ec53a8eb18747992bec73470704dfcb`, then verifies the Git
object and SHA-256 of every upstream source file compiled. The clone is ignored
and no upstream source is patched. Only six upstream modules and four local
modules are compiled, avoiding the known full-upstream `MkSymb.hs` failure.

A fresh clone at packaging commit `31b301f` built successfully from one command.
`run_tests.sh` then passed all 9 test methods. Exact commands and outputs are in
[the command log](stage07-command-log.md).

Toolchain:

- GHC 9.6.7
- cabal-install 3.10.3.0
- Z3 4.13.3, 64 bit
- driver 0.2.0
- upstream `marlowe-lang/marlowe` commit
  `7b5b1e900ec53a8eb18747992bec73470704dfcb`

## Acceptance evidence

### (a) Clean build and complete test command

Pass. A newly cloned repository at commit `31b301f` fetched the pinned upstream
tree, verified all six checksums, compiled all 10 modules plus `Main`, and
linked the executable. The final repository test run exited 0:

```text
Ran 9 tests in 6.899s

OK
```

### (b) Golden behavior

Pass. The agent's existing `escrow_golden.json` was read directly and returned
`Valid`. Five single-fault fixtures returned exactly one expected constructor:

- `partial_pay.json` → `TransactionPartialPay`
- `nonpositive_pay.json` → `TransactionNonPositivePay`
- `nonpositive_deposit.json` → `TransactionNonPositiveDeposit`
- `shadowing.json` → `TransactionShadowing`
- `assertion_failed.json` → `TransactionAssertionFailed`

Warnings are encoded by pattern matching directly on `TransactionWarning`, not
by parsing `show` output.

### (c) Initial state and merkleized continuations

Pass. The same payment contract returned `TransactionPartialPay` with empty
state and `Valid` with a funded state. State accepts canonical Core V1
association-list maps and rejects duplicate keys.

The merkleized fixture returned `Valid` plus an analysis note containing
`1 MerkleizedCase` and `not analyzed`. A merkleized continuation is only a
hash; neither this reference engine nor the tested on-chain-era analyzer can
inspect the absent continuation.

### (d) Constructor coverage and invalid input

Pass. Fixtures cover every requested `Contract`, `Case`, `Action`, `Value`, and
`Observation` constructor, both `Party` forms, both `Payee` forms, `ChoiceId`,
`Bound`, ADA, and a native token. The valid coverage fixture is `Valid`; the
warning coverage fixture returns `TransactionAssertionFailed`.

Malformed JSON, missing fields, extra fields, wrong types, and unknown
constructors all produce exactly one stdout JSON object with
`status: "InvalidInput"` and a nonzero exit. Diagnostics also go to stderr.

Addresses, currency symbols, token names, and merkleized hashes are mapped from
JSON strings to their UTF-8 byte sequences. UTF-8 is injective for Unicode
strings, so equality and map-key identity used by the business semantics are
preserved, including distinct hexadecimal strings. The bridge deliberately
does not decode hex, Bech32, network identifiers, byte-length constraints, or
ledger rules. Consequently malformed on-chain identifiers can still receive a
business-warning result and must be validated separately before submission.

### (e) Stress curve and process states

Pass. The committed summary contains 48 configurations and 144 measured runs:

- `n ∈ {1,2,3,5,8,12,16,20}` sequential `When`s;
- `k ∈ {1,2,4}` cases per `When`;
- nested `If` disabled and enabled;
- three runs per configuration under `/usr/bin/time -v timeout 300`.

All runs completed as `Counterexample`; none hit the 300-second measurement
ceiling. Wall time ranged from 0.20 to 0.41 seconds. Reported maximum RSS ranged
from 32,584 to 34,208 KiB. The heaviest generated case (`n=20`, `k=4`, nested
`If`, 80 branches) took 0.30/0.41/0.30 seconds and 34,168/34,176/34,096 KiB.
The complete table is
[`tools/marlowe_smt/bench/stress-summary.csv`](../../tools/marlowe_smt/bench/stress-summary.csv).

`time -v` reports the timed command and does not provide a sum of simultaneous
resident memory across the Haskell process and its Z3 child, so it is evidence
for sizing rather than a whole-job memory proof.

The heaviest contract with `--solver-timeout-ms 1` returned a real
`Indeterminate` with `solver_result: "Unknown.\n  Reason: timeout"`. Calling
the wrapper with a 1-microsecond hard deadline returned `Timeout` with
`process_exit: 124`; it was never converted to `Valid`.

Recommendation for Node 3: 5-second solver timeout and 30-second hard process
timeout. The observed maximum is below 0.5 seconds, so 5 seconds preserves more
than a 10× margin; 30 seconds allows startup/load variance while still bounding
a stuck subprocess. Start with at most `min(4, available CPU cores)` concurrent
jobs, one subprocess per job, and a 256 MiB job memory limit. Recalibrate from
production telemetry rather than increasing concurrency blindly.

The completed audit contracts top out at 9 cases and 5 `When`s, far below the
80-branch stress endpoint.

### (f) Existing audits and Python validator

Pass. All six usable completed audit records were accepted by the existing
Python validator, accepted by the strict bridge, and returned `Valid`:

- `en-escrow_2party-L1-010-full.json`
- `en-loan-L4-007-full.json`
- `vi-crowdfunding-L4-004-full.json`
- `vi-escrow_3party-L4-006-full.json`
- `vi-milestone-L4-003-full.json`
- `vi-rental_deposit-L3-003-full.json`

There were no validator/bridge disagreements. Blocked audit records without a
usable contract were excluded as required.

### (g) Upstream integrity

Pass. `verify_upstream.sh` checked the pinned Git SHA and the six committed
SHA-256 values. Its final result was:

```text
verified upstream commit 7b5b1e900ec53a8eb18747992bec73470704dfcb; no patches
```

## Stable subprocess contract

The driver accepts a bare Core V1 JSON contract or
`{"contract": ..., "state": ...}`. Stdout is exactly one JSON object. The
stable statuses are:

- `Valid`: analysis proved that no modeled warning trace exists.
- `Counterexample`: at least one modeled warning trace exists; `warnings` and
  the trace are structured.
- `Indeterminate`: the solver or internal analysis did not decide; the original
  theorem result is in `solver_result`.
- `InvalidInput`: strict input parsing failed; the process exits nonzero.
- `Timeout`: added only by `run_smt.py` after a hard subprocess deadline, with
  `process_exit: 124`.

Exact examples for every status are preserved in the command log. This is
sufficient for an agent decision: only `Valid` may proceed; a
`Counterexample` can drive a targeted repair using `warnings[].type` and its
fields; the other three statuses must stop or retry under an explicit policy.

## Optional Route A comparison

Route A was retried only after the mandatory work. Ubuntu had no suitable
`libblst` package, so official `supranational/blst` tag v0.3.11, commit
`3dd0f804b1819e5d03fb22ca2e6fac105932043a`, was built into a temporary prefix.
`pkg-config` then reported `libblst 0.3.11`.

An important Stage 0.6 command error was found: `cabal build lib:marlowe`
selected the unrelated Hackage package `marlowe-0.1.0.1`. The correct local
target is `lib:marlowe-cardano`. The correct package
`marlowe-cardano-0.2.1.0` at commit
`99f432d8ef9dbd1b52b7fa089254de15913b490f` built successfully with GHC 9.2.8;
the build included `Language.Marlowe.Analysis.FSSemantics` and took 17:03.55,
with maximum reported RSS 1,445,104 KiB. No node was installed, started, or
queried.

A temporary, uncommitted Route A driver invoked
`warningsTraceWithState (SlotLength 1000)` on the same semantic fixtures:

- escrow, all five warning fixtures, both state fixtures, and the merkleized
  fixture matched Route B status and warning type (9/9);
- all six completed audit contracts matched as `Valid` (6/6);
- both address/native-token coverage fixtures were rejected before SMT because
  `addr_test1vr8nl5` is intentionally not a valid on-chain address. Route B
  accepted it as the documented opaque UTF-8 identity.

Thus no SMT warning disagreement was observed for inputs accepted by both
routes. This is useful parity evidence, not universal equivalence: only
`SlotLength 1000` was exercised, Route A has a much larger dependency surface,
and the two input layers intentionally differ in on-chain address validation.

## Node 3 integration conditions

Before invoking the analyzer, Python should:

1. validate the supported Core V1 grammar and reject unexpected fields;
2. run one contract per isolated subprocess;
3. pass both solver and hard timeouts;
4. parse stdout only as the documented JSON object and retain stderr for audit;
5. treat every status other than `Valid` as non-success;
6. record elapsed time, contract size, solver/driver/upstream versions, and peak
   memory;
7. perform separate canonical address/hash/native-token and ledger-limit checks
   where on-chain validity matters.

No Node 3 integration was added in this stage.

## Verified and not verified

Verified:

- reproducible clean build, exact upstream provenance, and no upstream patch;
- all five warning constructors and structured fields;
- strict bridge behavior, full requested constructor coverage, initial state,
  merkleized disclosure, audits, stress grid, solver timeout, and hard timeout;
- Route A build after supplying BLST and observed parity for every input both
  routes accepted.

Not verified:

- analysis of the unavailable continuation behind a merkleized hash;
- on-chain identity/encoding validity or ledger resource limits;
- semantic equivalence for every possible contract, state, `SlotLength`, or
  future upstream version;
- a summed whole-job memory peak across Haskell and Z3;
- production Node 3 integration behavior.

The next step is a separate Node 3 design/implementation stage using this
subprocess contract and its fail-closed policy.
