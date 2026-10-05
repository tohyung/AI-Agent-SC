# Batch 01 capability inventory (offline)

Generate the frozen 20-case inventory with:

```bash
python -m research.experiments.batch_capability_matrix
```

The inventory checks the manifest and dataset SHA-256 before reading the first
20 records. It covers nine families: swap (4), third-party choice (3), rental
deposit (3), escrow with three parties (2), escrow with two parties (2),
milestone (2), vesting (2), crowdfunding (1), and infeasible (1). Six records
declare missing source facts. `info_mode=complete` is dataset metadata, not a
verified model result or authorization to fill unspecified facts.

## Shared construction rule

An accepted, source-grounded intent can be decomposed into typed Deposit,
Choice, Notify, Pay, IfChoice, When, and Close nodes. The deterministic lowerer
validates Core V1 structure and emits source-to-AST paths. It rejects invalid
amounts/deadlines, noncanonical asset identities, and Choice guards that cannot
refer to a Choice on their current path. Production compiler profiles must
still prove their own control-flow linkage, funding conservation, claim
coverage, and exact profile match before granting compiler authority.

Synthetic Haskell-reference tests cover Choice success/refund/timeout,
ADA/native-token swap with timeout refund, two-depositor success/refund, and
Notify with split payout/refund. The existing linear-time-release compiler now
uses the shared lowerer and retains its source and conservation checks. These
tests show that the representative primitive compositions execute, **not**
that the 20 Batch 01 candidates are semantically correct or ledger-ready.

## Remaining gates

- A missing amount, deadline, account owner, approval rule, or native asset
  identity remains unresolved until supported by source evidence or an
  explicitly labeled simulation answer. GOLD reward points are not silently
  treated as a Cardano native asset.
- Profile hints in the inventory are not profile matches. Crowdfunding has no
  accepted-intent compiler profile; multi-depositor accounting and complete
  refund coverage remain explicit work. Other families may also fail their
  strict profile shape and need generalized, evidence-preserving lowering.
- An infeasible request requires a feasibility finding, not an artificial
  contract or a forced ledger verdict.
- Reference execution proves the resulting Core V1 behavior for tested traces;
  it does not prove source-intent faithfulness or ledger validity. Ledger
  analysis remains a separate downstream gate.

No live model calls, candidate rewrites, authority promotion, or new Batch 01
ledger verdicts were made by this inventory and primitive work.
