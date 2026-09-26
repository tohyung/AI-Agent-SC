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

## Dataset v2 high-difficulty timing probe (n=5; not benchmark rates)

On 2026-09-26, five selected L3-L4 cases ran from commit `2100631` with 500
iterations, 2000 agent-call budget, 5400 seconds per case, and three workers.
The judge was not called. Raw results remain local under
`bench/results/20260926-105406-nvidia-nemotron-3-ultra-550b-a55b-free/`; full
audit copies are tracked in [bench/audit](audit/README.md).

| Case | Type / level / mode | Result | Iterations | Agent + user calls | Wall seconds | Evaluator |
|---|---|---:|---:|---:|---:|---:|
| `vi-escrow_3party-L4-006` | escrow_3party / L4 / complete | `done/ok` | 5 | 10 + 3 | 655.0 | 1.0, strict, fallback scenarios 2 |
| `vi-swap-L3-010` | swap / L3 / complete | `blocked/llm_error` | 9 | 14 + 12 | 622.7 | last draft 1.0, strict |
| `en-loan-L4-007` | loan / L4 / missing | `done/ok` | 3 | 5 + 6 | 251.6 | 1.0, strict |
| `vi-crowdfunding-L4-004` | crowdfunding / L4 / ambiguous | `done/ok` | 2 | 3 + 4 | 317.3 | 1.0, strict |
| `vi-cancellation_fee-L4-001` | cancellation_fee / L4 / complete | `blocked/harness_error` | 1 partial | 1 + 1 | 79.0 | no contract |

The loan agent asked six questions. Its first question directly recovered the
missing principal (164 ADA), while five follow-ups about on-chain loan flow and
default handling were broader than the single missing fact and mostly received
the simulated user's simplest-option fallback. It nevertheless converged to a
strictly correct contract. The crowdfunding agent asked four questions: the
first directly resolved the 176-versus-177 ADA conflict, and the remaining
questions clarified contribution order, deadline timezone, and partial
deposits. Those questions were relevant and the resulting contract was
strictly correct, although only the first was essential to the seeded
ambiguity.

Short iteration paths were: escrow `skip -> structural fail -> structural+
semantic pass / logic fail -> structural fail -> all pass`; swap `structural
fail -> semantic fail -> repeated clarification/regeneration -> structural
pass -> llm_error`; loan `clarification -> semantic fail -> all pass`;
crowdfunding `clarification -> all pass`; cancellation fee `clarification ->
provider rate-limit error`.

The independent evaluator reported no false convergence for any available
draft. After the choice-name evaluator fix, the earlier three-case audit also
re-evaluates without regression: escrow remains strict at 1.0, while rental
deposit and milestone improve from 0.4 to 1.0 and each reports two fallback
scenarios. In this new probe, three cases converged strictly; swap's last draft
was strict but the pipeline ended in `llm_error`, and cancellation fee produced
no contract because OpenRouter returned an explicit HTTP 429 free-tier daily
limit. These eight selected cases remain too small and non-random to estimate
100-case convergence or accuracy.

### Retry of the two provider-failed cases

`vi-swap-L3-010` and `vi-cancellation_fee-L4-001` were retried together from
commit `adc4636` at approximately 04:35:03 UTC on 2026-09-26, using the same
500-iteration, 2000-call, and 5400-second per-case limits. Both stopped during
the first partial iteration after three agent attempts: swap took 7.8 seconds
and cancellation fee took 7.9 seconds. Each trace records OpenRouter HTTP 429,
daily free-model quota remaining `0`, and a reset timestamp of 2026-09-27
00:00 UTC (07:00 Asia/Bangkok).

This retry strengthens the diagnosis that the two stops were caused by an
external provider quota, not by the configured wall-clock or iteration limits.
Because neither retry produced an evaluable contract, they add no evidence for
or against convergence, accuracy, or false convergence. Complete retry records
are published separately in [bench/audit](audit/README.md); the original audit
records remain unchanged.
