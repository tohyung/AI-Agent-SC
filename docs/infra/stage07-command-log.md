# Stage 0.7 command log

Date: 2026-09-28 to 2026-09-29. Repository commands ran from
`D:\code\marlowe_ai_agent`; Linux build and measurement commands ran in WSL2
Ubuntu. Temporary upstream and Route A trees were outside Git.

## Initial state and commits

```text
$ git status --short --branch
## main...origin/main

$ git log --oneline -4
6c2ee95 docs(infra): verify standalone Marlowe SMT analysis
0d652aa docs(infra): correct marlowe-cli run analyze scope
...
```

The implementation was split as required:

```text
31b301f feat(tools): package standalone Marlowe SMT driver
20b64a0 test(tools): add Marlowe SMT golden coverage
fab6fa0 test(tools): benchmark Marlowe SMT limits
```

No path under `marlowe_ai_agent/` changed:

```text
$ git diff --name-only 6c2ee95..fab6fa0 -- marlowe_ai_agent
<no output>
```

## Clean-clone build — complete output

```text
$ git clone --no-local /mnt/d/code/marlowe_ai_agent /home/tohung/stage07-clean-final
$ cd /home/tohung/stage07-clean-final
$ git checkout 31b301f
$ cd tools/marlowe_smt
$ ./build.sh
Cloning into '/home/tohung/stage07-clean-final'...
HEAD is now at 31b301f feat(tools): package standalone Marlowe SMT driver
ghc: 9.6.7
cabal: 3.10.3.0
z3: Z3 version 4.13.3 - 64 bit
Initialized empty Git repository in /home/tohung/stage07-clean-final/tools/marlowe_smt/upstream/marlowe/.git/
From https://github.com/marlowe-lang/marlowe
 * branch            7b5b1e900ec53a8eb18747992bec73470704dfcb -> FETCH_HEAD
HEAD is now at 7b5b1e9 Bump the version on the cabal level
b663716be5c2d1cb21b411618e8a2c79eb0d2f0279c8263518c4a31c72353882  haskell/src/Language/Marlowe/Pretty.hs
12786d80df093802718217e94113b6eeeaf13632fe2f7f187f0af78c6b370d9f  haskell/src/Language/Marlowe/Deserialisation.hs
1030f782c96abec65e922c5aef6c4d575bd2608f4f7f74202c15a3376df8af35  haskell/src/Language/Marlowe/Semantics.hs
d5f64dcf8bd34207640ce93f7d423d47bf687af19044d6c4cea05781379ddc19  haskell/src/Language/Marlowe/Semantics/Deserialisation.hs
98452fb0cb78a37c53f25d2cc647af9ad81611fce0dd33e9e70b9823b82fdb14  haskell/src/Language/Marlowe/Semantics/Types.hs
628532d2258d1bfcb71ebc393e04c4629fb852b39343350fe54ddf15406d1318  haskell/src/Language/Marlowe/Analysis/FSSemanticsFastVerbose.hs
verified upstream commit 7b5b1e900ec53a8eb18747992bec73470704dfcb; no patches
upstream: 7b5b1e900ec53a8eb18747992bec73470704dfcb
Resolving dependencies...
Build profile: -w ghc-9.6.7 -O1
In order, the following will be built (use -v for more details):
 - marlowe-smt-0.2.0.0 (exe:marlowe-smt) (first run)
Configuring executable 'marlowe-smt' for marlowe-smt-0.2.0.0..
Preprocessing executable 'marlowe-smt' for marlowe-smt-0.2.0.0..
Building executable 'marlowe-smt' for marlowe-smt-0.2.0.0..
[ 1 of 10] Compiling Language.Marlowe.Deserialisation ( upstream/marlowe/haskell/src/Language/Marlowe/Deserialisation.hs, /home/tohung/stage07-clean-final/tools/marlowe_smt/dist-newstyle/build/x86_64-linux/ghc-9.6.7/marlowe-smt-0.2.0.0/x/marlowe-smt/build/marlowe-smt/marlowe-smt-tmp/Language/Marlowe/Deserialisation.o )
[ 2 of 10] Compiling Language.Marlowe.Pretty ( upstream/marlowe/haskell/src/Language/Marlowe/Pretty.hs, /home/tohung/stage07-clean-final/tools/marlowe_smt/dist-newstyle/build/x86_64-linux/ghc-9.6.7/marlowe-smt-0.2.0.0/x/marlowe-smt/build/marlowe-smt/marlowe-smt-tmp/Language/Marlowe/Pretty.o )
[ 3 of 10] Compiling Language.Marlowe.Semantics.Types ( upstream/marlowe/haskell/src/Language/Marlowe/Semantics/Types.hs, /home/tohung/stage07-clean-final/tools/marlowe_smt/dist-newstyle/build/x86_64-linux/ghc-9.6.7/marlowe-smt-0.2.0.0/x/marlowe-smt/build/marlowe-smt/marlowe-smt-tmp/Language/Marlowe/Semantics/Types.o )
[ 4 of 10] Compiling Language.Marlowe.Semantics.Deserialisation ( upstream/marlowe/haskell/src/Language/Marlowe/Semantics/Deserialisation.hs, /home/tohung/stage07-clean-final/tools/marlowe_smt/dist-newstyle/build/x86_64-linux/ghc-9.6.7/marlowe-smt-0.2.0.0/x/marlowe-smt/build/marlowe-smt/marlowe-smt-tmp/Language/Marlowe/Semantics/Deserialisation.o )
[ 5 of 10] Compiling Language.Marlowe.Semantics ( upstream/marlowe/haskell/src/Language/Marlowe/Semantics.hs, /home/tohung/stage07-clean-final/tools/marlowe_smt/dist-newstyle/build/x86_64-linux/ghc-9.6.7/marlowe-smt-0.2.0.0/x/marlowe-smt/build/marlowe-smt/marlowe-smt-tmp/Language/Marlowe/Semantics.o )
[ 6 of 10] Compiling Language.Marlowe.Analysis.FSSemanticsFastVerbose ( upstream/marlowe/haskell/src/Language/Marlowe/Analysis/FSSemanticsFastVerbose.hs, /home/tohung/stage07-clean-final/tools/marlowe_smt/dist-newstyle/build/x86_64-linux/ghc-9.6.7/marlowe-smt-0.2.0.0/x/marlowe-smt/build/marlowe-smt/marlowe-smt-tmp/Language/Marlowe/Analysis/FSSemanticsFastVerbose.o )
[ 7 of 10] Compiling MarloweSMT.Analysis ( src/MarloweSMT/Analysis.hs, /home/tohung/stage07-clean-final/tools/marlowe_smt/dist-newstyle/build/x86_64-linux/ghc-9.6.7/marlowe-smt-0.2.0.0/x/marlowe-smt/build/marlowe-smt/marlowe-smt-tmp/MarloweSMT/Analysis.o )
[ 8 of 10] Compiling MarloweSMT.Bridge ( src/MarloweSMT/Bridge.hs, /home/tohung/stage07-clean-final/tools/marlowe_smt/dist-newstyle/build/x86_64-linux/ghc-9.6.7/marlowe-smt-0.2.0.0/x/marlowe-smt/build/marlowe-smt/marlowe-smt-tmp/MarloweSMT/Bridge.o )
[ 9 of 10] Compiling MarloweSMT.Output ( src/MarloweSMT/Output.hs, /home/tohung/stage07-clean-final/tools/marlowe_smt/dist-newstyle/build/x86_64-linux/ghc-9.6.7/marlowe-smt-0.2.0.0/x/marlowe-smt/build/marlowe-smt/marlowe-smt-tmp/MarloweSMT/Output.o )
[10 of 10] Compiling Main ( app/Main.hs, /home/tohung/stage07-clean-final/tools/marlowe_smt/dist-newstyle/build/x86_64-linux/ghc-9.6.7/marlowe-smt-0.2.0.0/x/marlowe-smt/build/marlowe-smt/marlowe-smt-tmp/Main.o )
[11 of 11] Linking /home/tohung/stage07-clean-final/tools/marlowe_smt/dist-newstyle/build/x86_64-linux/ghc-9.6.7/marlowe-smt-0.2.0.0/x/marlowe-smt/build/marlowe-smt/marlowe-smt
binary: /home/tohung/stage07-clean-final/tools/marlowe_smt/dist-newstyle/build/x86_64-linux/ghc-9.6.7/marlowe-smt-0.2.0.0/x/marlowe-smt/build/marlowe-smt/marlowe-smt
```

## Complete final test output

```text
$ cd /mnt/d/code/marlowe_ai_agent/tools/marlowe_smt
$ ./run_tests.sh
ghc: 9.6.7
cabal: 3.10.3.0
z3: Z3 version 4.13.3 - 64 bit
HEAD is now at 7b5b1e9 Bump the version on the cabal level
b663716be5c2d1cb21b411618e8a2c79eb0d2f0279c8263518c4a31c72353882  haskell/src/Language/Marlowe/Pretty.hs
12786d80df093802718217e94113b6eeeaf13632fe2f7f187f0af78c6b370d9f  haskell/src/Language/Marlowe/Deserialisation.hs
1030f782c96abec65e922c5aef6c4d575bd2608f4f7f74202c15a3376df8af35  haskell/src/Language/Marlowe/Semantics.hs
d5f64dcf8bd34207640ce93f7d423d47bf687af19044d6c4cea05781379ddc19  haskell/src/Language/Marlowe/Semantics/Deserialisation.hs
98452fb0cb78a37c53f25d2cc647af9ad81611fce0dd33e9e70b9823b82fdb14  haskell/src/Language/Marlowe/Semantics/Types.hs
628532d2258d1bfcb71ebc393e04c4629fb852b39343350fe54ddf15406d1318  haskell/src/Language/Marlowe/Analysis/FSSemanticsFastVerbose.hs
verified upstream commit 7b5b1e900ec53a8eb18747992bec73470704dfcb; no patches
upstream: 7b5b1e900ec53a8eb18747992bec73470704dfcb
Up to date
binary: /mnt/d/code/marlowe_ai_agent/tools/marlowe_smt/dist-newstyle/build/x86_64-linux/ghc-9.6.7/marlowe-smt-0.2.0.0/x/marlowe-smt/build/marlowe-smt/marlowe-smt
test_agent_escrow_fixture_is_valid (test_golden.MarloweSMTGoldenTests.test_agent_escrow_fixture_is_valid) ... ok
test_all_five_warning_types (test_golden.MarloweSMTGoldenTests.test_all_five_warning_types) ... ok
test_completed_audit_contracts_match_validator_acceptance (test_golden.MarloweSMTGoldenTests.test_completed_audit_contracts_match_validator_acceptance) ... AUDIT en-escrow_2party-L1-010-full.json: validator=pass smt=Valid warnings=[]
AUDIT en-loan-L4-007-full.json: validator=pass smt=Valid warnings=[]
AUDIT vi-crowdfunding-L4-004-full.json: validator=pass smt=Valid warnings=[]
AUDIT vi-escrow_3party-L4-006-full.json: validator=pass smt=Valid warnings=[]
AUDIT vi-milestone-L4-003-full.json: validator=pass smt=Valid warnings=[]
AUDIT vi-rental_deposit-L3-003-full.json: validator=pass smt=Valid warnings=[]
ok
test_constructor_address_and_native_token_coverage (test_golden.MarloweSMTGoldenTests.test_constructor_address_and_native_token_coverage) ... ok
test_initial_state_changes_result (test_golden.MarloweSMTGoldenTests.test_initial_state_changes_result) ... ok
test_invalid_inputs_are_structured_and_nonzero (test_golden.MarloweSMTGoldenTests.test_invalid_inputs_are_structured_and_nonzero) ... ok
test_merkleized_case_is_disclosed (test_golden.MarloweSMTGoldenTests.test_merkleized_case_is_disclosed) ... ok
test_hard_timeout_is_never_valid (test_process_states.ProcessStateTests.test_hard_timeout_is_never_valid) ... ok
test_solver_timeout_is_indeterminate (test_process_states.ProcessStateTests.test_solver_timeout_is_indeterminate) ... ok

----------------------------------------------------------------------
Ran 9 tests in 6.899s

OK
```

Exit status: 0.

## Exact status examples

### Valid

```text
$ marlowe-smt < marlowe_ai_agent/tests/fixtures/escrow_golden.json
{"analysis_notes":[],"counterexample":null,"meta":{"driver_version":"0.2.0","solver":"Z3 version 4.13.3 - 64 bit","upstream_commit":"7b5b1e900ec53a8eb18747992bec73470704dfcb"},"status":"Valid","warnings":[]}
```

### Counterexample

```text
$ marlowe-smt < tools/marlowe_smt/tests/nonpositive_pay.json
{"analysis_notes":[],"counterexample":{"start_time":"0","transactions":[{"inputs":[],"interval":{"from":"0","to":"0"}}]},"meta":{"driver_version":"0.2.0","solver":"Z3 version 4.13.3 - 64 bit","upstream_commit":"7b5b1e900ec53a8eb18747992bec73470704dfcb"},"status":"Counterexample","warnings":[{"account":{"role_token":"Alice"},"amount":0,"payee":{"party":{"role_token":"Bob"}},"type":"TransactionNonPositivePay"}]}
```

### InvalidInput

Complete stderr, stdout, and exit:

```text
$ printf '{' | marlowe-smt
stderr: invalid JSON: Unexpected end-of-input, expecting record key literal or }
stdout: {"analysis_notes":[],"counterexample":null,"error":"invalid JSON: Unexpected end-of-input, expecting record key literal or }","meta":{"driver_version":"0.2.0","solver":"Z3 version 4.13.3 - 64 bit","upstream_commit":"7b5b1e900ec53a8eb18747992bec73470704dfcb"},"status":"InvalidInput","warnings":[]}
exit=1
```

### Indeterminate

The input was generated with `generate(20, 4, True)`:

```text
$ marlowe-smt --solver-timeout-ms 1 < heavy.json
{"analysis_notes":[],"counterexample":null,"meta":{"driver_version":"0.2.0","solver":"Z3 version 4.13.3 - 64 bit","upstream_commit":"7b5b1e900ec53a8eb18747992bec73470704dfcb"},"solver_result":"Unknown.\n  Reason: timeout","status":"Indeterminate","warnings":[]}
```

### Timeout

The same input was passed to the standard-library Python wrapper:

```text
$ python3 run_smt.py --hard-timeout 0.000001 --solver-timeout-ms 300000 < heavy.json
{"status":"Timeout","warnings":[],"counterexample":null,"analysis_notes":[],"meta":{"solver":"z3 (subprocess did not complete)","upstream_commit":"7b5b1e900ec53a8eb18747992bec73470704dfcb","driver_version":"0.2.0"},"error":"hard timeout after 1e-06 seconds","process_exit":124}
```

The wrapper's Python return value contains `process_exit: 124`; the outer WSL
launcher translated the wrapper process's nonzero exit to 1. The status was
`Timeout`, never `Valid`.

## Stress command and summary

`bench/run_bench.py` executed this measurement shape for every generated row:

```text
/usr/bin/time -v -o <time-file> timeout 300 <marlowe-smt> --solver-timeout-ms 300000
```

The committed CSV has 48 configurations and 144 runs:

```text
rows=48 runs=144 min_s=0.2 max_s=0.41 min_rss=32584 max_rss=34208
```

The final, heaviest row is:

```text
20,4,true,80,Counterexample,0.30,34168,Counterexample,0.41,34176,Counterexample,0.30,34096
```

No run timed out, so the “two consecutive timeouts” stop rule was not reached.
Raw `time -v` files were intentionally not committed.

## Optional Route A

### BLST

Ubuntu package search returned no candidate:

```text
$ apt-cache search blst
<no output>
```

The official source was used:

```text
$ git clone --depth 1 --branch v0.3.11 https://github.com/supranational/blst.git /home/tohung/stage07-route-a/blst
$ cd /home/tohung/stage07-route-a/blst
$ git rev-parse HEAD
3dd0f804b1819e5d03fb22ca2e6fac105932043a
$ /usr/bin/time -v ./build.sh
+ cc -O2 -fno-builtin -fPIC -Wall -Wextra -Werror -D__ADX__ -c ./src/server.c
+ cc -O2 -fno-builtin -fPIC -Wall -Wextra -Werror -D__ADX__ -c ./build/assembly.S
+ ar rc libblst.a assembly.o server.o
        Elapsed (wall clock) time (h:mm:ss or m:ss): 0:01.67
        Maximum resident set size (kbytes): 100704
        Exit status: 0
$ PKG_CONFIG_PATH=/home/tohung/stage07-route-a/prefix/lib/pkgconfig pkg-config --modversion libblst
0.3.11
```

Headers, the static library, and a `libblst.pc` file were installed only to
`/home/tohung/stage07-route-a/prefix`; none was committed or installed into the
system prefix.

### Correct target and build

The Stage 0.6 command used the wrong component name. Repeating it showed that it
selected Hackage `marlowe-0.1.0.1`, not the local package:

```text
$ cabal build lib:marlowe --with-compiler=/home/tohung/.ghcup/ghc/9.2.8/bin/ghc
...
Starting     marlowe-0.1.0.1 (lib)
Building     marlowe-0.1.0.1 (lib)
Installing   marlowe-0.1.0.1 (lib)
Completed    marlowe-0.1.0.1 (lib)
```

Package identity check:

```text
$ grep -n '^name:\|^version:' marlowe/marlowe-cardano.cabal
2:name:            marlowe-cardano
3:version:         0.2.1.0
```

The correct build command and terminal output were:

```text
$ export PKG_CONFIG_PATH=/home/tohung/stage07-route-a/prefix/lib/pkgconfig
$ export LIBRARY_PATH=/home/tohung/stage07-route-a/prefix/lib
$ export C_INCLUDE_PATH=/home/tohung/stage07-route-a/prefix/include
$ /usr/bin/time -v timeout 1200 cabal build lib:marlowe-cardano --with-compiler=/home/tohung/.ghcup/ghc/9.2.8/bin/ghc
...
Configuring library for marlowe-cardano-0.2.1.0..
Preprocessing library for marlowe-cardano-0.2.1.0..
Building library for marlowe-cardano-0.2.1.0..
...
[14 of 31] Compiling Language.Marlowe.Analysis.FSSemantics
...
[31 of 31] Compiling Paths_marlowe_cardano
        Command being timed: "timeout 1200 cabal build lib:marlowe-cardano --with-compiler=/home/tohung/.ghcup/ghc/9.2.8/bin/ghc"
        User time (seconds): 4249.70
        System time (seconds): 609.16
        Percent of CPU this job got: 474%
        Elapsed (wall clock) time (h:mm:ss or m:ss): 17:03.55
        Maximum resident set size (kbytes): 1445104
        Exit status: 0
```

The full untruncated dependency/build stream was retained outside Git at
`/home/tohung/stage07-route-a/route-a-correct-build.log`; it contains no error.

The first temporary-driver compilation attempted before the correct local
package had been built. Its complete error was:

```text
$ cabal exec -w /home/tohung/.ghcup/ghc/9.2.8/bin/ghc -- ghc ... -package marlowe
Loaded package environment from /home/tohung/stage05-infra/marlowe-cardano-main/dist-newstyle/tmp/environment.-327/.ghc.environment.x86_64-linux-9.2.8
ghc-9.2.8: can't find a package database at /home/tohung/stage05-infra/marlowe-cardano-main/dist-newstyle/packagedb/ghc-9.2.8
```

After the correct build:

```text
$ cabal exec -w /home/tohung/.ghcup/ghc/9.2.8/bin/ghc -- ghc -O1 /home/tohung/stage07-route-a/Main.hs -o /home/tohung/stage07-route-a/route-a-driver -package marlowe-cardano -package aeson -package bytestring
Loaded package environment from /home/tohung/stage05-infra/marlowe-cardano-main/dist-newstyle/tmp/environment.-373/.ghc.environment.x86_64-linux-9.2.8
[1 of 1] Compiling Main
Linking /home/tohung/stage07-route-a/route-a-driver ...
```

### Same-fixture output

The temporary driver used `warningsTraceWithState (SlotLength 1000)`:

```text
escrow_golden.json    {"status":"Valid","warnings":[]}
partial_pay.json      {"status":"Counterexample","warnings":["TransactionPartialPay"]}
nonpositive_pay.json  {"status":"Counterexample","warnings":["TransactionNonPositivePay"]}
nonpositive_deposit.json {"status":"Counterexample","warnings":["TransactionNonPositiveDeposit"]}
shadowing.json        {"status":"Counterexample","warnings":["TransactionShadowing"]}
assertion_failed.json {"status":"Counterexample","warnings":["TransactionAssertionFailed"]}
state_empty.json      {"status":"Counterexample","warnings":["TransactionPartialPay"]}
state_funded.json     {"status":"Valid","warnings":[]}
merkleized.json       {"status":"Valid","warnings":[]}
coverage_valid.json   {"error":"Error in $: key \"assert\" not found; envelope: Error in $: parsing Main.Envelope(Envelope) failed, key \"contract\" not found","status":"InvalidInput"}
coverage_warning.json {"error":"Error in $.assert: key \"value\" not found; envelope: Error in $: parsing Main.Envelope(Envelope) failed, key \"contract\" not found","status":"InvalidInput"}
```

The two complete errors above arise because both fixtures contain the deliberate
placeholder address `addr_test1vr8nl5`; Route A's `Address` parser validates
on-chain encoding, whereas the packaged bridge treats addresses as opaque UTF-8.

All usable audit contracts matched:

```text
en-escrow_2party-L1-010-full.json     {"status":"Valid","warnings":[]} exit=0
en-loan-L4-007-full.json              {"status":"Valid","warnings":[]} exit=0
vi-crowdfunding-L4-004-full.json      {"status":"Valid","warnings":[]} exit=0
vi-escrow_3party-L4-006-full.json     {"status":"Valid","warnings":[]} exit=0
vi-milestone-L4-003-full.json         {"status":"Valid","warnings":[]} exit=0
vi-rental_deposit-L3-003-full.json    {"status":"Valid","warnings":[]} exit=0
```

No `cardano-node` command was executed and no node was installed or started.
