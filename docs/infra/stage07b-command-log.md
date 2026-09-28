# Stage 0.7b command log

Date: 2026-09-29. Commands ran in WSL2 from `/mnt/d/code/marlowe_ai_agent`.

## Baseline and environment

```text
$ tools/marlowe_smt/build.sh
ghc: 9.6.7
cabal: 3.10.3.0
z3: Z3 version 4.13.3 - 64 bit
HEAD is now at 7b5b1e9 Bump the version on the cabal level
verified upstream commit 7b5b1e900ec53a8eb18747992bec73470704dfcb; no patches
upstream: 7b5b1e900ec53a8eb18747992bec73470704dfcb
Up to date
binary: /mnt/d/code/marlowe_ai_agent/tools/marlowe_smt/dist-newstyle/build/x86_64-linux/ghc-9.6.7/marlowe-smt-0.2.0.0/x/marlowe-smt/build/marlowe-smt/marlowe-smt

$ uname -a
Linux To-hyung 6.18.33.2-microsoft-standard-WSL2 #1 SMP PREEMPT_DYNAMIC Thu Jun 18 21:54:43 UTC 2026 x86_64 GNU/Linux
$ nproc
16
$ lscpu | grep 'Model name'
Model name: AMD Ryzen 7 8845H w/ Radeon 780M Graphics
$ grep MemTotal /proc/meminfo
MemTotal:        6997668 kB
```

Initial `run_tests.sh` before the new generator had 9 tests and passed. The
post-change test output is recorded below.

## Generator verification

```text
$ python3 -m unittest tests.test_valid_generator -v
test_small_grid_is_deterministic_validated_and_has_expected_status ... ok

----------------------------------------------------------------------
Ran 1 test

OK
```

The 72 sub-configurations cover F1–F5/C1, n=1..3, k=1..2, and both nested
settings. The test validates every generated AST, generates each twice and
compares SHA-256, then checks F1–F5=`Valid` and C1=`Counterexample`.

Two recoverable benchmark-development errors occurred. The first full-grid run
stopped after 100 rows with the final exception text:

```text
RecursionError: maximum recursion depth exceeded
```

`count_cases` was changed to an iterative traversal. The resumed run then
stopped after 249 rows while copying/serializing deeply nested F5, with the same
final exception text:

```text
RecursionError: maximum recursion depth exceeded
```

The generator now raises its recursion limit to 10,000 for deterministic deep
F5 serialization. `--resume` preserved completed CSV rows in both cases. The
complete Python tracebacks were not retained, so they are not claimed here.

## Sequential grid

```text
$ python3 tools/marlowe_smt/bench/run_valid_bench.py --resume
{"resume":true,"existing_rows":249,"median_seconds":0.10564483950000181}
...
{"complete":true,"rows":361,"elapsed_seconds":106.51446733500006}

$ python3 tools/marlowe_smt/bench/run_valid_bench.py --grid 128 --resume
{"resume":true,"existing_rows":361,"median_seconds":0.10564483950000181}
...
{"family":"F3","n":128,"k":1,"nested_if":"false","branches":256,"contract_bytes":198255,"sha256":"8fd38131de4c17b1da0a1fbf2cd6a84d766a2691a36228a3ed26a6e1fba29088","status_1":"Valid","seconds_1":"87.571","tree_rss_kb_1":2741304,"driver_rss_kb_1":1796812,"z3_seen_1":"true","net_seconds_1":"87.465","status_2":"Valid","seconds_2":"85.146","tree_rss_kb_2":2678688,"driver_rss_kb_2":1734292,"z3_seen_2":"true","net_seconds_2":"85.040","status_3":"Valid","seconds_3":"85.631","tree_rss_kb_3":2678904,"driver_rss_kb_3":1734288,"z3_seen_3":"true","net_seconds_3":"85.526"}
{"family":"F3","n":128,"k":2,"nested_if":"false","branches":512,"contract_bytes":389079,"sha256":"3b49019498f0836fcac8b75a9b17f55754e1f05de203ec14838f1e380efd25b2","status_1":"Timeout","seconds_1":"120.169","tree_rss_kb_1":3455788,"driver_rss_kb_1":1829532,"z3_seen_1":"true","net_seconds_1":"120.063","status_2":"Timeout","seconds_2":"120.136","tree_rss_kb_2":3030460,"driver_rss_kb_2":1829536,"z3_seen_2":"true","net_seconds_2":"120.030","status_3":"Timeout","seconds_3":"120.120","tree_rss_kb_3":3540908,"driver_rss_kb_3":1829540,"z3_seen_3":"true","net_seconds_3":"120.014"}
^C
```

The interrupt intentionally ended the optional n=128 extension after the first
all-Timeout point; it did not truncate the required n≤64 grid. The resulting
CSV has 375 rows. Its status set is `Counterexample`, `Timeout`, `Valid`.

## Whole-tree memory cross-check

The first GNU-time invocation used an inline shell variable whose environment
was not initialized correctly. Its complete output was:

```text
/bin/bash: line 1: cabal: command not found
/usr/bin/time: cannot run : No such file or directory
```

The rerun used the already verified absolute driver path:

```text
$ /usr/bin/time -v marlowe-smt --solver-timeout-ms 115000 < bench/results/F3-n32-k1.json
{"analysis_notes":[],"counterexample":null,"meta":{"driver_version":"0.2.0","solver":"Z3 version 4.13.3 - 64 bit","upstream_commit":"7b5b1e900ec53a8eb18747992bec73470704dfcb"},"status":"Valid","warnings":[]}
        Elapsed (wall clock) time (h:mm:ss or m:ss): 0:02.69
        Maximum resident set size (kbytes): 116328
        Exit status: 0
```

For the same payload, tree sampling recorded 203,740–205,676 KiB total,
116,580–116,732 KiB driver RSS, and observed Z3 in all three runs.

## Parallel runs

```text
$ python3 tools/marlowe_smt/bench/run_parallel_valid_bench.py
N=1 batch medians: 62.792, 52.876, 48.754 s; peak 1671804..1671988 KiB; all Valid
N=2 batch medians: 56.793, 50.033, 49.989 s; peak 3338760..3343124 KiB; all Valid
N=4 batch medians: 62.804, 63.752, 64.564 s; peak 6235080..6371660 KiB; all Valid
```

The complete per-job times and statuses are in `parallel-valid-summary.csv`.

## Forced inconclusive states

Full solver output:

```text
$ marlowe-smt --solver-timeout-ms 1000 < bench/results/F3-n64-k4.json
{"analysis_notes":[],"counterexample":null,"meta":{"driver_version":"0.2.0","solver":"Z3 version 4.13.3 - 64 bit","upstream_commit":"7b5b1e900ec53a8eb18747992bec73470704dfcb"},"solver_result":"Unknown.\n  Reason: timeout","status":"Indeterminate","warnings":[]}
```

Full wrapper output:

```text
$ python3 tools/marlowe_smt/run_smt.py --hard-timeout 0.1 --solver-timeout-ms 115000 < bench/results/F3-n64-k4.json
{"status":"Timeout","warnings":[],"counterexample":null,"analysis_notes":[],"meta":{"solver":"z3 (subprocess did not complete)","upstream_commit":"7b5b1e900ec53a8eb18747992bec73470704dfcb","driver_version":"0.2.0"},"error":"hard timeout after 0.1 seconds","process_exit":124}
```

## Corpus and final verification

```text
$ python3 tools/marlowe_smt/bench/select_valid_corpus.py
wrote 15 contracts; corpus size 2092954 bytes

$ tools/marlowe_smt/run_tests.sh
...
Ran 12 tests in 20.266s

OK

$ tools/marlowe_smt/verify_upstream.sh
verified upstream commit 7b5b1e900ec53a8eb18747992bec73470704dfcb; no patches
```

The six fresh audit measurements all returned Valid in all three runs. Median
seconds were: escrow 0.168, loan 0.167, crowdfunding 0.168, three-party escrow
0.168, milestone 0.158, and rental deposit 0.158.
