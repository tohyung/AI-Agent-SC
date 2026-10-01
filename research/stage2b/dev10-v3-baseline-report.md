# Stage 2B development shadow baseline v3

This is the observed result of **one exploratory development pass** against
frozen Stage 2A candidate annotations. It is not human-reviewed ground truth,
model accuracy, or evidence of general improvement. The architecture and prompt
changed between v2 and v3, so raw validator-message counts are not comparable.
No source/prompt tuning, failed-case rerun, public validation, or production
authority change occurred during this measurement.

## Precheck and run integrity

- Source HEAD: `16b45a7c7011689b95e4e64d448cc740753a175a`.
- Stage 2A freeze verified; aggregate SHA-256:
  `897249E3D355121E7CF8304E8B336DC0A4118515B4BF847F7FB8B8EFAD587A46`.
- Pre-run Stage 2B tests: **87 passed**.
- Split: `development`, 10 canonical cases, no mutations.
- Dry-run: 10 unique records, all `dry_run`, core schema
  `stage2b-shadow-core-v1`; the user prompt did not contain the rich output
  schema.
- Live command: `python research/stage2b/run_shadow.py --live --split
  development --model nvidia/nemotron-3-ultra-550b-a55b:free --output
  runs/stage2b/dev10-v3-live.jsonl`.
- One live pass: 10 records; `ok=2`, `core_invalid=8`, `model_error=0`.
- Sum of per-case provider usage: **10 calls**, 15,252 prompt tokens, 32,502
  completion tokens, 1,072.354 request-latency seconds, provider-reported
  cost **0**. Cost is not an independently verified billing amount.
- Local gitignored artifact SHA-256:
  - `runs/stage2b/dev10-v3-dry.jsonl`:
    `53DC63281536DDC78E2F4D54547A6882BC7C118547815866CB9D3CB180564CBC`
  - `runs/stage2b/dev10-v3-live.jsonl`:
    `3059851430CD1973A9F7025C2E05D937E65869EDB5FDFEAE9669E06AD94C57B0`
  - `runs/stage2b/dev10-v3-score.json`:
    `0CCF75B332F32540C882616FEA98C9B431A71C69115D0176DD58AEDD7CF8E853`

## Exploratory metrics

| Metric | Observed result |
| --- | ---: |
| Core output rate | 10/10 |
| Core structural validity | 2/10 |
| Full structural validity | 2/10 |
| Projection completeness on eligible valid-core facts | 9/9 |
| Critical claim precision | 23/61 |
| Critical claim recall | 5/15 |
| Provenance completeness | 59/61 |
| Resolution exact match | 5/10 |
| Conflict classification recall | 1/1 |
| Required clarification recall | 7/8 |
| Unnecessary clarification rate | 2/2 |
| Unsafe freeze rate | 0/8 |
| Unsafe assumption rate | N/A (0/0) |
| Unsafe acceptance rate | N/A (0/0) |

Core output counts any JSON object. `refund-d1` returned `{}`, so 10/10 output
does **not** mean 10 usable cores. Critical claim recall's denominator follows
the scorer's accepted-candidate policy. The two zero-denominator rates are
unavailable, not zero-risk evidence. Projection completeness covers only the
two valid cores; it says nothing about projection from the eight invalid ones.

## Per-case audit

`M/FP/Missed` counts exact critical-claim matches, false positives, and misses
under the scorer key. The score JSON contains the corresponding claim keys and
raw validator messages. Resolution is `predicted -> candidate`.

| Case | Run/projection classification | Core errors | Full errors | Resolution | M/FP/Missed |
| --- | --- | ---: | ---: | --- | ---: |
| `pay-d1` | core_invalid / CORE_INVALID | 1 | 13 | clarification -> accepted | 3/5/3 |
| `refund-d1` | core_invalid / CORE_INVALID | 9 | 7 | null -> clarification | 0/0/6 |
| `choice-d1` | core_invalid / CORE_INVALID | 3 | 18 | clarification -> clarification | 4/6/4 |
| `escrow-d1` | core_invalid / CORE_INVALID | 4 | 19 | clarification -> clarification | 5/3/3 |
| `double-d1` | core_invalid / CORE_INVALID | 3 | 16 | clarification -> accepted | 2/6/7 |
| `conditional-d1` | core_invalid / CORE_INVALID | 3 | 19 | clarification -> clarification | 4/5/3 |
| `choice-d2-correction` | ok / PASS | 0 | 0 | conflict -> clarification | 0/3/4 |
| `pay-d2-clarify` | core_invalid / CORE_INVALID | 2 | 8 | clarification -> clarification | 2/2/1 |
| `escrow-d2-clarify` | core_invalid / CORE_INVALID | 1 | 13 | conflict -> clarification | 3/5/3 |
| `double-d2-conflict` | ok / PASS | 0 | 0 | conflict -> conflict | 0/3/2 |

Both `PASS` labels mean structural/projection success only. One has the wrong
candidate resolution, and both have low exact critical-claim overlap. Full
structural validity is therefore not an intent-quality measure.

## Error attribution and comparison

There were 26 core-validator messages across eight invalid cores, including
nine cascading messages caused by the empty `refund-d1` object. The dominant
pattern is scope/`decision_id` reference failure (11 categorized messages),
followed by malformed unscored observations, invalid `derived_from` links,
and one malformed clarification. The category counts in local score JSON are
coarse diagnostics, not independent root-cause counts. **No projection error
was observed on a valid core**; full errors on invalid cores are not classified
as projector bugs.

For context only: v2 had native core metrics **N/A**, full structural validity
**0/10**, 82 historical validator messages, and 70,485 completion tokens.
V3 used 32,502 completion tokens. The 82 messages are not a v3 denominator,
and lower token usage alone is not a quality result.

The three v3 artifacts remain local and gitignored. Their hashes make the
record identifiable but do not make the raw JSONL or detailed score available
to a repo-only reviewer. This report contains the aggregate and per-case
findings without committing raw model output.

Status: Stage 2B foundation, semantic-core/projector refactor, and core-v1
hardening accepted at source level; development baselines v1/v2/v3 measured;
public validation not run; Stage 2C not started; production authority unchanged.
Stage 2B is **not** declared complete.
