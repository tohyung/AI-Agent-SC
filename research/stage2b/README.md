# Stage 2B IntentSpec shadow foundation

Stage 2B is research-only shadow extraction and evaluation. The current
production path remains prompt -> ContractDraft/Marlowe generation -> semantic
verification -> Node 3. In parallel, Stage 2B runs requirement history ->
IntentSpec shadow -> deterministic validation -> exploratory comparison with
`stage2a-v1`. No Stage 2B output changes a production result or freezes intent.
There is no Marlowe compiler or Node 3 call in this stage.

The source is the frozen **candidate** corpus. Its 32 annotations remain
`draft`; 20 canonical cases are independent intent observations and 12
mutations are excluded from default intent scoring. Development canonical
cases are the default. Public validation requires an explicit selection and
is not a blind test set.

These numbers measure agreement with frozen candidate annotations. They are
not accuracy estimates against human-reviewed ground truth. Quality metrics
in the Stage 2A protocol require human-reviewed, frozen cases. The exploratory
scorer uses exact kind, normalized value, scope ID and active evidence version;
it has no fuzzy or model judge. Exploratory scoring retains invalid predictions,
reports per-case `validation_errors`, and includes a structural-validity rate;
`strict_validation=True` is reserved for CI or direct validation checks.
Zero denominators return `null`. Missing predictions remain in candidate-based
recall denominators rather than silently disappearing. Its unsafe
freeze rate is a simulated decision over candidate clarification/conflict
cases; unsafe acceptance rate is a separate metric over model-predicted
accepted cases. Timestamps are run metadata, not scoring inputs.
Required clarification recall measures whether a clarification/conflict case
was held for user resolution; generic clarification on a conflict case counts
as held. The separate exploratory resolution exact-match and conflict
classification recall metrics measure label agreement. A resolution prediction
can match by chance even when the IntentSpec is structurally invalid.
Resolution diagnostics must therefore be interpreted together with structural
validity, not as independent evidence of intent correctness.

From the repository root:

```bash
python research/stage2b/run_shadow.py --dry-run --case-id pay-d1
python research/stage2b/run_shadow.py --dry-run --split validation --output /tmp/stage2b-prompts.jsonl
python research/stage2b/run_shadow.py --live --case-id pay-d1 --output /tmp/stage2b-live.jsonl
```

Dry-run is the default and never calls a model. Live mode is explicit and
requires an output path and the existing LLM configuration. `LegacyReasonerTransport`
uses the production reasoner's private JSON transport only as a research
adapter; it is not production authority, does not request a Marlowe AST, and
does not import `ContractDraft`. Tests use fake transports and make no API
calls. Output paths are caller-selected; live outputs are not committed by
default.
The shadow prompt embeds the validator's closed enum and field vocabulary;
unknown business facts stay unresolved rather than becoming guessed claims or
rich projections. With `--output`, prechecks finish before the file is opened.
Each completed case record is appended and flushed before the next case.
Expected model failures produce a sanitized `model_error` record and the run
continues; the command exits non-zero after all selected cases if any such
failure occurred. Usage in each record is the delta for that case, including
failed cases where the transport observed a request; aggregate usage sums the
per-case deltas. Flushing protects completed records at the process/filesystem
boundary, not against power loss, OS crashes, or disk corruption.

`unscored_observations` hold source-grounded facts outside the frozen claim
taxonomy. They cannot authorize rich IntentSpec fields, count as matched
claims, or be used by a future compiler without a versioned schema change.
Assumptions never become evidence merely by quoting a suggestive span.
Rich objects are closed-schema projections of scoped claims: unknown fields and
unsupported state/outcome kinds are rejected. Financial derivations use exact
source spans plus a normalization basis; `derived_from` is optional and cannot
point from an amount to an `asset=ADA` claim as a substitute for quantity.
