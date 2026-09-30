# Stage 1.0 command log

Baseline: `git rev-parse HEAD` -> `5281f063e621a24887de9c198522451c06cfda1c`;
`git status --short` -> clean.

## Commit 1: isolated lint and adapter

`python -m pytest marlowe_ai_agent/tests/test_logic_graph.py marlowe_ai_agent/tests/test_node3_policy.py marlowe_ai_agent/tests/test_node3_smt.py -q`
-> `49 passed in 0.15s`.

`python -m pytest marlowe_ai_agent/tests/ -q`
-> `184 passed in 17.24s`.

`uvx ruff check --select F401,F841` -> `All checks passed!`.

Commit: `febc31b refactor(agent): isolate deterministic node3 lints and production smt backend`.

## Commit 2: live integration

`python -m pytest marlowe_ai_agent/tests/test_pipeline.py -q`
-> `82 passed in 0.24s` after adding retry, stall, and serialization tests.

`wsl bash -lc 'cd /mnt/d/code/marlowe_ai_agent && tools/marlowe_smt/run_tests.sh'`
-> GHC 9.6.7, cabal 3.10.3.0, Z3 4.13.3; `Ran 12 tests in 20.589s`, `OK`.

`wsl bash -lc 'cd /mnt/d/code/marlowe_ai_agent && tools/marlowe_smt/verify_upstream.sh'`
-> `verified upstream commit 7b5b1e900ec53a8eb18747992bec73470704dfcb; no patches`.

Real acceptance command used `wsl --cd /mnt/d/code/marlowe_ai_agent -e env`
with `PYTHONPATH=marlowe_ai_agent`, `MARLOWE_SMT_BIN` set to the binary path
printed by `run_tests.sh`, and `python3 -c` to instantiate
`Node3VerificationNode`. Output:

```json
{"good": ["pass", "valid", []], "bad": ["fail", "counterexample", ["Tài khoản Alice cố trả 10 cho bên Bob nhưng chỉ trả được 0."]], "critical": [false, true, "pass", "valid", []]}
```

The first direct WSL attempt without `MARLOWE_SMT_BIN` returned
`unavailable`/`SMT wrapper không trả JSON` because `cabal` was absent from the
non-login process PATH; no production code was changed to accommodate that
environment-specific PATH.

Minimal real SMT pipeline command used the same WSL environment and
`AgentPipeline(FakeReasoner([draft]), max_iterations=2)`; output:

```json
{"status": "done", "stop_reason": "ok", "node3_status": "valid", "backend": "marlowe-smt", "iterations": 1}
```

Replay command from project directory:

`wsl --cd /mnt/d/code/marlowe_ai_agent/marlowe_ai_agent -e env MARLOWE_SMT_BIN=<built binary> python3 -m bench.node3_replay`

Summary: `both_correct=7`, `both_wrong=0`, `old_only_correct=0`,
`new_only_correct=0`; 3 ground-truth-unavailable rows, 2 persisted-truth drift
rows. The pre-replay CSV was copied to `%TEMP%` with `Copy-Item`; a Python
`csv.DictReader` row/key comparison excluding `smt_seconds` returned
`old_rows=10`, `new_rows=10`, `semantic_diff=[]`.

`python -m pytest marlowe_ai_agent/tests/ -q`
-> `196 passed in 14.87s` before the final CLI trace-only test.

`uvx ruff check --select F401,F841` -> `All checks passed!`.

No OpenRouter, LLM API, dataset, evaluator, audit, or SMT source files were
changed or called for paid inference. Final regression follows below.

`python -m pytest marlowe_ai_agent/tests/test_pipeline.py marlowe_ai_agent/tests/test_node3_trace_compat.py marlowe_ai_agent/tests/test_node3_replay.py marlowe_ai_agent/tests/test_node3_wired.py marlowe_ai_agent/tests/test_logic_graph.py marlowe_ai_agent/tests/test_node3_policy.py marlowe_ai_agent/tests/test_node3_smt.py -q`
-> `151 passed in 0.52s`.

`python -m pytest marlowe_ai_agent/tests/ -q`
-> `197 passed in 16.15s`.

`uvx ruff check --select F401,F841` -> `All checks passed!`.

## Finalization — verified SMT counterexample paths

`git rev-parse HEAD` -> `7fae83bc9adde862ec80825d36e211858ac04a88`;
`git status --short` -> clean before edits.

`python -m pytest marlowe_ai_agent/tests/test_node3_mapper.py marlowe_ai_agent/tests/test_node3_policy.py marlowe_ai_agent/tests/test_node3_renderer.py marlowe_ai_agent/tests/test_pipeline.py marlowe_ai_agent/tests/test_node3_trace_compat.py marlowe_ai_agent/tests/test_node3_wired.py -q`
-> `140 passed in 16.78s`. This includes whole-warning-sequence equivalence,
no fabricated path, mapper exception, and lint-once/SMT-twice tests.

Real mapper acceptance used `wsl --cd /mnt/d/code/marlowe_ai_agent -e env`
with `MARLOWE_SMT_BIN` set to the built binary, `PYTHONPATH=marlowe_ai_agent`,
and `python3 -c` invoking `Node3VerificationNode().run()` for each fixture.
All five returned `counterexample`/fail with every finding `verified`:

```text
partial_pay.json         root.when[0].then.pay
nonpositive_pay.json     root.pay
nonpositive_deposit.json root.when[0].case.deposits
shadowing.json           root.then.let
assertion_failed.json    root.assert
```

The same real-driver command on
`tools/marlowe_smt/compare/corpus/hand-written/04-symbolic-partial-pay.json`
returned `counterexample`/fail and verified
`TransactionPartialPay` at `root.when[0].then.when[0].then.pay`.

Minimal real-SMT repair-loop acceptance used `AgentPipeline` with
`FakeReasoner`, a real partial-pay fixture followed by a fixed escrow draft,
and a captured logic-feedback call. Output: `done/ok`, 2 iterations, 2 Node 2
semantic calls, verified `root.when[0].then.pay` in the finding and rendered
error, and the same path in the regenerated draft prompt. No paid LLM/API call.

`python -m tools.regen_sample` from `marlowe_ai_agent/` regenerated
`marlowe_ai_agent/sample_result.json` using the existing deterministic tool.

`wsl bash -lc 'cd /mnt/d/code/marlowe_ai_agent && tools/marlowe_smt/run_tests.sh'`
-> `Ran 12 tests in 25.381s`, `OK`.

`wsl bash -lc 'cd /mnt/d/code/marlowe_ai_agent && tools/marlowe_smt/verify_upstream.sh'`
-> `verified upstream commit 7b5b1e900ec53a8eb18747992bec73470704dfcb; no patches`.

`wsl --cd /mnt/d/code/marlowe_ai_agent/marlowe_ai_agent -e env MARLOWE_SMT_BIN=<built binary> python3 -m bench.node3_replay --output /tmp/stage10-final-replay.csv`
-> `both_correct=7`, `ground_truth_unavailable=3`, no new disagreement.
The CSV output was outside the tracked repository because the schema and
semantic results did not change; `smt_seconds` remains volatile telemetry.

`python -m pytest marlowe_ai_agent/tests/ -q` -> `227 passed in 15.34s`.

`uvx ruff check --select F401,F841` -> `All checks passed!`.

No `tools/marlowe_smt/**` source, evaluator, dataset, or audit file was edited.

Final pre-commit regression after documentation updates:

`python -m pytest marlowe_ai_agent/tests/test_node3_mapper.py marlowe_ai_agent/tests/test_node3_policy.py marlowe_ai_agent/tests/test_node3_renderer.py marlowe_ai_agent/tests/test_pipeline.py marlowe_ai_agent/tests/test_node3_trace_compat.py marlowe_ai_agent/tests/test_node3_wired.py -q`
-> `140 passed in 19.34s`.

`python -m pytest marlowe_ai_agent/tests/ -q` -> `227 passed in 15.21s`.

`uvx ruff check --select F401,F841` -> `All checks passed!`.
