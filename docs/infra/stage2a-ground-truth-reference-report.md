# Stage 2A: Ground truth and reference-semantics foundation

Baseline HEAD: `63b94828aad56c27b28b57adc11ed75fdce2c994`.
Stage 1.0 remains closed. Stage 2A infrastructure is implemented; the corpus
is **draft and awaits human ground-truth review**. Stage 2B promotion is blocked
until adjudication. No production agent behavior, output schema or trace schema
was changed.

## Scope and research basis

This stage adds a schema-neutral candidate intent/behavior corpus, an evaluation
protocol, and a concrete reference executor. It does not add production
`IntentSpec`, intent freezing, a compiler, Node 4, a Python runtime, property
learning, ledger validation, testnet or deployment.

FSM-SCG (Luo et al., IJCAI 2025) motivates checking an intermediate
representation before code generation; its structural FSM checks do **not**
establish that the model matches user intent. Lamela Seijas et al., *Marlowe:
implementing and analysing financial contracts on blockchain*, motivate using
executable reference semantics and inspecting warnings, payments, state and
continuation. LeVer (Zhang et al., ACL 2026) motivates formal/adversarial
complementarity while explicitly identifying semantic-translation fidelity as
a limitation. None of these papers proves this repository's proposed future
architecture correct.

## Corpus and annotation protocol

`research/stage2a/corpus/{development,evaluation}.jsonl` contains 32
**candidate** cases, 16 in each provisional split. All 32 have annotation
status `draft`, author `codex`, and no reviewer or adjudicator. The 12
controlled mutation records inherit a parent interpretation in the same split
and test a specified behavioral deviation, not a new user intent. There are
13 proposed accepted canonical cases; this is a composition count, not
an accuracy result. No model accuracy, precision or recall was measured.

Family distribution: choice-based release 6, conditional payment 5,
deposit-refund 5, simple timed payment 5, single-deadline escrow 6,
two-deadline escrow 5. Proposed resolutions: accepted interpretation 25,
clarification required 3, conflict resolution required 3, unsupported in
current study 1. Mutation types: double payment, missing refund, reversed
timeout branch, swapped deadline, unauthorized choice, wrong account owner,
wrong amount, wrong Choice owner, wrong depositing party, wrong recipient,
wrong token and wrong unit scaling (one each).

Records keep versioned requirement history, claims with source spans and
normalization bases, supersession links, required clarifications, forbidden
assumptions, abstract behavior expectations, mutation provenance and annotation
metadata. Choice owner, depositing party, account owner, payment source and
recipient are distinct concepts; a transaction submitter is not inferred from
Core V1 inputs. A later correction can supersede an older explicit claim.
Behavior expectations do not use exact AST equality. The provisional split
keeps parent/mutations together and rejects exact cross-split requirement
duplicates; it is **not** truly held out until reviewed and frozen. These
32 cases seed schema/protocol development, not production-accuracy claims.

The human queue is `research/stage2a/review_queue.md` with approve/edit/reject
for every case. In particular, reviewers should inspect whether these proposed
`accepted_interpretation` labels need additional clarification or edits:
`choice-d1` (timeout/no-choice outcome), `choice-d2-correction` (funding and
deadline), `refund-d1` (what constitutes disbursement), `escrow-d1` (deposit
timing), and `conditional-d1`/`conditional-e1` (source and enforceability of
the Notify condition). These are **review flags**, not resolved conclusions.
The remaining cases and all mutations also require review. Approval must
include each claim, normalized value, abstract trace and mutation relation.

`research/stage2a/protocol.md` defines the seven future metrics with exact
numerators and denominators, including case-level Unsafe Freeze Rate. It does
not set a numeric promotion threshold before baseline data exists. Future
assurance records separate verdict, method, scope, coverage, evidence and
assumptions; `tested` is not a verdict and `exhaustive` requires a completeness
argument.

## Pinned reference executor

The new `marlowe-reference` executable is additive in the existing
`tools/marlowe_smt` Cabal package. It reuses `MarloweSMT.Bridge` for strict Core
V1 JSON parsing and calls the pinned
`Language.Marlowe.Semantics.computeTransaction` for every transaction. Initial
`State` is mandatory: accounts, choices, boundValues and minTime. Each input
retains its `[from,to]` interval and the SMT counterexample's Deposit/Choice/
Notify shape. Successful steps carry the official state and continuation to
the next step; a transaction error is recorded at its index and stops without
committing the failed step. Outputs serialize structured warnings, all Payment
fields, canonical State, and full Core V1 continuation. The Python wrapper is
subprocess orchestration only, with a hard timeout and no shell invocation.

Pinned upstream commit:
`7b5b1e900ec53a8eb18747992bec73470704dfcb`.
Reference driver version: `0.1.0`. `verify_upstream.sh` checks file hashes and
reports no upstream patches. This tool is not the symbolic `marlowe-smt`
analyzer; it reports behavior for a supplied explicit trace, not warning
freedom over all symbolic traces. The existing SMT request/response behavior
remains unchanged.

Representative actual output excerpts from the reference wrapper:

```json
{"status":"Success","steps":[{"index":0,"status":"Success","warnings":[],"payments":[{"amount":10,"source_account":{"role_token":"Alice"},"payee":{"party":{"role_token":"Alice"}},"token":{"currency_symbol":"","token_name":""}}],"state":{"accounts":[],"choices":[],"boundValues":[],"minTime":0},"contract":"close"}],"final_state":{"accounts":[],"choices":[],"boundValues":[],"minTime":0},"final_contract":"close"}
```

The excerpt selects semantic fields from a funded `Close` response. The full
response also includes `meta` and `detail`. A `Pay 4` from Alice's 10-unit
account to Bob produced a 4-unit payment to Bob and a 6-unit `Close` refund to
Alice. For `When(timeout=100)`, `[99,99]` plus Notify succeeded,
`[100,100]` followed the timeout continuation, and `[99,100]` returned:

```json
{"status":"TransactionError","steps":[{"index":0,"status":"TransactionError","error":{"type":"TEAmbiguousTimeIntervalError"}}],"final_state":{"accounts":[],"choices":[],"boundValues":[],"minTime":0}}
```

The command log records the actual invocation and observed semantic summaries;
the JSON above is a selected excerpt of the wrapper's full response.

## Supported fragment and limits

The parser handles the current canonical Core V1 contract grammar and explicit
State/normal Deposit, Choice and Notify inputs. Reference tests cover Close
refund, Pay-to-Party/Account, same-account transfer, all five warning types,
Choice bounds, Notify truth, timeout-before/after/straddle, nested timeout
regions, minTime trimming, multiple inputs and transactions, and error-stop
behavior. Merkleized cases or inputs are conservatively `Unsupported`; no
hash continuation is guessed. Off-chain event truth, real signer/role-token
ownership, transaction construction, ledger validity and deployment are not
modeled. The harness is an execution oracle only for the explicit traces and
initial states supplied; the candidate corpus's abstract behavior annotations
have **not** been reference-verified or human adjudicated as a set.

## Test evidence and next gate

- `tools/marlowe_smt/verify_upstream.sh`: verified exact pin, no patches.
- `tools/marlowe_smt/run_tests.sh` in WSL: 29 passed (12 existing SMT/bench
  tests plus 17 new reference tests).
- `python -m pytest research/stage2a/test_foundation.py -q`: 15 passed.
- `python research/stage2a/foundation.py validate`: 32 draft cases valid.
- `python -m pytest marlowe_ai_agent/tests/ -q`: 228 passed, 7 skipped on
  Windows under the existing real-SMT integration policy; 0 failed.
- `uvx ruff check --select F401,F841`: all checks passed.
- LLM/API calls: 0. Ledger/testnet/deployment changes: 0.

Ground-truth review is required before Stage 2B promotion. The researcher
must approve, edit or reject each proposed case/claim, then separately freeze
the approved development/evaluation sets, corpus version and SHA-256. Until
then: **Stage 2A infrastructure: IMPLEMENTED; ground-truth corpus: DRAFT /
HUMAN REVIEW PENDING; Stage 2B promotion: BLOCKED.**
