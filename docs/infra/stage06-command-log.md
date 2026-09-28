# Stage 0.6 command log

Date: 2026-09-28. Commands ran in WSL2 Ubuntu unless a PowerShell prompt is
shown. Build artifacts and temporary contracts were kept under
`/home/tohung/stage06-infra/` and were not committed.

## Stage 0.5 correction

Source inspection was performed against `marlowe-cardano` commit
`99f432d8ef9dbd1b52b7fa089254de15913b490f`. The correction was committed before
any Stage 0.6 build work:

```text
$ git log -1 --oneline
0d652aa docs(infra): correct marlowe-cli run analyze scope
```

The append-only command logs for Stage 0 and Stage 0.5 contain the detailed
source-inspection commands and correction note.

## Toolchain

```text
$ z3 --version
Z3 version 4.13.3 - 64 bit

$ ghc --version
The Glorious Glasgow Haskell Compilation System, version 9.6.7

$ cabal --version
cabal-install version 3.10.3.0
compiled using version 3.10.3.0 of the Cabal library

$ ghcup --version
The GHCup Haskell installer, version v0.2.6.2

$ uname -a
Linux To-hyung 6.18.33.2-microsoft-standard-WSL2 #1 SMP PREEMPT_DYNAMIC Thu Jun 18 21:54:43 UTC 2026 x86_64 GNU/Linux
```

The first Ubuntu update used the pre-existing Docker source and failed:

```text
W: GPG error: https://download.docker.com/linux/ubuntu resolute InRelease: The following signatures couldn't be verified because the public key is not available: NO_PUBKEY 7EA0A9C3F273FCD8
E: The repository 'https://download.docker.com/linux/ubuntu resolute InRelease' is not signed.
```

The retry restricted apt to Ubuntu's official source and installed the required
packages:

```text
# apt-get -o Dir::Etc::sourcelist=/etc/apt/sources.list.d/ubuntu.sources -o Dir::Etc::sourceparts=- update
# DEBIAN_FRONTEND=noninteractive apt-get -o Dir::Etc::sourcelist=/etc/apt/sources.list.d/ubuntu.sources -o Dir::Etc::sourceparts=- install -y z3 build-essential curl libffi-dev libgmp-dev libncurses-dev pkg-config xz-utils
```

GHCup installed GHC 9.2.8 first. An initial link attempt then exposed a missing
Gold linker:

```text
collect2: fatal error: cannot find ‘ld’
compilation terminated.
```

`binutils-gold` was installed from the same official Ubuntu source. GHC 9.6.7
was then installed and selected:

```text
$ /usr/bin/time -v ghcup install ghc 9.6.7
[ Info  ] ghc installation successful
        Elapsed (wall clock) time (h:mm:ss or m:ss): 3:11.38
        Maximum resident set size (kbytes): 725884
        Exit status: 0

$ ghcup set ghc 9.6.7
[ Info  ] ghc 9.6.7 successfully set as default version
```

## Route B source and entry point

```text
$ git clone https://github.com/marlowe-lang/marlowe.git /home/tohung/stage06-infra/marlowe-reference-source
$ cd /home/tohung/stage06-infra/marlowe-reference-source
$ git rev-parse HEAD
7b5b1e900ec53a8eb18747992bec73470704dfcb
$ git show -s --format='%cI %s' HEAD
2026-05-26T12:12:40+02:00 Bump the version on the cabal level
```

The exact inspected declaration was:

```text
warningsTraceWithState :: Contract
              -> Maybe State
              -> IO (Either ThmResult
                            (Maybe (POSIXTime, [TransactionInput], [TransactionWarning])))
warningsTraceWithState con maybeState =
    do thmRes@(ThmResult result) <- satCommand
       return (case result of
                 Unsatisfiable _ _ -> Right Nothing
                 Satisfiable _ smtModel ->
                    Right (Just (extractCounterExample smtModel con maybeState params))
                 _ -> Left thmRes)
  where maxActs = 1 + countWhens con
        params = generateLabels maxActs
        property = do v <- generateParameters params
                      r <- wrapper con v maybeState
                      return (sNot r)
        satCommand = proveWith z3 property
```

## Route B upstream build attempts

With GHC 9.2.8:

```text
$ cd /home/tohung/stage06-infra/marlowe-reference-source/haskell
$ /usr/bin/time -v cabal build all
...
collect2: fatal error: cannot find ‘ld’
compilation terminated.
```

After installing `binutils-gold`, both the normal build and the retry with a
warning override stopped at the same complete diagnostic:

```text
$ /usr/bin/time -v cabal build all --ghc-option=-Wno-error=dodgy-imports
...
Data/SBV/Core/Model.hs:64:1: error: [-Wdodgy-imports, -Werror=dodgy-imports]
    Module ‘GHC.TypeLits’ does not export ‘SChar’
   |
64 | import GHC.TypeLits hiding (SChar)
   | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Error: cabal: Failed to build sbv-10.12 (which is required by exe:marlowe from
marlowe-reference-0.3.0.1). See the build log above for details.

Command exited with non-zero status 1
        Command being timed: "cabal build all --ghc-option=-Wno-error=dodgy-imports"
        User time (seconds): 95.08
        System time (seconds): 5.87
        Percent of CPU this job got: 120%
        Elapsed (wall clock) time (h:mm:ss or m:ss): 1:23.46
        Maximum resident set size (kbytes): 757972
        Exit status: 1
```

With GHC 9.6.7, SBV itself completed and the required analysis module compiled,
but the full upstream executable failed in the unrelated Template Haskell
helper:

```text
$ ghc --version
The Glorious Glasgow Haskell Compilation System, version 9.6.7
$ /usr/bin/time -v cabal build all
...
Installing   sbv-10.12 (lib)
Completed    sbv-10.12 (lib)
...
[ 4 of 29] Compiling Language.Marlowe.Analysis.MkSymb

src/Language/Marlowe/Analysis/MkSymb.hs:16:55: error:
    Module ‘Language.Haskell.TH’ does not export ‘BndrVis’
   |
16 |                             Info(TyConI), PatQ, Name, BndrVis)
   |                                                       ^^^^^^^
...
[12 of 29] Compiling Language.Marlowe.Analysis.FSSemanticsFastVerbose
...
Error: cabal: Failed to build exe:marlowe from marlowe-reference-0.3.0.1.

Command exited with non-zero status 1
        Command being timed: "cabal build all"
        User time (seconds): 971.64
        System time (seconds): 136.05
        Percent of CPU this job got: 337%
        Elapsed (wall clock) time (h:mm:ss or m:ss): 5:28.55
        Maximum resident set size (kbytes): 859052
        Exit status: 1
```

## External driver build

The driver and its hand-written contracts were created under
`/home/tohung/stage06-infra/smt-driver-b/`. It references the upstream source
tree but compiles only the modules required by `FSSemanticsFastVerbose`.

```text
$ cd /home/tohung/stage06-infra/smt-driver-b
$ /usr/bin/time -v cabal build exe:smt-driver-b
Resolving dependencies...
Build profile: -w ghc-9.6.7 -O1
In order, the following will be built (use -v for more details):
 - smt-driver-b-0.1.0.0 (exe:smt-driver-b) (configuration changed)
Configuring executable 'smt-driver-b' for smt-driver-b-0.1.0.0..
Warning: 'hs-source-dirs: ../marlowe-reference-source/haskell/src' is a
relative path outside of the source tree. This will not work when generating a
tarball with 'sdist'.
Preprocessing executable 'smt-driver-b' for smt-driver-b-0.1.0.0..
Building executable 'smt-driver-b' for smt-driver-b-0.1.0.0..
[5 of 7] Compiling Language.Marlowe.Semantics
[6 of 7] Compiling Language.Marlowe.Analysis.FSSemanticsFastVerbose
[7 of 7] Compiling Main
[8 of 8] Linking /home/tohung/stage06-infra/smt-driver-b/dist-newstyle/build/x86_64-linux/ghc-9.6.7/smt-driver-b-0.1.0.0/x/smt-driver-b/build/smt-driver-b/smt-driver-b
        Command being timed: "cabal build exe:smt-driver-b"
        User time (seconds): 7.25
        System time (seconds): 2.22
        Percent of CPU this job got: 76%
        Elapsed (wall clock) time (h:mm:ss or m:ss): 0:12.37
        Maximum resident set size (kbytes): 342568
        Exit status: 0
```

The final output-envelope change rebuilt successfully:

```text
$ cabal build exe:smt-driver-b
Resolving dependencies...
Build profile: -w ghc-9.6.7 -O1
In order, the following will be built (use -v for more details):
 - smt-driver-b-0.1.0.0 (exe:smt-driver-b) (file Main.hs changed)
Preprocessing executable 'smt-driver-b' for smt-driver-b-0.1.0.0..
Building executable 'smt-driver-b' for smt-driver-b-0.1.0.0..
[7 of 7] Compiling Main
[8 of 8] Linking /home/tohung/stage06-infra/smt-driver-b/dist-newstyle/build/x86_64-linux/ghc-9.6.7/smt-driver-b-0.1.0.0/x/smt-driver-b/build/smt-driver-b/smt-driver-b
```

## Solver tests — exact output

The common binary path below is abbreviated as `$SMT` in the displayed
commands only:

```text
SMT=/home/tohung/stage06-infra/smt-driver-b/dist-newstyle/build/x86_64-linux/ghc-9.6.7/smt-driver-b-0.1.0.0/x/smt-driver-b/build/smt-driver-b/smt-driver-b
```

Canonical escrow:

```text
$ timeout 300 $SMT < /mnt/d/code/marlowe_ai_agent/marlowe_ai_agent/tests/fixtures/escrow_golden.json
{"counterexample":null,"status":"Valid","warnings":[]}
```

Deposit 10, then attempt to pay 20:

```text
$ timeout 300 $SMT < /home/tohung/stage06-infra/smt-driver-b/cases/bad-overpay.json
{"counterexample":{"start_time":"0","transactions":["TransactionInput {txInterval = TimeInterval 0 0, txInputs = [NormalInput (IDeposit (Role \"Alice\") (Role \"Alice\") (Token \"\" \"\") 10)]}"]},"status":"Counterexample","warnings":["TransactionPartialPay (Role \"Alice\") (Party (Role \"Bob\")) 10 20"]}
```

Zero deposit:

```text
$ timeout 300 $SMT < /home/tohung/stage06-infra/smt-driver-b/cases/bad-zero-deposit.json
{"counterexample":{"start_time":"0","transactions":["TransactionInput {txInterval = TimeInterval 0 0, txInputs = [NormalInput (IDeposit (Role \"Alice\") (Role \"Alice\") (Token \"\" \"\") 0)]}"]},"status":"Counterexample","warnings":["TransactionNonPositiveDeposit (Role \"Alice\") (Role \"Alice\") 0"]}
```

Duplicate `Let`:

```text
$ timeout 300 $SMT < /home/tohung/stage06-infra/smt-driver-b/cases/bad-duplicate-let.json
{"counterexample":{"start_time":"0","transactions":["TransactionInput {txInterval = TimeInterval 0 0, txInputs = []}"]},"status":"Counterexample","warnings":["TransactionShadowing \"x\" 1 2"]}
```

Malformed-input control:

```text
$ printf '{' | $SMT
invalid JSON: Unexpected end-of-input, expecting record key literal or }
```

The malformed-input process exited 1.

## Hardest L4 selection and exact measurements

```text
PS> Get-ChildItem marlowe_ai_agent/bench/audit/*-L4-*-full.json | ...
File                                       Status  CaseCount WhenCount HasContract
----                                       ------  --------- --------- -----------
vi-milestone-L4-003-full.json              done            9         5        True
vi-crowdfunding-L4-004-full.json           done            4         3        True
vi-escrow_3party-L4-006-full.json          done            3         2        True
en-loan-L4-007-full.json                   done            2         2        True
vi-cancellation_fee-L4-001-full.json       blocked         0         0        True
vi-cancellation_fee-L4-001-retry-full.json blocked         0         0        True
```

Copy verification:

```text
PS> compare compact JSON for audit.contract and cases/hardest-l4.json
equal=True
source_length=3279 copy_length=3279
```

Run 1:

```text
$ /usr/bin/time -v timeout 300 $SMT < /home/tohung/stage06-infra/smt-driver-b/cases/hardest-l4.json
{"counterexample":null,"status":"Valid","warnings":[]}
        Command being timed: "timeout 300 /home/tohung/stage06-infra/smt-driver-b/dist-newstyle/build/x86_64-linux/ghc-9.6.7/smt-driver-b-0.1.0.0/x/smt-driver-b/build/smt-driver-b/smt-driver-b"
        User time (seconds): 0.00
        System time (seconds): 0.02
        Percent of CPU this job got: 27%
        Elapsed (wall clock) time (h:mm:ss or m:ss): 0:00.10
        Average shared text size (kbytes): 0
        Average unshared data size (kbytes): 0
        Average stack size (kbytes): 0
        Average total size (kbytes): 0
        Maximum resident set size (kbytes): 28588
        Average resident set size (kbytes): 0
        Major (requiring I/O) page faults: 0
        Minor (reclaiming a frame) page faults: 6437
        Voluntary context switches: 197
        Involuntary context switches: 0
        Swaps: 0
        File system inputs: 8
        File system outputs: 0
        Socket messages sent: 0
        Socket messages received: 0
        Signals delivered: 0
        Page size (bytes): 4096
        Exit status: 0
```

Run 2:

```text
$ /usr/bin/time -v timeout 300 $SMT < /home/tohung/stage06-infra/smt-driver-b/cases/hardest-l4.json
{"counterexample":null,"status":"Valid","warnings":[]}
        Command being timed: "timeout 300 /home/tohung/stage06-infra/smt-driver-b/dist-newstyle/build/x86_64-linux/ghc-9.6.7/smt-driver-b-0.1.0.0/x/smt-driver-b/build/smt-driver-b/smt-driver-b"
        User time (seconds): 0.00
        System time (seconds): 0.02
        Percent of CPU this job got: 27%
        Elapsed (wall clock) time (h:mm:ss or m:ss): 0:00.10
        Average shared text size (kbytes): 0
        Average unshared data size (kbytes): 0
        Average stack size (kbytes): 0
        Average total size (kbytes): 0
        Maximum resident set size (kbytes): 28800
        Average resident set size (kbytes): 0
        Major (requiring I/O) page faults: 0
        Minor (reclaiming a frame) page faults: 6441
        Voluntary context switches: 195
        Involuntary context switches: 0
        Swaps: 0
        File system inputs: 0
        File system outputs: 0
        Socket messages sent: 0
        Socket messages received: 0
        Signals delivered: 0
        Page size (bytes): 4096
        Exit status: 0
```

Run 3:

```text
$ /usr/bin/time -v timeout 300 $SMT < /home/tohung/stage06-infra/smt-driver-b/cases/hardest-l4.json
{"counterexample":null,"status":"Valid","warnings":[]}
        Command being timed: "timeout 300 /home/tohung/stage06-infra/smt-driver-b/dist-newstyle/build/x86_64-linux/ghc-9.6.7/smt-driver-b-0.1.0.0/x/smt-driver-b/build/smt-driver-b/smt-driver-b"
        User time (seconds): 0.00
        System time (seconds): 0.02
        Percent of CPU this job got: 29%
        Elapsed (wall clock) time (h:mm:ss or m:ss): 0:00.10
        Average shared text size (kbytes): 0
        Average unshared data size (kbytes): 0
        Average stack size (kbytes): 0
        Average total size (kbytes): 0
        Maximum resident set size (kbytes): 28432
        Average resident set size (kbytes): 0
        Major (requiring I/O) page faults: 0
        Minor (reclaiming a frame) page faults: 6442
        Voluntary context switches: 196
        Involuntary context switches: 1
        Swaps: 0
        File system inputs: 0
        File system outputs: 0
        Socket messages sent: 0
        Socket messages received: 0
        Signals delivered: 0
        Page size (bytes): 4096
        Exit status: 0
```

## Route A attempt and exact blocker

Initial attempt:

```text
$ /usr/bin/time -v timeout 900 cabal build lib:marlowe --with-compiler=/home/tohung/.ghcup/ghc/9.2.8/bin/ghc
Cloning into '/home/tohung/stage05-infra/marlowe-cardano-main/dist-newstyle/src/actus-core-8f176c27d79c037'...
HEAD is now at 3bddfeb SCP-5006: Nix flakes
Cloning into '/home/tohung/stage05-infra/marlowe-cardano-main/dist-newstyle/src/cardano-a_-9dcb24dcdc64ec91'...
HEAD is now at 0b66b8ad Merge pull request #240 from IntersectMBO/angerman-patch-1
Cloning into '/home/tohung/stage05-infra/marlowe-cardano-main/dist-newstyle/src/marlowe-ec90a0ac04f71c59'...
HEAD is now at e94fab2 Bump tasty-quickcheck version
Warning: Caught exception during _mirrors lookup:DnsHostNotFound
Warning: No mirrors found for https://chap.intersectmbo.org/
Warning: The package list for 'cardano-haskell-packages' does not exist. Run
'cabal update' to download it.
Warning: Requested index-state 2024-08-28T06:44:16Z is newer than
'cardano-haskell-packages'! Falling back to older state ().
Resolving dependencies...
Error: cabal: Could not resolve dependencies:
[__0] trying: cardano-addresses-3.12.0 (user goal)
[__1] unknown package: cardano-crypto (dependency of cardano-addresses)
[__1] fail (backjumping, conflict set: cardano-addresses, cardano-crypto)
After searching the rest of the dependency tree exhaustively, these were the
goals I've had most trouble fulfilling: cardano-addresses, cardano-crypto

Command exited with non-zero status 1
        Elapsed (wall clock) time (h:mm:ss or m:ss): 0:30.16
        Maximum resident set size (kbytes): 862988
        Exit status: 1
```

The CHaP retry succeeded:

```text
$ /usr/bin/time -v timeout 300 cabal update cardano-haskell-packages
HEAD is now at 3bddfeb SCP-5006: Nix flakes
HEAD is now at 0b66b8ad Merge pull request #240 from IntersectMBO/angerman-patch-1
HEAD is now at e94fab2 Bump tasty-quickcheck version
Downloading the latest package list from cardano-haskell-packages
Package list of cardano-haskell-packages has been updated.
The index-state is set to 2026-09-24T00:08:56Z.
        Elapsed (wall clock) time (h:mm:ss or m:ss): 0:08.02
        Maximum resident set size (kbytes): 38704
        Exit status: 0
```

After installing `libsodium-dev` and `libsecp256k1-dev`, the final Route A
attempt produced this complete dependency-resolution blocker:

```text
$ pkg-config --modversion libsodium
1.0.18
$ /usr/bin/time -v timeout 900 cabal build lib:marlowe --with-compiler=/home/tohung/.ghcup/ghc/9.2.8/bin/ghc
Resolving dependencies...
Error: cabal: Could not resolve dependencies:
[__0] trying: cardano-debug-0.0.1 (user goal)
[__1] trying: cardano-ledger-shelley-1.13.0.0 (dependency of cardano-debug)
[__2] next goal: cardano-crypto-class (dependency of cardano-ledger-shelley)
[__2] rejecting: cardano-crypto-class-2.1.5.0, cardano-crypto-class-2.1.4.0,
cardano-crypto-class-2.1.3.0, cardano-crypto-class-2.1.2.0 (conflict:
pkg-config package libblst-any, not found in the pkg-config database)
[__2] trying: cardano-crypto-class-2.1.1.0
[__3] next goal: cardano-api (dependency of cardano-debug)
[__3] rejecting: cardano-api-9.2.0.0 (conflict: cardano-crypto-class==2.1.1.0,
cardano-api => cardano-crypto-class^>=2.1.2)
[__3] skipping: cardano-api-9.1.0.0, cardano-api-9.0.0.0,
cardano-api-8.49.0.0, cardano-api-8.48.0.1, cardano-api-8.48.0.0,
cardano-api-8.47.0.0, cardano-api-8.46.0.0, cardano-api-8.45.2.0,
cardano-api-8.45.1.0, cardano-api-8.45.0.0, cardano-api-8.44.0.0,
cardano-api-8.43.0.0, cardano-api-8.42.0.0, cardano-api-8.41.0.0,
cardano-api-8.40.0.0, cardano-api-8.39.3.0, cardano-api-8.39.2.0,
cardano-api-8.39.1.0, cardano-api-8.39.0.0, cardano-api-8.38.0.2,
cardano-api-8.38.0.1, cardano-api-8.38.0.0, cardano-api-8.37.1.0,
cardano-api-8.37.0.0, cardano-api-8.36.1.1, cardano-api-8.36.1.0,
cardano-api-8.35.0.0, cardano-api-8.34.1.0, cardano-api-8.34.0.0,
cardano-api-8.33.0.0, cardano-api-8.32.0.0, cardano-api-8.31.0.0,
cardano-api-8.30.0.0, cardano-api-8.29.1.0, cardano-api-8.29.0.0,
cardano-api-8.28.0.0, cardano-api-8.27.0.0, cardano-api-8.26.0.0,
cardano-api-8.25.2.0, cardano-api-8.25.0.1, cardano-api-8.25.0.0,
cardano-api-8.24.0.0, cardano-api-8.23.2.0, cardano-api-8.23.1.0,
cardano-api-8.23.0.0, cardano-api-8.22.0.0, cardano-api-8.21.0.0,
cardano-api-8.20.2.0, cardano-api-8.20.1.0, cardano-api-8.20.0.0,
cardano-api-8.19.0.0, cardano-api-8.18.0.0, cardano-api-8.17.1.0,
cardano-api-8.17.0.0, cardano-api-8.16.3.0, cardano-api-8.16.2.0,
cardano-api-8.16.1.0, cardano-api-8.16.0.0, cardano-api-8.15.0.0 (has the same
characteristics that caused the previous version to fail: excludes
'cardano-crypto-class' version 2.1.1.0)
[__3] rejecting: cardano-api-8.14.0.0 (conflict: cardano-debug =>
cardano-api^>=9.2)
[__3] skipping: cardano-api-8.13.1.0, cardano-api-8.13.0.0,
cardano-api-8.12.0.0, cardano-api-8.11.1.0, cardano-api-8.11.0.0,
cardano-api-8.10.2.0, cardano-api-8.10.1.0, cardano-api-8.10.0.0,
cardano-api-8.9.0.0, cardano-api-8.8.1.2, cardano-api-8.8.1.1,
cardano-api-8.8.1.0, cardano-api-8.8.0.0, cardano-api-8.7.0.0,
cardano-api-8.6.0.0, cardano-api-8.5.2.0, cardano-api-8.5.0.0,
cardano-api-8.4.0.0, cardano-api-8.3.0.0, cardano-api-8.2.0.0,
cardano-api-8.1.1.1, cardano-api-8.1.1.0, cardano-api-8.1.0.1,
cardano-api-8.0.0, cardano-api-1.36.0, cardano-api-1.35.4, cardano-api-1.35.3
(has the same characteristics that caused the previous version to fail:
excluded by constraint '^>=9.2' from 'cardano-debug')
[__3] fail (backjumping, conflict set: cardano-api, cardano-crypto-class,
cardano-debug)
After searching the rest of the dependency tree exhaustively, these were the
goals I've had most trouble fulfilling: cardano-crypto-class,
cardano-ledger-shelley, cardano-api, cardano-debug
Try running with --minimize-conflict-set to improve the error message.

Command exited with non-zero status 1
        Command being timed: "timeout 900 cabal build lib:marlowe --with-compiler=/home/tohung/.ghcup/ghc/9.2.8/bin/ghc"
        User time (seconds): 3.61
        System time (seconds): 0.44
        Percent of CPU this job got: 96%
        Elapsed (wall clock) time (h:mm:ss or m:ss): 0:04.21
        Maximum resident set size (kbytes): 433112
        Exit status: 1
```

No `cardano-node` process or binary was installed or started.
