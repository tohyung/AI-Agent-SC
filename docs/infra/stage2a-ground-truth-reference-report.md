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

`research/stage2a/corpus/{development,validation}.jsonl` contains 32
**candidate** cases, 16 in each public split. All 32 have annotation
status `draft`, author `codex`, and no reviewer or adjudicator. The 12
controlled mutation records inherit a parent interpretation in the same split
and test a specified behavioral deviation, not a new user intent. There are
6 proposed accepted canonical cases; this is a composition count, not
an accuracy result. No model accuracy, precision or recall was measured.

Family distribution: choice-based release 6, conditional payment 5,
deposit-refund 5, simple timed payment 5, single-deadline escrow 6,
two-deadline escrow 5. Current resolutions: accepted interpretation 12,
clarification required 16, conflict resolution required 3, unsupported in
current study 1. Mutation types: double payment, missing refund, reversed
timeout branch, swapped deadline, unauthorized choice, wrong account owner,
wrong amount, wrong Choice owner, wrong depositing party, wrong recipient,
wrong token and wrong unit scaling (one each).

Records keep versioned requirement history, scoped claims with source spans and
normalization bases, supersession links, required clarifications, forbidden
assumptions, abstract behavior expectations, mutation provenance and annotation
metadata. Scope IDs identify case-local business transitions, branches,
timeouts or outcomes, not AST paths. Choice owner, depositing party, account owner, payment source and
recipient are distinct concepts; a transaction submitter is not inferred from
Core V1 inputs. A later correction can supersede an older explicit claim.
Behavior expectations do not use exact AST equality. The public split
keeps parent/mutations together and rejects exact cross-split requirement
duplicates; it is **not** a blind evaluation set even if later frozen. These
32 cases seed schema/protocol development, not production-accuracy claims.

The human queue is `research/stage2a/review_queue.md` with approve/edit/reject
for every case. The following seven canonical cases now propose
`clarification_required`, rather than silently supplying missing facts:
`choice-d1` (no-choice timeout outcome), `choice-d2-correction` (funding/account
and Choice deadline), `refund-d1` (meaning of disbursement and success path),
`refund-e1` (Notify-success continuation), `escrow-d1` (deposit deadline), and
`conditional-d1`/`conditional-e1` (which Marlowe Observation establishes
completion/delivery). The questions are proposed content, not end-user answers.
The remaining cases and all mutations also require review. Approval must
include each claim, normalized value, abstract trace and mutation relation.

`research/stage2a/protocol.md` defines the seven future metrics with exact
numerators and denominators, including case-level Unsafe Freeze Rate. It does
not set a numeric promotion threshold before baseline data exists. Future
assurance records separate verdict, method, scope, coverage, evidence and
assumptions; `tested` is not a verdict and `exhaustive` requires a completeness
argument.

## Pre-adjudication hardening (prior patch)

The former public `evaluation` split was renamed/reclassified as `validation`.
It was exposed during schema development, so freezing or versioning it cannot
make it an independent blind test. A future hidden set must be generated after
schema stabilization, human-reviewed, independently versioned and kept outside
the development agent's context. Public development/validation scores can
inform debugging and model selection, not production-promotion accuracy claims.

Each canonical case now defines `behavior_scopes`; each claim references one
`scope_id`. The validator checks scope identity and references, conflicts by
`(kind, scope_id)`, and requires supersession to stay in the same scope.
Mutations must share exact requirement history, family, group, split,
resolution and clarifications with a canonical parent; they have no local
claims or scopes. The review queue renders inherited claims, derived values and
scope IDs. `choice-e1` previously used one refund claim for reject and timeout;
the migration represented the same stated recipient as two separately scoped
draft claims with distinct source spans. No resolution or claim value was
changed. Annotation status now strictly determines `ground_truth_source`, and
the reference wrapper checks both pinned upstream SHA and driver version.

These changes were made by the development agent. The prior external review
was a source/design assessment, not an independent Haskell rerun of this HEAD.
The reference-test counts below are local/WSL execution evidence, not an
independent reviewer CI result. The current draft annotations are still not
gold.

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

Ground-truth review is required before Stage 2B. A meaningful subset must be
genuinely reviewed and the development/public-validation protocol sufficiently
frozen before shadow experiments begin; no hidden set is required merely for
those experiments. Before accuracy supports production promotion, an
independent hidden evaluation protocol is mandatory. The researcher must
approve, edit or reject each proposed case/claim, then separately version and
hash approved sets. Until then: **Stage 2A infrastructure/schema: HARDENED;
candidate corpus: DRAFT / HUMAN REVIEW PENDING; public validation:
PROVISIONAL; Stage 2B: BLOCKED pending human adjudication; production-promotion
metrics: BLOCKED pending future independent hidden evaluation.**

## Hardening verification

At baseline HEAD `9095f85350901cdaf32ad18b587e0d9e5fc013b6`, only the
pre-existing ZIP was untracked. The migration preserved all 32 requirement
histories, resolutions, original claim kinds/values/statuses, and draft
annotation statuses. The one additional `choice-e1` refund claim is a
scope-specific representation of the already stated timeout refund, not a new
recipient or adjudicated fact. Seven case-specific concerns are review notes,
not changed labels. The public split is 16 development / 16 validation.

Current local evidence: corpus validation 32/32; Stage 2A foundation tests
24 passed; reference suite in WSL 20 passed (17 semantic + 3 wrapper identity);
SMT package regression 32 passed; production Python suite 228 passed,
7 skipped; Ruff F401/F841 clean. `verify_upstream.sh` confirmed the pinned
commit with no patches. Two review-queue regenerations produced identical
SHA-256 `6d2efe5aebaaab0cb83ed9867644913db7d07ec6a2e363358d91391f3979d93`.
No independent reviewer rerun is claimed. LLM/API calls: 0; production and
ledger/deployment files changed: 0.

## Researcher-approved semantic content pass

This pass starts from `9912b8c916382c95dfd4ff2c77a5766372ed58b0` and
applies the researcher's plan to **candidate content only**. All 32 cases
remain; development/validation stay 16/16. Before: 25 accepted, 3
clarification, 3 conflict, 1 unsupported. After: 12 accepted, 16
clarification, 3 conflict, 1 unsupported. The structured baseline diff has
9 unchanged cases and 23 edited cases;
none was rejected. Seven canonical cases changed to
`clarification_required`: `refund-d1`, `choice-d1`, `escrow-d1`,
`conditional-d1`, `choice-d2-correction`, `refund-e1`, `conditional-e1`.
Their six mutations inherited the same resolution and questions.

The edited canonical cases add only requirement-grounded claims with exact
source spans and case-local scopes. `double-d1` and `double-e1` gained
`decision-1:approve` branch scopes; `escrow-d2-clarify` and
`choice-e2-clarify` gained distinct timeout-refund scopes linked to explicit
Choice deadlines. The latter two still ask which funding account is used.
`pay-d2-clarify` gains its explicit 1100 ms deadline, but **not** a Marlowe
depositor claim: the wording “Alice gửi” is not taken as sufficient proof of
that role or of account ownership. `escrow-d1` gains only the explicit 6000 ms
approval deadline, not an inferred deposit deadline. No Notify Observation or
oracle is invented for either conditional case.

Mutations remain implementation-deviation candidates, not independent
accepted contracts. Six descriptors/behavior summaries were scoped to their
updated parent: `refund-d1-m-missing`, `choice-d1-m-owner`,
`escrow-d1-m-party`, `conditional-d1-m-token`, `refund-e1-m-account`, and
`conditional-e1-m-double`. They assert violations only of explicit facts; a
valid success Observation or unspecified disbursement path is not assumed.
The other six were checked against updated effective parent claims/scopes and
kept unchanged. Exact requirement histories and **all annotation metadata**
match the baseline case by case. A researcher-approved classification plan
does not constitute an answer from the end user or finalized ground truth.

**Current status:** schema HARDENED; semantic adjudication content APPLIED;
clarification cases correctly classified but missing business facts NOT
RESOLVED; mutation corpus REVALIDATED; annotations still DRAFT/CANDIDATE;
ground-truth freeze NOT DONE; Stage 2A NOT CLOSED; Stage 2B NOT STARTED.
Next gate: cross-case consistency audit, then corpus version/manifest/hash and
freeze after the remaining human decisions.

Patch verification from baseline `9912b8c`: corpus validator accepted 32/32
draft cases; foundation tests 31 passed; production Python tests 228 passed,
7 skipped; `compileall` exited 0; Ruff F401/F841 clean. The regenerated
review queue was byte-identical across two runs (SHA-256
`f81ff87715c5be8bc5b15e844b95955ecd1af1665da3837af9c4fd0d0785c897`).
No SMT/reference/production code was edited or rerun for this corpus-only
patch. LLM/API calls: 0.
