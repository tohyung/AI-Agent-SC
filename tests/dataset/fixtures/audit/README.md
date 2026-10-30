# Three-case timing probe audit

These are complete, pretty-printed copies of the three records in the local
`bench/results/20260925-103853-nvidia-nemotron-3-ultra-550b-a55b-free/runs.jsonl`.
They include `iteration_history`, `semantic_history`, every recorded trace
event, simulated-user Q&A, per-request usage/latency, draft, contract, and
independent evaluation. The records do not include raw model chain-of-thought
or full provider response bodies.

- [L1 escrow, English](en-escrow_2party-L1-010-full.json): 2 iterations,
  `done/ok`, 331.1 seconds, 7 total LLM requests (3 agent requests).
- [L3 rental deposit, Vietnamese](vi-rental_deposit-L3-003-full.json):
  1 iteration, `done/ok`, 375.4 seconds, 2 agent requests; independent
  evaluator flagged false convergence.
- [L4 milestone, Vietnamese](vi-milestone-L4-003-full.json):
  5 iterations, `done/ok`, 2065.3 seconds, 17 total LLM requests
  (13 agent requests); independent evaluator flagged false convergence.

All three started within one millisecond at approximately 03:38:53 UTC on
2026-09-25, using three workers. The elapsed time for the entire probe was
therefore approximately 2065 seconds, not the sum of the three case durations.
This is a selected timing diagnostic (n=3), not a 100-case benchmark estimate.

The dataset SHA-256 is
`e05c23f43a2bd025258ad5e2fa77569874357f79173e98863a8f8d48ee9a907a`.
The `git_commit` field inside the run records captures `a7cd9c6`, which was
HEAD during execution; the timing-probe code was still uncommitted then and
was committed immediately afterward as `5753306`. Both facts are needed when
interpreting provenance.

## Five-case high-difficulty timing probe

These are complete, pretty-printed copies of the five records in the local
`bench/results/20260926-105406-nvidia-nemotron-3-ultra-550b-a55b-free/runs.jsonl`.
As above, they retain the full recorded prompt, Q&A transcript, histories,
trace, draft, contract, independent evaluation, request usage, and timing.

- [L4 three-party escrow, Vietnamese](vi-escrow_3party-L4-006-full.json):
  5 iterations, `done/ok`, 655.0 seconds, 13 total LLM requests (10 agent
  requests), evaluator score 1.0 with two scenarios using choice-name fallback.
- [L3 swap, Vietnamese](vi-swap-L3-010-full.json): 9 iterations,
  `blocked/llm_error`, 622.7 seconds, 26 total LLM requests (14 agent requests).
  The last available draft independently scores 1.0, but the run did not
  converge and is not counted as a successful contract.
- [L4 loan, English, missing information](en-loan-L4-007-full.json):
  3 iterations, `done/ok`, 251.6 seconds, 11 total LLM requests (5 agent
  requests), evaluator score 1.0.
- [L4 crowdfunding, Vietnamese, ambiguous information](vi-crowdfunding-L4-004-full.json):
  2 iterations, `done/ok`, 317.3 seconds, 7 total LLM requests (3 agent
  requests), evaluator score 1.0.
- [L4 cancellation fee, Vietnamese](vi-cancellation_fee-L4-001-full.json):
  1 partial iteration, `blocked/harness_error`, 79.0 seconds, 2 total LLM
  requests (1 agent request). The simulated-user request received an explicit
  OpenRouter free-tier daily-rate-limit response, so no contract was available
  for evaluation.

All five started from the same timing probe at approximately 03:54:06 UTC on
2026-09-26, using three workers. The probe used commit `2100631`, dataset
SHA-256 `e05c23f43a2bd025258ad5e2fa77569874357f79173e98863a8f8d48ee9a907a`,
and model `nvidia/nemotron-3-ultra-550b-a55b:free`. Secret-pattern checks found
no API key, bearer token, or key assignment in any of the five published
records. This selected probe is diagnostic evidence only, not a population
estimate.

## Retry after the five-case probe

The two provider-failed cases were retried from commit `adc4636` in a separate
two-worker timing probe at approximately 04:35:03 UTC on 2026-09-26. The raw
retry directory remains local at
`bench/results/20260926-113503-nvidia-nemotron-3-ultra-550b-a55b-free/`.

- [L3 swap retry](vi-swap-L3-010-retry-full.json): one partial iteration,
  `blocked/llm_error`, 3 agent requests, 7.8 seconds, and no independent
  evaluation.
- [L4 cancellation-fee retry](vi-cancellation_fee-L4-001-retry-full.json):
  one partial iteration, `blocked/llm_error`, 3 agent requests, 7.9 seconds,
  and no independent evaluation.

Both pipelines retried draft generation three times. Every request received
OpenRouter HTTP 429 with `X-RateLimit-Remaining: 0` from the daily free-model
quota. The response advertised a reset at 2026-09-27 00:00 UTC (07:00 in
Asia/Bangkok). These records confirm an external provider limit rather than an
agent convergence failure; they do not provide new contract-quality evidence.
Secret-pattern checks found no API key, bearer token, or key assignment in
either retry record.
