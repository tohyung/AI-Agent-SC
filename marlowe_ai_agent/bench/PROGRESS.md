# Benchmark progress (temporary)

As of 2026-09-25, the 100-case live run has **not** started.

- Dataset v2: 100 validated cases; SHA-256
  `e05c23f43a2bd025258ad5e2fa77569874357f79173e98863a8f8d48ee9a907a`.
- Offline suite: 112 tests passed; F401/F841 lint passed.
- Offline end to end: 95/95 feasible reference contracts converged and scored
  strictly correct. The deliberately doubled-amount variants were marked false
  convergence in 95/95 feasible cases. These are harness checks, **not** agent
  performance measurements.
- Live smoke used dataset v1 (SHA-256
  `bddc66e4223abbdc9278edd8972651448b9752ac4e898533bde2de69bc45226d`),
  model `nvidia/nemotron-3-ultra-550b-a55b:free`, and a diagnostic 60-second
  per-case wall-clock limit. Two of five cases produced records before the run
  was interrupted: both stopped with `wallclock_timeout`, and one judge response
  was invalid JSON. Provider-reported cost was 0 USD. The sample is too small
  and truncated to estimate convergence or accuracy.
- Dataset v2 changed prompt wording after the v1 smoke to correct relative-time
  labeling and improve persona variety. Results across the two versions must
  not be combined.

## Dataset v2 timing probe (n=3; not benchmark rates)

Three complete-information cases ran with 500 iterations, 2000 agent-call
budget, 5400 seconds per case, and three workers. The judge was not called:
it is not part of agent convergence time. `llm_calls` below includes simulated
user requests; agent calls are listed separately.

- L1 escrow: `en-escrow_2party-L1-010` reached `done/ok` in 2 iterations,
  7 total LLM calls (3 agent), 331.1 wall seconds; evaluator score 1.0.
- L3 rental deposit: `vi-rental_deposit-L3-003` reached `done/ok` in 1
  iteration, 2 agent calls, 375.4 wall seconds; evaluator score 0.4 and
  `false_convergence=true`.
- L4 milestone: `vi-milestone-L4-003` reached `done/ok` in 5 iterations,
  17 total LLM calls (13 agent), 2065.3 wall seconds; evaluator score 0.4 and
  `false_convergence=true`.

Provider-reported cost was 0 USD for these `:free` model runs. These three
selected cases cannot estimate population convergence or accuracy. The raw run
directory remains ignored; complete copies of the three case records for
audit are tracked in [bench/audit](audit/README.md).

Live raw results and transcripts remain local under ignored `bench/results/`.
The next gate for a 100-case accuracy benchmark remains a successful smoke on
v2 with stable judge responses and observable usage, under the 50 USD ceiling.
