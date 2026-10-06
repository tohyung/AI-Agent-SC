# Main-pipeline roleplay batch 20: progress report

Date: 2026-10-06. This report records one sequential, simulation-labeled run of
the frozen 20-case batch through the supported main pipeline. It is an interim
result, not a production or testnet acceptance report.

## Observed progress

- Cases 1-4 each reached `REACHED_LEDGER_PASS` in local Marlowe CLI transaction-size
  analysis. Together they exercised 12 successful pinned-reference scenarios:
  1 for case 1, 4 for case 2, 4 for case 3, and 3 for case 4.
- Case 5 (`vi-milestone-L2-001`) produced a structurally valid core and asked five
  business clarification questions. After simulated natural-language answers were
  added to requirement history, the next model request hit `provider_limit`.
  The pipeline reported `BLOCKED` / `llm_error`; no new contract candidate passed.
- Cases 6-20 were not attempted. Thus the batch result is 4/20 cases observed at
  the ledger-size gate, 1 provider-blocked case, and 15 not attempted. This is
  not a 4/20 semantic accuracy estimate.
- The local append-only outbound journal contains 57 reserved physical request
  attempts across cases 1-5 (15, 21, 9, 10, 2 respectively). This counts local
  dispatch reservations, including interrupted attempts; it is not a provider
  billing or dashboard count. No further provider requests were made after the
  limit was encountered.

| Case | Observed result | Scenario coverage |
| --- | --- | --- |
| `vi-third_party-L1-001` | Ledger-size gate reached; 12,194/16,384 bytes | One independent reference trace |
| `vi-rental_deposit-L4-001` | Ledger-size gate reached; 12,246/16,384 bytes | Damage, no damage, choice timeout, and no deposit |
| `vi-escrow_3party-L3-001` | Ledger-size gate reached; 12,176/16,384 bytes | Release, refund, choice timeout, and no deposit |
| `vi-swap-L2-001` | Ledger-size gate reached; 12,222/16,384 bytes | Swap, counterparty timeout, and depositor timeout |
| `vi-milestone-L2-001` | Provider limit before a revised candidate | Clarification answers recorded, no passing contract |

The additional scenarios for cases 2-4 replayed the same stored contract artifact
for each respective case without another model call. The case 4 GOLD asset was a
**labeled synthetic native-token assumption**: its policy ID/token name were not
provided by the original requirement and no real token was minted or verified.

## Harness changes

- Added an append-only, case-by-case roleplay runner with source-attributed
  natural-language answers, outbound request journaling, exact candidate and
  contract-artifact replay, and interruption-safe attempt numbering. Replay
  requires a matching reviewed candidate and preserved provenance.
- Hardened the main intent-extraction path with bounded validation repair,
  source-backed schema guidance, explicit timing and amount rules, and clearer
  unsupported/clarification handling. Model transport now classifies reported
  provider limits, records request-phase telemetry, and handles transient errors
  without treating 402/429 as repairable business ambiguity.
- Bound abstract scenario Choice inputs to a unique enabled AST ChoiceId before
  reference execution; ambiguous bindings remain inconclusive. Tightened
  intent-to-AST alignment so an unverified model-supplied JSONPath alone cannot
  prove a semantic violation. The stage 4 declared-action domain uses the same
  binder.
- Kept simulated expectations and roleplay reviewer answers explicitly separate
  from independent human acceptance and production authority. The main CLI and
  README expose the revised route and limits.

No candidate, frozen corpus, benchmark dataset, or reference/SMT semantics were
altered to make a case pass. The fixes are shared harness behavior, with focused
regression tests for the transport, replay, binding, validation, and runner.

Verification before commit: `python -m pytest research/ marlowe_ai_agent/tests/ -q`
reported **648 passed, 36 skipped**. `uvx ruff check --select F401,F841`
reported no findings. Skips are not treated as passing real integrations.

## Assurance boundary and evidence

The observed gates used a local private Babbage node and Marlowe CLI size analysis.
`REACHED_LEDGER_PASS` here means only the configured ledger-size analysis gate
completed for the simulated traces. It does **not** mean transaction signing,
submission, public testnet deployment, full ledger validity, semantic equivalence
for all possible inputs, compiler authority, or production readiness. Testnet and
deployment stages remained `NOT_EVALUATED`.

The raw attempt JSON, model output, roleplay transcript, and outbound journals
remain in ignored local `runs/roleplay-main-batch20/`; they are not committed.
This summary alone is insufficient to independently recompute every metric from
the remote repository. In particular, simulated user responses must not be
presented as authenticated acceptance of the original intent.

Resume only after provider access is available, starting at case 5 with its
preserved requirement history. If the candidate or contract was already saved,
replay that exact artifact for harness-only fixes instead of spending another
model call. Continue cases 6-20 sequentially, retaining the same assurance labels.
