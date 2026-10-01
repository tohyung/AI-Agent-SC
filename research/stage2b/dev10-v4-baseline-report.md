# Stage 2B development shadow baseline v4

**Observed change on one additional exploratory stochastic pass.** This is not
an accuracy claim, a causal estimate of the prompt patch, or human-reviewed
ground truth. The reference is frozen Stage 2A candidate annotations. No case
was rerun or selected by output quality; public validation was not run.

## Contract patch and run integrity

- Baseline HEAD: `e50b47ceceb52f6d57c5a105f27f9d87fff5c9a1`.
- Source patch: `a82a7e8e4b33bd4ed9f8b970058b4b111f14932d` (`fix(stage2b): expose remaining core prompt invariants`).
- The core prompt now states that every `decision_id` references an existing
  transition scope, `scope_id` is unique, and `deadline_claim_id` references an
  existing deadline claim. It exposes the exact required observation fields,
  reason, and source-evidence shape. The validator shares the relevant Stage 2B
  constants. Claim/resolution taxonomy, scoring, projector, Stage 2A, and
  production code were not changed.
- Offline gates before commit/live: Stage 2A freeze verified; Stage 2B
  **103 passed**; Stage 2A **46 passed**; agent tests **228 passed, 7 skipped**;
  `compileall` and Ruff F401/F841 passed. The seven renderer skips reflect
  environment/test prerequisites, not passing renderer executions.
- Dry run: 10 distinct canonical development cases; all predictions null;
  `stage2b-shadow-core-v1` and core-only prompt with both new contracts verified.
- Live command: `python research/stage2b/run_shadow.py --live --split development
  --model nvidia/nemotron-3-ultra-550b-a55b:free --output
  runs/stage2b/dev10-v4-live.jsonl`. Exactly one pass. It wrote all 10 records
  and returned nonzero because two records have `model_error=invalid_model_json`.
  No bad case, empty object, or failed JSON response was rerun.
- Native score used `FrozenCandidateAdapter().load(split="development")` and
  `score_predictions(predictions, candidates, run_records=run_records)`: all 10
  selected records, eight projected predictions, no historical scoring mode.
- Local gitignored artifact SHA-256:
  - `runs/stage2b/dev10-v4-dry.jsonl`:
    `B14A847A10751AE89A4341D568425F770DF3B64A0BE24F6861D94D69D4D349D4`
  - `runs/stage2b/dev10-v4-live.jsonl`:
    `BAFCDBE41F490109EB794A2D38FB0084EEBD0204AAA65A5F437FED9DF50DC6B8`
  - `runs/stage2b/dev10-v4-score.json`:
    `2786667B81FB596B138AC86BE9428A37723E19E5DF7CFD41FCEEB152797500AC`
  The v3 local artifacts retain their hashes recorded in the v3 report.

## Exploratory native metrics

| Metric | Numerator / denominator | Value |
| --- | ---: | ---: |
| Core output rate | 8 / 10 | 80.0% |
| Core structural validity | 7 / 10 | 70.0% |
| Full structural validity | 7 / 10 | 70.0% |
| Projection completeness on valid cores | 73 / 73 | 100.0% |
| Critical claim precision | 23 / 47 | 48.9% |
| Critical claim recall | 5 / 15 | 33.3% |
| Provenance completeness | 47 / 47 | 100.0% |
| Resolution exact match | 6 / 10 | 60.0% |
| Conflict classification recall | 1 / 1 | 100.0% |
| Required clarification recall | 6 / 8 | 75.0% |
| Unnecessary clarification rate | 1 / 2 | 50.0% |
| Unsafe freeze rate | 0 / 8 | 0.0% |
| Unsafe acceptance rate | 0 / 0 | N/A |
| Unsafe assumption rate | 0 / 0 | N/A |

Core output counts JSON objects, including the empty `{}` from
`choice-d2-correction`. Both model-error cases count in all-case rate
denominators but have no prediction. Critical claim recall follows the scorer's
accepted-candidate denominator policy; the per-case missed counts below are
descriptive across all candidate cases. Zero denominators are unavailable,
not evidence of zero risk.

## Contract diagnostics and attribution

| Core diagnostic | V3 | V4 |
| --- | ---: | ---: |
| `decision_id` does not reference transition | 10 | 0 |
| Duplicate `scope_id` | 1 | 0 |
| Invalid `unscored_observation` | 3 | 0 |

The v4 core validator emitted nine messages, all cascading from one empty
object, not nine independent defects. The two malformed-JSON responses do not
reach core validation. The three targeted categories disappearing is
**consistent with improved prompt/validator compatibility in this pass**; the
single stochastic pass cannot establish causality. It also cannot prove those
rules would be obeyed on the two cases with no parseable output.

Three separate assessments:

- **Harness/prompt contract:** Both previously implicit contracts are explicit
  and regression-tested. No targeted reference or observation violations were
  observed among eight emitted cores.
- **Model core extraction:** Two responses were invalid JSON; one emitted core
  was `{}`. Valid cores still have candidate-relative semantic mismatches:
  `23/47` critical-claim precision, `5/15` recall, and `6/10` resolution match.
  `pay-d1` asks an unnecessary question. No invalid `derived_from` was observed
  in v4; no false conflict classification was observed. Exact claim mismatches
  can involve scope/provenance as well as value, so they are not by themselves
  proof of an amount-normalization defect. Individual normalization and
  question-quality errors were not independently adjudicated from raw text.
- **Deterministic projector:** Seven valid cores produced seven strict-valid
  full IntentSpecs, with 73/73 eligible mandatory facts projected. Observed
  projector errors on valid cores: **0**. The seven full errors generated from
  the empty core are a cascade, not independent projector errors.

## Per-case audit

`M/FP/Missed` is exact critical-claim matching under the scorer key. `Q` is
predicted/candidate clarification count; it does not assert individual
question equivalence. `-` denotes unavailable output, not a valid core.

| Case | Run; core/full valid; errors core/full; projection | Resolution predicted -> candidate | M/FP/Missed | Q | Diagnostic / note |
| --- | --- | --- | ---: | ---: | --- |
| `pay-d1` | ok; yes/yes; 0/0; PASS | clarification -> accepted | 5/2/1 | 1/0 | Unnecessary clarification; resolution mismatch. |
| `refund-d1` | ok; yes/yes; 0/0; PASS | clarification -> clarification | 3/5/3 | 3/2 | Resolution matches; claim mismatch remains. |
| `choice-d1` | ok; yes/yes; 0/0; PASS | clarification -> clarification | 5/5/3 | 6/1 | Many questions; content not separately adjudicated. |
| `escrow-d1` | model_error; -/-; 0/0; - | - -> clarification | 0/0/8 | -/1 | Invalid model JSON; no core to classify. |
| `double-d1` | model_error; -/-; 0/0; - | - -> accepted | 0/0/9 | -/0 | Invalid model JSON; no core to classify. |
| `conditional-d1` | ok; yes/yes; 0/0; PASS | clarification -> clarification | 5/4/2 | 5/1 | Resolution matches; several extra questions. |
| `choice-d2-correction` | core_invalid; no/no; 9/7; CORE_INVALID | - -> clarification | 0/0/4 | -/3 | `MODEL_SCHEMA_COMPLIANCE`: one empty `{}` caused all nine core errors. Full errors are cascade. |
| `pay-d2-clarify` | ok; yes/yes; 0/0; PASS | clarification -> clarification | 2/2/1 | 2/2 | Resolution matches; claim mismatch remains. |
| `escrow-d2-clarify` | ok; yes/yes; 0/0; PASS | clarification -> clarification | 3/3/3 | 1/2 | Fewer questions than candidate; content not adjudicated. |
| `double-d2-conflict` | ok; yes/yes; 0/0; PASS | conflict -> conflict | 0/3/2 | 2/1 | Conflict class matches; critical claims differ. |

Only `choice-d2-correction` is a core-invalid case; its root label is
`MODEL_SCHEMA_COMPLIANCE`. The two `invalid_model_json` cases are model-output
failures before core validation, so they are not relabeled as core-invalid or
projector defects.

## Usage and comparison

- Selected cases: **10**. Provider-reported requests: **10** (one per case in
  recorded usage). `model_error`: **2**. No manual retry or second pass.
- Provider usage sums: **15,422 prompt tokens**, **34,562 completion tokens**,
  **1,315.676 seconds** request latency, provider-reported cost **0**. Cost is
  not independently verified billing.
- V3 completion tokens: **32,502**; v4: **34,562**. Token movement is not a
  quality metric.
- V3 core output/valid/full-valid: **10/10, 2/10, 2/10**. V4:
  **8/10, 7/10, 7/10**. V3 valid-core projection: **2/2**, 9/9 mandatory;
  v4: **7/7**, 73/73 mandatory. These are observed results on different
  stochastic passes, not proof the patch caused improvement or the model learned.

## Status and next decision

Stage 2B foundation: **ACCEPTED**; development baselines v1/v2/v3/v4:
**MEASURED**; semantic-core/projector refactor: **ACCEPTED**; core-v1
validation/scoring hardening: **ACCEPTED**; remaining prompt-contract gaps:
**PATCHED**; public validation: **NOT RUN**; Stage 2C: **NOT STARTED**;
production authority changed: **NO**. Stage 2B is **not complete**.

The targeted structural categories were absent in this pass, so the next
investigation can focus on semantic extraction and malformed JSON while
preserving the core/projector boundary. Repeated, controlled measurements
would be needed before making a causal or general-quality claim.
