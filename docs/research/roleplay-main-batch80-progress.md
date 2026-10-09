# Main-pipeline roleplay: remaining 80 frozen cases

Date: 2026-10-09. Source baseline: `79b7103`. This is a **partial checkpoint**
for the frozen dataset entries 21-100, not a completed 80-case result. The
first 20 cases are reported separately in `roleplay-main-batch20-completion.md`.
All additional user answers and behavior confirmations here are explicitly
simulation-labeled; none is authenticated customer acceptance.

## Progress when OpenRouter stopped the run

- `21 vi-vesting-L2-003`: two scheduled payouts and no-deposit branches reached
  local ledger-size analysis (2 scenarios). A first contract incorrectly hid
  timed payments behind `Notify`; pinned-reference counterexample exposed it.
- `22 vi-loan-L1-001`: repayment, unpaid loan and no-loan branches reached the
  size gate (3 scenarios). The unpaid branch did not fabricate return of
  disbursed principal.
- `23 vi-cancellation_fee-L4-001`: cancellation fee/refund, travel, no choice
  and no deposit reached the size gate (4 scenarios). The no-choice full refund
  was a labeled synthetic clarification, not a fact in the frozen prompt.
- `24 vi-vesting-L1-004`: two scheduled payouts and no deposit reached the
  size gate (2 scenarios). Two initial generated contracts repeated the
  `Notify`-instead-of-timeout error and stall detection stopped that attempt.
  The general generation prompt was corrected; the unchanged reviewed core
  then produced a candidate that passed the reference and size checks.
- `25 en-loan-L2-002`: the model correctly asked for the unspecified principal
  and deadline times. A labeled answer set the simulated principal to 91 ADA.
  The next extraction request returned OpenRouter `RateLimitError`, recorded as
  `BLOCKED / llm_error / provider_limit=true`. No accepted contract exists.
- Cases 26-100: **not attempted**. No pass/fail inference is made for them.

The five attempted cases have 24 local physical-call entries, including the
rate-limited request; this is not a provider billing count. The four completed
cases have 11 observed size-checked scenarios. These are bounded checks on a
private Babbage node, not public testnet signing/submission, exhaustive
behavioral coverage, production authority, or model accuracy. The testnet
stage remained `NOT_EVALUATED` because no wallet/signing method was supplied.

## General changes after the first-20 commit

- The roleplay runner can address entries 21-100 while retaining the original
  20-case path. It validates the existing manifest's whole-dataset SHA-256,
  checks the first 20 entries unchanged, verifies 100 unique case IDs, and
  writes new evidence under a separate ignored batch-80 directory.
- The Stage 3 generation prompt explains how a payment caused solely by time
  belongs in `When.timeout_continuation`, including a two-payment schedule.
  It explicitly preserves source-stated approvals or other required inputs;
  it does not turn those into automatic payments.
- Regression tests cover frozen case selection and the timed-payment prompt.
  No frozen prompt, accepted intent, candidate JSON, Marlowe reference or SMT
  semantics was edited to force a pass.

Verification: `python -m pytest -q` reported **680 passed, 36 skipped**;
`uvx ruff check --select F401,F841` reported no findings. Skips are not counted
as integration passes.

## Resume boundary

Do not call the model again until provider access is available. Resume case 25
from its preserved requirement history with `--case-index 25` and **without**
another `--revision-file`; the simulated answer is already in local evidence.
Then continue sequentially through 100. Raw attempts, outbound-call journals,
node logs and property SQLite stay under ignored local `runs/` and are not
committed. A fresh clone of this report cannot recompute the raw results.
