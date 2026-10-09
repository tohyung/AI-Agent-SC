# Main-pipeline roleplay batch 20: completion and harness changes

Date: 2026-10-09. This supersedes the progress status in
`roleplay-main-batch20-progress.md` without rewriting that historical report.
The frozen first 20 prompts in `marlowe_ai_agent/bench/dataset/cases.jsonl` were
run sequentially through the supported main pipeline. All clarifications and
behavior confirmations were **simulation-labeled roleplay**, not authenticated
customer acceptance. No frozen prompt or candidate artifact was manually edited.

## Observed outcome

- 19/20 cases reached `SIMULATED_LEDGER_SIZE_CHECKED`, meaning local Marlowe CLI
  transaction-size analysis completed against a synchronized private Babbage
  node. One case, `vi-infeasible-L2-001`, asked to delete confirmed Cardano
  transaction history and correctly stopped as source-backed `UNSUPPORTED`.
- The local evidence contains 61 ledger-size-checked scenario attempts across
  the 19 cases. This is bounded observed branch coverage, not exhaustive
  equivalence or a 19/20 model accuracy estimate. Cases 1 and 6 have only one
  independently checked scenario each.
- There are 174 saved attempt records and 182 physical model-call entries in
  their local usage metadata across the full batch. These are local dispatch
  records accumulated over several sessions, not OpenRouter billing counts.
- No public testnet transaction was signed or submitted. The `testnet` stage
  remained `NOT_EVALUATED`; no wallet/signing method was provided.

Checked scenario counts by frozen case ID (each count includes only attempts
that reached the local ledger-size gate):

```text
01 vi-third_party-L1-001         1
02 vi-rental_deposit-L4-001      4
03 vi-escrow_3party-L3-001       4
04 vi-swap-L2-001                3
05 vi-milestone-L2-001           4
06 vi-vesting-L3-001             1
07 en-swap-L1-002                3
08 vi-infeasible-L2-001         UNSUPPORTED (0)
09 vi-escrow_2party-L3-001       3
10 en-third_party-L1-002         4
11 en-rental_deposit-L3-002      4
12 en-escrow_2party-L4-002       3
13 vi-rental_deposit-L3-003      4
14 en-escrow_3party-L1-002       4
15 en-vesting-L2-002             2
16 en-swap-L1-003                3
17 en-milestone-L4-002           4
18 vi-third_party-L2-003         4
19 en-swap-L1-004                3
20 vi-crowdfunding-L3-001        3
```

For cases 15-20 the independent scenarios exercised, respectively: two
scheduled vesting payouts and no deposit; swap success and both deposit
timeouts; two milestone approvals, partial approval, both missed and no
deposit; price 50 versus 49 and both timeouts; swap success and both timeouts;
and full crowdfunding, partial funding/refund and no funding. Saved contract
artifacts were replayed for additional branches without model calls. The
GOLD examples used an explicitly labeled placeholder native-token policy ID;
token existence, minting and exchangeability were not verified.

## General changes carried by this commit

- Stage 2B extraction now has more explicit source-backed date/time, currency
  normalization, native-token and Choice schema guidance. Repair feedback
  distinguishes missing `choice_bounds` / `choice_guard` fields from malformed
  evidence, and explains invalid `derived_from` links and duplicate ADA-unit
  claims. English local-time phrasing and one shared timezone are handled by
  deterministic calendar checks without silently inventing a timezone.
- Core v3 recognizes the source-backed request to delete ledger history as an
  unsupported signal. Stage 2C and the session runner terminate it as
  `UNSUPPORTED`, without fabricating an accepted contract or treating ordinary
  autonomous execution as unsupported in v3.
- The Stage 3 model prompt clarifies canonical Marlowe `Constant` and `Pay`
  shapes. A failed independent reference comparison can return a bounded,
  sanitized counterexample to model regeneration, including the distinction
  between a timed `When.timeout_continuation` and a `Notify` input. It never
  edits the accepted intent or candidate JSON by hand.
- Choice binding in comparison and declared Stage 4 actions uses the pinned
  reference continuation to identify the currently enabled choice, rather
  than selecting a same-owner Choice from a different branch. Stage 4 includes
  declared timeout transactions at or after the active timeout while retaining
  fail-closed behavior for ambiguous paths.
- Model transport accepts a complete JSON code fence or BOM without altering
  the parsed object; provider errors remain errors rather than business
  clarifications.
- Stage 5 records local content-addressed property/oracle observations in a
  SQLite dataset, including satisfied and inconclusive observations. It does
  not promote observations to training labels. Export requires pinned replay,
  concordant reviews and explicit data-use authorization; simulation-only
  observations remain ineligible. See `research/stage5/README.md` for trust,
  privacy, revocation and leakage-group limits. The CLI can opt out or select
  a separate dataset path.

These are shared harness changes. The SMT driver, pinned Marlowe reference,
frozen dataset and candidate artifacts were not modified to force a pass.
The local private node had to be restarted when it stopped advancing; the
ledger gate was rerun only after its tip showed synchronization and new blocks.

## Verification and limits

`python -m pytest -q`: **679 passed, 36 skipped**.
`uvx ruff check --select F401,F841`: **clean**.
`git diff --check`: no whitespace errors (Windows line-ending notices only).

The 36 skipped tests are not integration passes. `REACHED_LEDGER_PASS` proves
only the checked transaction-size condition on observed traces, not signing,
submission, public testnet validity, complete reference equivalence, or
production readiness. Simulated review and placeholder assets cannot be
silently promoted to factual user intent or real on-chain assets.

Raw attempt JSON, model output, roleplay answers, node logs, SQLite evidence
and outbound journals remain under ignored local `runs/` and are not pushed.
This report is therefore an audit summary, not sufficient on its own to
independently recompute every result from a fresh clone.
