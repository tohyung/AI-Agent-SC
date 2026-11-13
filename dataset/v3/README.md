# Dataset v3 (E6)

Frozen 2026-11-10, before any pipeline or baseline run on it. Design: `docs/archive/E6-Dataset-Design.md`.

SHA-256 of `cases.jsonl`:
`cdc0ea456f2e103d86bb195522b6510755e65fdd5c9f9e1e2342cf68ad6e46cc`

## Contents

- **Size and language:** 100 cases, 60 Vietnamese (10 without diacritics) and 40 English (8 mixing Vietnamese
  and English).
- **Expected behaviour:**
  - 40 complete;
  - 25 missing facts (the system must ask);
  - 10 ambiguous;
  - 10 conflicting or self-corrected;
  - 5 feasible with one unsupported extra request (the system must say so);
  - 10 infeasible or out of scope (the system must refuse).
- **Families:** 19 contract families, with no price oracle. The 10 feasible v2 families are kept, plus
  installment, k-of-n approval, first-come sale, zero-coupon bond, coupon bond, split, collateral loan,
  deduction and matching donation.
- **Prompts:** written by hand by Claude to probe known weaknesses (`adversarial_target`, `author_note`), in the
  voice of a user talking to the system.

## Fields

| Field | Meaning |
| --- | --- |
| `prompt` | the user's message to the system |
| `spec` | structured facts; `builders.py` turns it into `reference_contract` and `checks.scenarios` |
| `fact_sheet` | answers the simulated user gives when asked; the only source for facts the prompt omits, shared by every arm |
| `expected_behavior` | `converge`, `ask_then_converge`, `flag_conflict_then_converge`, `converge_and_decline_extra`, `reject_unsupported` |
| `phenomena` | hand tags, plus tags detected from the prompt by `build.py` |
| `marlowe_features` | constructs read off the reference contract |
| `reference_contract` | Core V1 JSON; `null` for infeasible cases |
| `checks.scenarios` | steps with absolute POSIX-ms times; expected payouts computed from the spec, not from running the contract |

## Checks done before freezing

- `python -m dataset.v3.build --write` checks:
  - every reference passes `validate_contract`;
  - every scenario gives the spec-derived payouts on `dataset/marlowe_sim.py`, with no rejected input and
    no partial pay;
  - no duplicate or near-duplicate prompt, within v3 or against v2;
  - no storytelling openers;
  - policy ids are 56 hex characters;
  - every role name appears in the prompt or the fact sheet;
  - the coverage minimums of the design are met.
- `E5_FULL=dataset.v3.check_reference bash runs/e5/run_wsl.sh` (inside WSL): all 90 feasible references
  are SMT `Valid`, and every scenario runs on the pinned Haskell reference executor with the expected
  payouts and no warnings.

## Rules

- Do not edit cases after a run has used them. A fix needs a new version and a note in the protocol's
  deviations.
- The author of the cases is also the experimenter, the simulated user and the adjudicator. Every
  report must say so.
- Machine labels against `reference_contract` are only valid where the fact sheet fixes every fact.
  E5 showed that labels against hidden facts flip when a simulated user invents facts. Adjudicate
  model contracts against the facts the simulated user confirmed (`docs/archive/E5-Adjudication-Rubric.md`).
