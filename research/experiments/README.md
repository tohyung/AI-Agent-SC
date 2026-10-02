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
  --input <NEW_LANE_B_JSONL> --output <NEW_LANE_B_SCORE_JSON>
```

Lane A uses a synthetic exact-spec laboratory reviewer probe, not authenticated
human approval. The behavior expectation is fixed independently of model and
compiler output. A real pinned Marlowe reference is required for any canary
that reaches comparison. Authority remains candidate-only. No ledger, testnet,
or deployment executes. An observed corridor pass is not production validation.
