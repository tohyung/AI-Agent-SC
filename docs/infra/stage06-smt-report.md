# Stage 0.6 — Standalone Marlowe SMT analysis

Date: 2026-09-28

## Verdict

**SMT độc lập chạy được, đạt cả 3 tiêu chí.**

The working path is Route B, using
`Language.Marlowe.Analysis.FSSemanticsFastVerbose.warningsTraceWithState` from
`marlowe-lang/marlowe` plus a small Core V1 JSON bridge. It runs under WSL2,
uses Z3 directly, and does not install, start, or query `cardano-node`.

The three acceptance criteria all passed:

1. `marlowe_ai_agent/tests/fixtures/escrow_golden.json` returned `Valid`.
2. The three hand-written negative contracts returned three distinct and
   expected counterexamples: `TransactionPartialPay`,
   `TransactionNonPositiveDeposit`, and `TransactionShadowing`.
3. The largest completed L4 audit contract returned `Valid` in 0.10 seconds in
   each of three runs, well below the five-minute limit. Peak resident memory
   was 28,588 KB, 28,800 KB, and 28,432 KB.

Raw commands, solver output, measurements, and build blockers are in
[stage06-command-log.md](stage06-command-log.md).

## Tested environment

- WSL2 kernel: `6.18.33.2-microsoft-standard-WSL2`, x86_64.
- Z3: `4.13.3` (64 bit), installed from Ubuntu packages.
- GHC used by the working driver: `9.6.7`, installed with GHCup.
- GHC also tested: `9.2.8`.
- cabal-install: `3.10.3.0` (Cabal library `3.10.3.0`).
- GHCup: `0.2.6.2`.
- Route B source: `marlowe-lang/marlowe` commit
  `7b5b1e900ec53a8eb18747992bec73470704dfcb`, dated 2026-05-26.
- Route A source: `marlowe-lang/marlowe-cardano` commit
  `99f432d8ef9dbd1b52b7fa089254de15913b490f`.
- Build data, driver source, and hand-written contracts are outside Git under
  `/home/tohung/stage06-infra/`.

## Route B result

The inspected entry point is exactly:

```haskell
warningsTraceWithState
  :: Contract
  -> Maybe State
  -> IO (Either ThmResult
                (Maybe (POSIXTime, [TransactionInput], [TransactionWarning])))
```

`warningsTrace` calls this function with `Nothing`. Unlike the older
`marlowe-cardano` implementation, this reference implementation does not take
a `SlotLength`. Its implementation calls `proveWith z3`; `Right Nothing`
means no warning trace exists, `Right (Just ...)` carries the counterexample,
and `Left ThmResult` is an indeterminate solver result.

The upstream `cabal build all` is not clean with either initially tested
compiler:

- GHC 9.2.8 reaches `sbv-10.12` but fails because SBV treats the missing
  `GHC.TypeLits.SChar` import warning as an error.
- GHC 9.6.7 builds SBV and compiles `FSSemanticsFastVerbose`, but the unrelated
  upstream example executable also includes `MkSymb.hs`, which imports the
  newer Template Haskell type `BndrVis` unavailable in GHC 9.6.

This does not block the analysis path. The external driver builds only the
seven modules it needs, including the unmodified upstream
`FSSemanticsFastVerbose`, and links successfully with GHC 9.6.7. The final
driver build took 12.37 seconds and peaked at 342,568 KB while compiling.

## Core V1 JSON bridge and semantic equivalence

The reference package's SMT `Contract` type has no Aeson `FromJSON` instance.
The external bridge parses the agent's supported Core V1 grammar and maps every
supported constructor directly:

- `Contract`: Close, Pay, If, When, Let, Assert.
- `Case` and MerkleizedCase; `Action`: Deposit, Choice, Notify.
- `Value`, `Observation`, `Party`, `Payee`, `Token`, `ChoiceId`, and `Bound`.
- POSIX times remain integral milliseconds and the analysis starts with
  `Nothing` state, matching an empty initial state.

Representational differences are limited and documented:

- The reference `Role`, `Address`, `ChoiceName`, and token fields use
  `ByteString`. The bridge UTF-8 encodes JSON strings. This preserves identity
  and equality for canonical JSON strings, which is what the warning analysis
  uses, but it does not validate or decode an on-chain Shelley address.
- Currency symbols, token names, and merkleization hashes are likewise treated
  as opaque UTF-8 bytes, not hex-decoded bytes. Equality remains injective for
  canonical strings, but ledger-level byte length and hash validity are out of
  scope. Those belong to the separate pre-deployment ledger-limit check.
- The reference contract constructors and warning semantics used here are
  otherwise one-to-one with the agent's supported Core V1 grammar. The tested
  fixture and selected audit contract contain no addresses or merkleized cases.

The bridge is intentionally outside the application repository. Before Node 3
integration, it should also enforce exact object field sets (the Python
validator already does this) and add golden tests for addresses, native tokens,
all expression constructors, and merkleized cases.

## Solver results

The stable success envelope is:

```json
{"counterexample":null,"status":"Valid","warnings":[]}
```

The overpayment contract deposits 10 and then attempts to pay 20. Its exact
result is:

```json
{"counterexample":{"start_time":"0","transactions":["TransactionInput {txInterval = TimeInterval 0 0, txInputs = [NormalInput (IDeposit (Role \"Alice\") (Role \"Alice\") (Token \"\" \"\") 10)]}"]},"status":"Counterexample","warnings":["TransactionPartialPay (Role \"Alice\") (Party (Role \"Bob\")) 10 20"]}
```

The zero-deposit result contains
`TransactionNonPositiveDeposit (Role "Alice") (Role "Alice") 0`. The duplicate
`Let` result contains `TransactionShadowing "x" 1 2`. Each result includes a
start time and transaction list and therefore meets the requested
counterexample shape.

## Hardest L4 selection and measurements

Among completed `marlowe_ai_agent/bench/audit/*-L4-*-full.json` records,
`vi-milestone-L4-003-full.json` is largest by the requested branch measure:
`case_count = 9` and `when_count = 5`. The next completed L4 records have 4/3,
3/2, and 2/2 respectively. Blocked cancellation-fee runs have no usable
contract complexity.

The copied test input was checked structurally equal to the audit record's
`contract` property (`equal=True`, both compact serializations length 3279).
With `/usr/bin/time -v timeout 300`:

- Run 1: `Valid`, wall 0.10 s, maximum RSS 28,588 KB.
- Run 2: `Valid`, wall 0.10 s, maximum RSS 28,800 KB.
- Run 3: `Valid`, wall 0.10 s, maximum RSS 28,432 KB.

These observations show no explosion for the current hardest audit sample.
They do not prove a general complexity bound: the implementation sizes its
symbolic trace from `1 + countWhens`, and branch/value combinations can still
grow sharply on adversarial or substantially larger contracts.

## Route A result and blocker

Route A was attempted because time remained. After a transient CHaP DNS failure,
`cabal update cardano-haskell-packages` succeeded. Installing Ubuntu's
`libsodium-dev` resolved the first native dependency, but dependency resolution
then stopped because the required pkg-config package `libblst-any` was absent.
The decisive error is preserved verbatim in the command log.

Therefore Route A is **not operational in this stage**. Its blocker is the
Cardano native cryptography dependency/toolchain (`libblst-any`), not a running
node and not the SMT API. Because Route B already met all acceptance criteria,
no bespoke BLST build was added and no further Cardano dependency stack was
introduced.

## Node 3 integration assessment

The output is suitable for a stable structure
`{status, warnings[], counterexample}`:

- `Valid`: exit 0, `warnings: []`, `counterexample: null`.
- `Counterexample`: exit 0, warning constructor strings plus start time and
  transaction trace.
- `Indeterminate`: represented by a distinct status when SBV returns `Left`.
- Parse/build/process errors: nonzero process exit and diagnostics on stderr.
- Timeout: enforced by the caller (`timeout 300` in this experiment), distinct
  from solver JSON and therefore detectable as process termination.

For Node 3, package the working driver as a small version-pinned CLI or isolated
HTTP worker. The Python node should validate Core V1 JSON first, invoke one
analysis per subprocess/job, parse only stdout JSON, retain stderr for audit,
and apply CPU/memory/concurrency limits. A 30-second normal timeout with a
300-second hard ceiling is recommended initially. Record contract complexity,
elapsed time, peak memory, solver version, and source commit so the ceiling can
be tuned from production-like samples. A timeout must produce an explicit
`timeout` outcome, never `Valid`.

No additional Cardano service is needed for this SMT step. The independent
ledger-limit check remains a later deployment concern with a version-pinned,
isolated devnet.

## Background claims checked

Verified from source or execution:

- `marlowe-cli run analyze` imports the Safety Ledger/Transaction/Types modules,
  and `marlowe-cli.cabal` has no SBV dependency.
- `marlowe/marlowe-cardano.cabal` version 0.2.1.0 depends on `sbv ^>=9.2`.
- Route A's `warningsTraceCustom`/`warningsTraceWithState` signatures and
  `Right Nothing`/counterexample interpretation.
- In the checked-out main tree, direct callers were found in
  `marlowe-test` and `marlowe-contracts`.
- Route B's exact entry point, Z3 call, input/output type, and lack of a Core V1
  Aeson instance on its SMT `Contract`.
- The release/main Cardano version pins recorded in the Stage 0.5 correction.
- Standalone execution does not require `cardano-node`.

Not verified in this stage:

- The separate `marlowe-symbolic` service was not present in the inspected
  `marlowe-cardano` checkout, so its caller relationship remains unverified.
- Organization-wide absence of every possible fork or unpublished newer CLI
  was not re-proven; the prior release audit and the inspected official source
  are retained as the available evidence.
- Runtime behavior for arbitrary Shelley addresses, merkleized continuations,
  native tokens, or contracts materially larger than the current L4 audit set.
