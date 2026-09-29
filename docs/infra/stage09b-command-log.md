# Stage 0.9b command log: direct bash invocation in renderer tests

Baseline on the Windows host before this patch passed because its `wsl.exe`
launcher was available. Independent acceptance in an environment without that
launcher reported `FileNotFoundError: 'wsl'` in seven renderer tests; that
failure was not reproduced on this Windows host.

```text
PS D:\code\marlowe_ai_agent> python -m pytest marlowe_ai_agent/tests/ -q
........................................................................ [ 51%]
...................................................................      [100%]
139 passed in 21.35s
```

The renderer test now invokes `bash -lc` directly and retains the existing
POSIX path conversion behavior.

Final full-suite run:

```text
PS D:\code\marlowe_ai_agent> pytest marlowe_ai_agent/tests/ -q
........................................................................ [ 51%]
...................................................................      [100%]
139 passed in 14.95s
```

Repository test-tree search:

```text
PS D:\code\marlowe_ai_agent> rg -n -i 'wsl' marlowe_ai_agent/tests/
(no matches; rg exit code 1)
```

No offline replay, LLM/API call, or SMT driver change was made.
