# Live Stage2B Corridor v1

This research experiment has two separate questions. Lane A asks whether a live
model independently produces a core that traverses the proven direct-payment
path. Lane B characterizes Stage2B extraction on the 20 frozen candidate
canonical requirements; it does not run the compiler or reference engine.
The public validation split is not blind ground truth.

No command in this directory calls a provider without `--live`. Before live
use, select the same exact model for both lanes and explicitly declare positive
USD maximum spend and conservative per-physical-request cost ceilings. Prices
are not inferred from model names. The effective physical call cap is the
minimum of the requested cap, lane hard cap, and floor(max spend / ceiling).
Missing provider cost telemetry does not weaken that predeclared cap.
Live preflight requires a clean committed worktree and rejects raw or summary
paths inside the repository. Both files use exclusive creation. Raw JSONL is
flushed and fsynced per completed observation; a sidecar named
`<raw>.summary.json` records execution completeness, usage with null-aware
telemetry, and the SHA-256 of exact raw bytes. Exit 0 means every requested
observation was durably classified, not that the model passed; exit 2 means
configuration/environment/budget blocked completion; exit 3 means a local
experiment invariant failed.

```bash
python -m research.stage2b.report_shadow_run
python -m research.experiments.live_stage2b_corridor --live \
  --model <MODEL> --reference-binary <PINNED_MARLOWE_REFERENCE_BINARY> \
  --max-physical-calls 9 --max-spend-usd <LANE_A_USD> \
  --per-request-cost-ceiling-usd <LANE_A_USD_PER_REQUEST> \
  --output <NEW_LANE_A_JSONL>
python -m research.stage2b.run_shadow --live --all-canonical \
  --model <SAME_MODEL> --max-physical-calls 60 \
  --max-spend-usd <LANE_B_USD> \
  --per-request-cost-ceiling-usd <LANE_B_USD_PER_REQUEST> \
  --output <NEW_LANE_B_JSONL>
python -m research.stage2b.report_shadow_run \
  --input <NEW_LANE_B_JSONL> --lane-a-summary <LANE_A_JSONL.summary.json> \
  --output <NEW_LANE_B_SCORE_JSON>
```

Execution sequence: commit infrastructure; verify a clean tree; choose the
exact model and both monetary budgets; build/locate the pinned reference;
choose a result directory **outside the repo**; run Lane A; without code
changes run Lane B with the same model; verify both summaries have identical
experiment version, code SHA, and model; score Lane B; review and sanitize
results; copy selected artifacts into the repo; create a results-only commit.
The reporter rejects mismatched cross-lane identity or a Lane B raw hash that
does not match its sidecar. No live calls are authorized merely by this README.

Lane A uses a synthetic exact-spec laboratory reviewer probe, not authenticated
human approval. The behavior expectation is fixed independently of model and
compiler output. A real pinned Marlowe reference is required for any canary
that reaches comparison. Authority remains candidate-only. No ledger, testnet,
or deployment executes. An observed corridor pass is not production validation.
