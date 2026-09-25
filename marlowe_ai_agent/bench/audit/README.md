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
