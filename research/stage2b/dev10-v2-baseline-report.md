# Stage 2B development shadow baseline v2

This is one exploratory pass against frozen **candidate** annotations, not a
ground-truth or production accuracy estimate. No semantic threshold is applied.
The run used the unmodified Stage 2B tuning patch #1 at
`3f491816d22fac06a6ae3297e7cb23d9d8676a33`. The Stage 2A freeze verifier
passed (`stage2a-v1` aggregate SHA-256
`897249e3d355121e7cf8304e8b336dc0a4118515b4bf847f7fb8b8efad587a46`),
and the Stage 2B suite reported 48 passed. No source or provider configuration
was changed for this measurement; public validation was not run.

## Run and artifact integrity

- Selected split: `development`, 10 canonical cases, no mutations.
- Dry-run: 10 records, all `run_status=dry_run`, `prediction=null`,
  `source_corpus_version=stage2a-v1`.
- Live command: `python research/stage2b/run_shadow.py --live --split development
  --model nvidia/nemotron-3-ultra-550b-a55b:free --output
  runs/stage2b/dev10-v2-live.jsonl`.
- Model: `nvidia/nemotron-3-ultra-550b-a55b:free`. API style was `responses` in
  the prior configuration check; this run did not re-read or print `.env` and
  the JSONL does not independently record API style.
- One live pass: 10 successful case records, 0 `model_error` records, exit 0.
  Four cases used two requests each (`refund-d1`, `double-d1`,
  `conditional-d1`, `choice-d2-correction`); the other six used one. Total:
  **14 API requests**, distinct from the 10 selected cases. The output does
  not identify which internal retry/repair mechanism caused extra requests.
- Sum of per-case usage deltas: 34,407 prompt tokens, 70,485 completion tokens,
  1,678.19149 seconds of request latency, provider-reported cost 0. The cost
  is not independently verified billing.
- `runs/stage2b/dev10-live.jsonl` (v1) SHA-256 before and after the run:
  `4FBFA3558C01E1E2B56D2179432A6F5ECED64129341EB0E01CEC17A858F78A9F`.
  It was not overwritten.
- `runs/stage2b/dev10-v2-live.jsonl` SHA-256:
  `AE1A6FF9B5CD02836FF22365B12640322CE9F642A473912E197197AA9D1E69BA`.
- `runs/stage2b/dev10-v2-score.json` SHA-256:
  `42A88CF27E25A919817577E27CBF23802902D4317B517B5C505E8554B3C35EB2`.
- The three raw output files remain local and gitignored. Hashes identify the
  local artifacts but do not make them available from this repository.

## Exploratory metrics

The two resolution diagnostics for v1 were recomputed from the unchanged v1
predictions using the current scorer. Other v1 values agree with the original
baseline report. `null` denotes a zero denominator, not a zero error rate.

| Metric | v1 numerator / denominator = value | v2 numerator / denominator = value |
| --- | ---: | ---: |
| `exploratory_structural_validity_rate` | 0/10 = 0 | **0/10 = 0** |
| `exploratory_critical_claim_precision` | 0/0 = null | 13/68 = 0.1912 |
| `exploratory_critical_claim_recall` | 0/15 = 0 | 2/15 = 0.1333 |
| `exploratory_unsafe_assumption_rate` | 0/0 = null | 0/0 = null |
| `exploratory_required_clarification_recall` | 7/8 = 0.875 | 8/8 = 1 |
| `exploratory_unnecessary_clarification_rate` | 2/2 = 1 | 2/2 = 1 |
| `exploratory_unsafe_freeze_rate` | 0/8 = 0 | 0/8 = 0 |
| `exploratory_unsafe_acceptance_rate` | 0/0 = null | 0/0 = null |
| `exploratory_provenance_completeness` | 0/0 = null | 65/68 = 0.9559 |
| `exploratory_resolution_exact_match_rate` | 6/10 = 0.6 (recomputed) | 8/10 = 0.8 |
| `exploratory_conflict_classification_recall` | 0/1 = 0 (recomputed) | 1/1 = 1 |

Required clarification recall measures whether a candidate clarification or
conflict case was held for user resolution. It deliberately counts a generic
clarification on a conflict case as a hold; exact-resolution and conflict
classification measure the more specific label agreement. Since **all 10 v2
IntentSpecs are structurally invalid**, no resolution or claim metric alone
establishes intent correctness.

## Structural errors

The total number of validator messages changed from 610 in v1 to 82 in v2,
while structural validity remained 0/10. The prompt/schema contract addressed
the frequent enum and shape errors, but did not achieve a valid end-to-end
projection.

| Error pattern | v1 | v2 |
| --- | ---: | ---: |
| Invalid claim criticality | 87 | 0 |
| Invalid claim status | 76 | 0 |
| Invalid evidence target/span | 73 | 0 |
| Invalid scope type | 34 | 0 |
| Claim scope ID not found | 25 | 0 |
| Unsupported rich fields | 160 | 0 |
| Unsupported business state kind | 25 | 0 |
| Transition deadline lacks matching scoped claim reference | not compared | 15 |
| Transition actor lacks matching claim reference | not compared | 13 |
| Transition ID lacks matching business scope | 30 | 11 |
| Scope decision ID does not reference transition | 0 | 7 |
| Funding account owner lacks matching claim reference | not compared | 6 |

Other v2 errors include outcome recipient backing (5), invalid unscored
observations (5), funding relation scope (4), and invalid `derived_from`
source claims (3). These errors cluster around **claim -> scope -> rich-object
links**. Assignments across the requested failure taxonomy are: all ten cases
have `SCHEMA_OUTPUT`; `SCOPE` and `RICH_PROJECTION` dominate the remaining
validator messages; `PROVENANCE` affects three derived amounts; `CLAIM_EXTRACTION`,
`CLAIM_NORMALIZATION`, `RESOLUTION`, `CLARIFICATION`, and `CONFLICT_HANDLING`
appear in the case audit below. `MODEL_TRANSPORT=0` observed failures.
`UNSUPPORTED_HANDLING` was not exercised by these ten selected cases.

## Case-level audit

All ten records have `run_status=ok` and `structurally_valid=false`.
`raw/active/matched/FP/missed` counts raw claims, active critical predicted
claims, exact matched critical claims, false positives, and missed active
candidate critical claims, respectively. Exact matching uses kind, normalized
value, scope ID, and active requirement version, without fuzzy matching.
The scorer's aggregate critical-claim recall denominator includes only
accepted candidate cases, so it must not be inferred by summing the per-case
`missed` column across all resolutions.

| Case | Candidate -> predicted | Validation errors | Raw/active/matched/FP/missed | Clarification and safety assessment |
| --- | --- | ---: | ---: | --- |
| `pay-d1` | accepted -> clarify | 4 | 7/6/1/5/5 | Unnecessary payment-source question; source remains unresolved rather than invented. `SCOPE`, `RICH_PROJECTION`, `RESOLUTION`, `CLARIFICATION`. |
| `refund-d1` | clarify -> clarify | 11 | 7/7/1/6/5 | Asks to confirm known parties, amounts and deadlines, but not what "giai ngan" means or how the success branch behaves. `PROVENANCE`, `SCOPE`, `RICH_PROJECTION`, `CLARIFICATION`. |
| `choice-d1` | clarify -> clarify | 11 | 12/8/2/6/6 | Bob is Choice owner, but the questions ask for a generic timeout rather than the no-choice outcome; recipient kind/scope differs from the candidate. `SCOPE`, `CLAIM_EXTRACTION`, `CLARIFICATION`. |
| `escrow-d1` | clarify -> clarify | 14 | 10/10/2/8/6 | Correctly asks for deposit deadline. Separately asserts `payment_source_account_owner=Alice` as explicit based only on the deposit account phrase, which does not directly specify payout source. `SCOPE`, `RICH_PROJECTION`, `CLAIM_EXTRACTION`. |
| `double-d1` | accepted -> clarify | 10 | 10/9/1/8/8 | Unnecessary question about Bob's payout source. `SCOPE`, `RICH_PROJECTION`, `RESOLUTION`, `CLARIFICATION`. |
| `conditional-d1` | clarify -> clarify | 4 | 9/9/3/6/4 | Does not invent a Choice owner for Notify, but provides **no business question** for the missing Observation. `SCOPE`, `RICH_PROJECTION`, `CLARIFICATION`. |
| `choice-d2-correction` | clarify -> clarify | 5 | 9/3/1/2/3 | Bob is superseded and Alice is active, but Alice is `explicit/nonfinancial` rather than candidate `user_confirmed/financial`; payout scope differs. `CLAIM_NORMALIZATION`, `SCOPE`, `RICH_PROJECTION`. |
| `pay-d2-clarify` | clarify -> clarify | 7 | 14/4/1/3/2 | Recipient/source remain unresolved, but eight questions introduce several unsupported branches. Derived amount provenance fails. `PROVENANCE`, `SCOPE`, `RICH_PROJECTION`, `CLARIFICATION`. |
| `escrow-d2-clarify` | clarify -> clarify | 13 | 9/9/1/8/5 | Asks about Choice-owner interpretation but omits the account-owner question. Marks both Lan and Minh as active explicit Choice owners in one scope, creating a false conflict. `CONFLICT_HANDLING`, `PROVENANCE`, `SCOPE`, `CLARIFICATION`. |
| `double-d2-conflict` | conflict -> conflict | 3 | 3/3/0/3/2 | Preserves both conflicting deadlines, but puts them in `global` rather than `deposit-1` and supplies no required business question. `SCOPE`, `CONFLICT_HANDLING`, `CLARIFICATION`. |

No case was predicted `accepted_interpretation`, so unsafe acceptance has a
zero denominator. No predicted claim used `status=assumed`; this does **not**
rule out hidden assumptions mislabeled `explicit`, as in `escrow-d1`.
Clarification failures include the two unnecessary holds (`pay-d1`,
`double-d1`), no question on `conditional-d1` and `double-d2-conflict`, and
questions that miss the key ambiguity in `refund-d1` and `escrow-d2-clarify`.
Conflict classification is exact in `double-d2-conflict` (1/1) but its
IntentSpec remains invalid. The missing question and wrong scope are material.

## Interpretation and status

**Observed change on one additional exploratory pass:** enum/evidence/rich-key
compatibility improved in this run, but structural validity did not move from
0/10. The remaining errors are mostly cross-field backing and scope alignment,
not simple enum spelling. Exact-resolution agreement can occur by chance on
an invalid IntentSpec. One pass is subject to sampling, provider, and model
serving variation; these observations do not establish better semantic
understanding, model generalization, or production accuracy. Do not tune on
public validation or claim Stage 2B completion from this result.

- Stage 2B foundation: ACCEPTED
- Development baseline v1: MEASURED
- Prompt/schema tuning patch #1: ACCEPTED
- Development baseline v2: MEASURED
- Public validation: NOT RUN
- Stage 2C: NOT STARTED
- Production authority changed: NO
