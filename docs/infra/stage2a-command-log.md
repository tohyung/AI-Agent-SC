# Stage 2A command log

Run from `D:\code\marlowe_ai_agent` unless noted. No LLM or deployment command
was run. Commands below record the actual environment and outcomes; `wsl`
provided the Haskell/Cabal toolchain. The pre-existing untracked
`AI-Agent-SC-72283469.zip` was not touched.

## Baseline

```text
git rev-parse HEAD
63b94828aad56c27b28b57adc11ed75fdce2c994

git status --short
?? AI-Agent-SC-72283469.zip

git log --oneline -8
63b9482 test(agent): separate renderer unit tests from real smt integration
7228346 fix(agent): map smt counterexamples to verified ast paths
7fae83b feat(agent): wire smt-backed node3 into live pipeline
febc31b refactor(agent): isolate deterministic node3 lints and production smt backend
5281f06 fix(bench): classify node3 replay disagreement by correctness, not pass
889a4d7 fix(bench): recompute node3 replay ground truth with current evaluator
c9954f2 fix(tests): call bash directly instead of wrapping with wsl.exe
ad0ae98 docs(infra): assess Node3 policy offline replay
```

The worktree was not strictly clean because of that unrelated ZIP; baseline
HEAD matched. No prior commit was amended or rewritten.

## Reference build and execution

```text
wsl --cd /mnt/d/code/marlowe_ai_agent/tools/marlowe_smt -e bash -lc 'cabal build exe:marlowe-reference'
exit 0; built marlowe-reference with GHC 9.6.7

wsl --cd /mnt/d/code/marlowe_ai_agent/tools/marlowe_smt -e bash -lc 'python3 -m unittest tests/test_reference.py -v'
Ran 17 tests in 2.651s
OK
```

The representative wrapper commands piped explicit JSON requests into
`wsl --cd /mnt/d/code/marlowe_ai_agent/tools/marlowe_smt -e bash -lc 'python3 run_reference.py'`.
All used `state={accounts,choices,boundValues,minTime}` and the pinned upstream
SHA in output. Observed:

```text
funded Close: Success, one 10-unit refund to Alice, final accounts []
Pay 4 to Bob from Alice's 10: Success, Bob 4 and Alice Close refund 6
When timeout 100, interval [99,99] + Notify: Success, minTime 99
When timeout 100, interval [100,100] + []: Success, timeout continuation, minTime 100
When timeout 100, interval [99,100] + []: TransactionError at index 0,
  TEAmbiguousTimeIntervalError, initial state/contract retained
```

Direct `wsl -e python3 run_reference.py` without a login shell first returned
`Unavailable` because `cabal` was not on that process's PATH. The documented
WSL `bash -lc` invocation and `MARLOWE_REFERENCE_BIN`/`--binary` override avoid
that environment issue. This did not require modifying the upstream pin.

## Final verification

```text
wsl --cd /mnt/d/code/marlowe_ai_agent -e bash -lc 'tools/marlowe_smt/verify_upstream.sh'
verified upstream commit 7b5b1e900ec53a8eb18747992bec73470704dfcb; no patches
exit 0

wsl --cd /mnt/d/code/marlowe_ai_agent -e bash -lc 'tools/marlowe_smt/run_tests.sh'
Ran 29 tests in 23.140s
OK
exit 0

python research/stage2a/foundation.py validate
VALID: 32 draft candidate cases
exit 0

python research/stage2a/foundation.py stats
total_candidate_cases: 32; development: 16; evaluation: 16; draft: 32
clarification_cases: 3; conflict_cases: 3; supported_explicit_cases: 13
exit 0

python research/stage2a/foundation.py review --output research/stage2a/review_queue.md
generated 32 per-case review entries
exit 0

python -m pytest research/stage2a/test_foundation.py -q
15 passed in 0.07s
exit 0

python -m pytest marlowe_ai_agent/tests/ -q
228 passed, 7 skipped in 1.28s
exit 0

uvx ruff check --select F401,F841
All checks passed!
exit 0
```

The literal `ruff check --select F401,F841` and `python -m ruff ...` commands
were unavailable in the Windows Python environment. `uvx ruff ...` ran the
requested check successfully. WSL system Python lacked pytest; the full Python
suite was run with Windows Python according to its existing skip policy.

No production files, benchmark dataset, upstream semantics files, or deployment
files were changed. LLM/API calls: **0**. The candidate review queue remains
unapproved.
