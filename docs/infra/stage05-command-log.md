# Stage 0.5 command log

Recorded on 2026-09-27 in WSL2 Ubuntu. All downloaded binaries, source
checkouts, generated contracts, and private-network files were kept under
`/home/tohung/stage05-infra/`, outside the Git repository. The only repository
input read was the audit JSON. No LLM or model API was invoked.

## 1. Official Linux release download and verification

Release metadata identified this exact asset:

```text
tag: 11.1.2
asset: cardano-node-11.1.2-linux-amd64.tar.gz
size: 233771973
url: https://github.com/IntersectMBO/cardano-node/releases/download/11.1.2/cardano-node-11.1.2-linux-amd64.tar.gz
```

Commands:

```bash
mkdir -p /home/tohung/stage05-infra
cd /home/tohung/stage05-infra
curl -L --fail --show-error \
  -o cardano-node-11.1.2-linux-amd64.tar.gz \
  https://github.com/IntersectMBO/cardano-node/releases/download/11.1.2/cardano-node-11.1.2-linux-amd64.tar.gz
curl -L --fail --show-error \
  -o cardano-node-11.1.2-linux-amd64.tar.gz.sha256sums.txt \
  https://github.com/IntersectMBO/cardano-node/releases/download/11.1.2/cardano-node-11.1.2-sha256sums.txt
stat -c 'size_bytes=%s' cardano-node-11.1.2-linux-amd64.tar.gz
sha256sum cardano-node-11.1.2-linux-amd64.tar.gz
grep cardano-node-11.1.2-linux-amd64.tar.gz \
  cardano-node-11.1.2-linux-amd64.tar.gz.sha256sums.txt
```

Output:

```text
size_bytes=233771973
fd872fbeb9cc663e67088ca47ed01aa01d18a77d7dbee694e2444bb23d833759  cardano-node-11.1.2-linux-amd64.tar.gz
fd872fbeb9cc663e67088ca47ed01aa01d18a77d7dbee694e2444bb23d833759  cardano-node-11.1.2-linux-amd64.tar.gz
```

The archive's main executables were extracted to
`/home/tohung/stage05-infra/cardano-node-11.1.2-linux/bin`. The Marlowe binary
verified in Stage 0 was copied to `/home/tohung/stage05-infra/bin`.

```bash
cardano-node --version
cardano-cli --version
cardano-testnet version
marlowe-cli --version
file cardano-node cardano-testnet marlowe-cli
sha256sum marlowe-cli
```

Output:

```text
cardano-node 11.1.2 - linux-x86_64 - ghc-9.6
git rev fef83fed01d7926f3de83b3b917be5a4a48768b5
cardano-cli 11.2.3.0 - linux-x86_64 - ghc-9.6
git rev fef83fed01d7926f3de83b3b917be5a4a48768b5
cardano-node 11.1.1 - linux-x86_64 - ghc-9.6
git rev 0000000000000000000000000000000000000000
built against cardano-api 11.6.0.0
built against cardano-rpc 11.2.0.0
built against cardano-cli 11.2.3.0
marlowe-cli 0.2.0.0
cardano-node:    ELF 64-bit LSB executable, x86-64, statically linked, not stripped
cardano-testnet: ELF 64-bit LSB executable, x86-64, statically linked, not stripped
marlowe-cli:     ELF 64-bit LSB executable, x86-64, statically linked, stripped
464f14957aafeefc86aa868074e200f700aefc070f1ecb32466d999110e58939  marlowe-cli
```

Note: `cardano-testnet version` identifies its package as 11.1.1 even though
it is the executable shipped inside the checksum-verified 11.1.2 archive.

## 2. Private network and Unix socket

The effective successful invocation was:

```bash
CARDANO_CLI=/home/tohung/stage05-infra/cardano-node-11.1.2-linux/bin/cardano-cli \
CARDANO_NODE=/home/tohung/stage05-infra/cardano-node-11.1.2-linux/bin/cardano-node \
/home/tohung/stage05-infra/cardano-node-11.1.2-linux/bin/cardano-testnet cardano \
  --num-pool-nodes 1 \
  --testnet-magic 42 \
  --slot-length 0.2 \
  --active-slots-coeff 0.05 \
  --output-dir /home/tohung/stage05-infra/private-testnet
```

Startup output:

```text
Creating environment: /home/tohung/stage05-infra/private-testnet/
Starting testnet in environment: /home/tohung/stage05-infra/private-testnet/
```

The explicit environment variables were necessary. An initial invocation that
only prepended `PATH` could not discover `CARDANO_CLI` and stopped with:

```text
Could not find plan.json in the path: dist-newstyle/cache/plan.json. Please run
"cabal build cardano-cli" if you are working with sources. Otherwise define
CARDANO_CLI and have it point to the executable you want.
```

A first network using 0.1-second slots and active-slots coefficient 0.2 also
missed its small startup window and its watchdog stopped it:

```text
node1 was unable to produce any blocks for 38s. The testnet probably missed
its startup window and can never produce a block: nodes can only forge while
the wall-clock slot is at most 3 * securityParam / activeSlotsCoeff slots past
the chain tip (7.5s of wall clock for this testnet), and the genesis start time
is set only 15s after the testnet files are created.
```

The slower successful control above produced a socket and accepted local state
queries. Exact verification:

```bash
file /home/tohung/stage05-infra/private-testnet/socket/node1/sock
stat -c 'mode=%F permissions=%A inode=%i path=%n' \
  /home/tohung/stage05-infra/private-testnet/socket/node1/sock
CARDANO_NODE_SOCKET_PATH=/home/tohung/stage05-infra/private-testnet/socket/node1/sock \
  cardano-cli query tip --testnet-magic 42
```

Output:

```text
/home/tohung/stage05-infra/private-testnet/socket/node1/sock: socket
mode=socket permissions=srwxr-xr-x inode=56844 path=/home/tohung/stage05-infra/private-testnet/socket/node1/sock
{
    "epoch": 0,
    "era": "Conway",
    "slotInEpoch": 0,
    "slotsToEpochEnd": 500,
    "syncProgress": "100.00"
}
```

The testnet later printed `Testnet started` and was stopped with Ctrl+C. A
process check after shutdown returned no `cardano-node` or `cardano-testnet`
process.

## 3. Contract extraction and CLI-discovered file format

Python's standard JSON library read this file only:

```text
/mnt/d/code/marlowe_ai_agent/marlowe_ai_agent/bench/audit/en-escrow_2party-L1-010-full.json
```

The value at top-level key `contract` was written outside Git to
`/home/tohung/stage05-infra/contracts/escrow-contract.json`. A minimal control
containing only JSON string `"close"` was written beside it.

```text
escrow bytes: 2437
escrow SHA-256: af7d7d6e7a21de6a9d9a16c60d33e9375390ccb23de4126f4e36b3b1cf580d9d
minimal SHA-256: 97959247360c5f0b8faf336aea5eba322af7be295958302fdb8a3fe8c6eb8ab8
```

The exact relevant help output was:

```text
$ marlowe-cli run --help
Commands for running contracts:
  execute                  Run a Marlowe transaction.
  initialize               Initialize the first transaction of a Marlowe
                           contract and write output to a JSON file.
  prepare                  Prepare the next step of a Marlowe contract and write
                           the output to a JSON file.
  withdraw                 Withdraw funds from the Marlowe role address.
  analyze                  [EXPERIMENTAL] Analyze a Marlowe contract.

$ marlowe-cli run initialize --help
Usage: marlowe-cli run initialize (--mainnet | --testnet-magic INTEGER)
                                  --socket-path SOCKET_FILE
                                  [--stake-address ADDRESS]
                                  [--roles-currency CURRENCY_SYMBOL]
                                  --contract-file CONTRACT_FILE
                                  --state-file STATE_FILE
                                  [--at-address ADDRESS |
                                    --permanently STAKING_ADDRESS |
                                    --permanently-without-staking]
                                  [--out-file OUTPUT_FILE] [--merkleize]
                                  [--print-stats]

$ marlowe-cli run analyze --help
Usage: marlowe-cli run analyze (--mainnet | --testnet-magic INTEGER)
                               --socket-path SOCKET_FILE
                               --marlowe-file MARLOWE_FILE [--preconditions]
                               [--roles] [--tokens] [--maximum-value]
                               [--minimum-utxo] [--execution-cost]
                               [--transaction-size] [--best] [--verbose]

  --marlowe-file MARLOWE_FILE
                           JSON file with the state and contract.
```

`template simple` generated an accepted state with keys `accounts`,
`boundValues`, `choices`, and `minTime`. The release-tag source then confirmed
the full `SomeMarloweTransaction` envelope (`era`, `plutusVersion`, and `tx`)
and supplied a checked-in initialized example at
`marlowe-cli/doc/simple-1.marlowe`.

## 4. Initializer result

Command:

```bash
marlowe-cli --conway-era run initialize \
  --testnet-magic 42 \
  --socket-path /home/tohung/stage05-infra/private-testnet/socket/node1/sock \
  --contract-file /home/tohung/stage05-infra/contracts/escrow-contract.json \
  --state-file /home/tohung/stage05-infra/contracts/initial-state.json \
  --out-file /home/tohung/stage05-infra/results/escrow-marlowe.json \
  --print-stats
```

Complete error (exit code 1):

```text
marlowe-cli: DecoderFailure (LocalStateQuery HardForkBlock (': * ByronBlock (': * (ShelleyBlock (TPraos StandardCrypto) (ShelleyEra StandardCrypto)) (': * (ShelleyBlock (TPraos StandardCrypto) (AllegraEra StandardCrypto)) (': * (ShelleyBlock (TPraos StandardCrypto) (MaryEra StandardCrypto)) (': * (ShelleyBlock (TPraos StandardCrypto) (AlonzoEra StandardCrypto)) (': * (ShelleyBlock (Praos StandardCrypto) (BabbageEra StandardCrypto)) (': * (ShelleyBlock (Praos StandardCrypto) (ConwayEra StandardCrypto)) ('[] *)))))))) Query (BlockQuery (HardForkBlock (': * ByronBlock (': * (ShelleyBlock (TPraos StandardCrypto) (ShelleyEra StandardCrypto)) (': * (ShelleyBlock (TPraos StandardCrypto) (AllegraEra StandardCrypto)) (': * (ShelleyBlock (TPraos StandardCrypto) (MaryEra StandardCrypto)) (': * (ShelleyBlock (TPraos StandardCrypto) (AlonzoEra StandardCrypto)) (': * (ShelleyBlock (Praos StandardCrypto) (BabbageEra StandardCrypto)) (': * (ShelleyBlock (Praos StandardCrypto) (ConwayEra StandardCrypto)) ('[] *))))))))))) ServerAgency TokQuerying BlockQuery (QueryIfCurrent (QS (QS (QS (QS (QS (QS (QZ GetCurrentPParams))))))))) (DeserialiseFailure 5 "Size mismatch when decoding Record RecD.\nExpected 31, but found 30.")
```

## 5. Analyze controls

Because initialization cannot pass the node query, two valid Conway envelopes
were assembled outside Git from the release's checked-in initialized example.
Both passed the v0.2.0.0 JSON decoder. Their only material contract difference
was the audit escrow contract versus `"close"`.

Commands (each bounded by 1,200 seconds):

```bash
timeout 1200 marlowe-cli run analyze \
  --testnet-magic 42 \
  --socket-path /home/tohung/stage05-infra/private-testnet/socket/node1/sock \
  --marlowe-file /home/tohung/stage05-infra/results/escrow-marlowe.json \
  --preconditions --roles --tokens --maximum-value --minimum-utxo \
  --execution-cost --transaction-size --best --verbose

timeout 1200 marlowe-cli run analyze \
  --testnet-magic 42 \
  --socket-path /home/tohung/stage05-infra/private-testnet/socket/node1/sock \
  --marlowe-file /home/tohung/stage05-infra/results/minimal-close-marlowe.json \
  --preconditions --roles --tokens --maximum-value --minimum-utxo \
  --execution-cost --transaction-size --best --verbose
```

Escrow result, exit code 1, wall time 0.515 seconds:

```text
marlowe-cli: DecoderFailure (LocalStateQuery HardForkBlock (': * ByronBlock (': * (ShelleyBlock (TPraos StandardCrypto) (ShelleyEra StandardCrypto)) (': * (ShelleyBlock (TPraos StandardCrypto) (AllegraEra StandardCrypto)) (': * (ShelleyBlock (TPraos StandardCrypto) (MaryEra StandardCrypto)) (': * (ShelleyBlock (TPraos StandardCrypto) (AlonzoEra StandardCrypto)) (': * (ShelleyBlock (Praos StandardCrypto) (BabbageEra StandardCrypto)) (': * (ShelleyBlock (Praos StandardCrypto) (ConwayEra StandardCrypto)) ('[] *)))))))) Query (BlockQuery (HardForkBlock (': * ByronBlock (': * (ShelleyBlock (TPraos StandardCrypto) (ShelleyEra StandardCrypto)) (': * (ShelleyBlock (TPraos StandardCrypto) (AllegraEra StandardCrypto)) (': * (ShelleyBlock (TPraos StandardCrypto) (MaryEra StandardCrypto)) (': * (ShelleyBlock (TPraos StandardCrypto) (AlonzoEra StandardCrypto)) (': * (ShelleyBlock (Praos StandardCrypto) (BabbageEra StandardCrypto)) (': * (ShelleyBlock (Praos StandardCrypto) (ConwayEra StandardCrypto)) ('[] *))))))))))) ServerAgency TokQuerying BlockQuery (QueryIfCurrent (QS (QS (QS (QS (QS (QS (QZ GetCurrentPParams))))))))) (DeserialiseFailure 5 "Size mismatch when decoding Record RecD.\nExpected 31, but found 30.")
```

Minimal `"close"` result, exit code 1, wall time 0.480 seconds:

```text
marlowe-cli: DecoderFailure (LocalStateQuery HardForkBlock (': * ByronBlock (': * (ShelleyBlock (TPraos StandardCrypto) (ShelleyEra StandardCrypto)) (': * (ShelleyBlock (TPraos StandardCrypto) (AllegraEra StandardCrypto)) (': * (ShelleyBlock (TPraos StandardCrypto) (MaryEra StandardCrypto)) (': * (ShelleyBlock (TPraos StandardCrypto) (AlonzoEra StandardCrypto)) (': * (ShelleyBlock (Praos StandardCrypto) (BabbageEra StandardCrypto)) (': * (ShelleyBlock (Praos StandardCrypto) (ConwayEra StandardCrypto)) ('[] *)))))))) Query (BlockQuery (HardForkBlock (': * ByronBlock (': * (ShelleyBlock (TPraos StandardCrypto) (ShelleyEra StandardCrypto)) (': * (ShelleyBlock (TPraos StandardCrypto) (AllegraEra StandardCrypto)) (': * (ShelleyBlock (TPraos StandardCrypto) (MaryEra StandardCrypto)) (': * (ShelleyBlock (TPraos StandardCrypto) (AlonzoEra StandardCrypto)) (': * (ShelleyBlock (Praos StandardCrypto) (BabbageEra StandardCrypto)) (': * (ShelleyBlock (Praos StandardCrypto) (ConwayEra StandardCrypto)) ('[] *))))))))))) ServerAgency TokQuerying BlockQuery (QueryIfCurrent (QS (QS (QS (QS (QS (QS (QZ GetCurrentPParams))))))))) (DeserialiseFailure 5 "Size mismatch when decoding Record RecD.\nExpected 31, but found 30.")
```

The identical post-decode failure classifies the result as protocol/API
incompatibility, not contract-specific format failure.

## 6. Newer binary and source requirements

The GitHub releases API was queried with `per_page=100`. Every returned asset
whose name contained `marlowe-cli` was:

```text
runtime@v1.0.0          2024-05-05  marlowe-cli              46572360
runtime@v0.0.6          2023-12-12  marlowe-cli              38496392
marlowe-cli@v0.1.0.0    2023-09-27  marlowe-cli              52846136
runtime@v0.0.5          2023-09-27  marlowe-cli              52846136
marlowe-cli@v0.0.12.0   2023-08-11  marlowe-cli              49772808
runtime@v0.0.4          2023-08-11  marlowe-cli              49772808
runtime@v0.0.2          2023-06-16  marlowe-cli.x86_64-linux 48766408
```

No newer binary was available. Read-only shallow source checkouts outside Git
showed:

```text
release runtime@v1.0.0 commit: 2c0ad60ad2caabb7865b6dda56f7ec478f8637e7
release marlowe-cli version:    0.2.0.0
release cardano-api constraint: ^>=8.39.2.0
release compiler-nix-name:     ghc928

main commit:                   99f432d8ef9dbd1b52b7fa089254de15913b490f
main marlowe-cli version:      0.2.0.0
main cardano-api constraint:   ^>=9.2
main compiler-nix-name:        ghc928
main Hackage index state:      2024-08-07T14:18:16Z
main CHaP index state:         2024-08-28T06:44:16Z
```

No Cabal, GHC, Nix, or source build was started.

## Stage 0.6 correction note — 2026-09-28

The commands and failures above remain accurate historical evidence. Their
scope was corrected after inspecting the implementation: `marlowe-cli run
analyze` checks ledger limits and state preconditions and is not the
SBV/Z3-based Marlowe safety analyzer. The Conway protocol-parameter decoding
failure blocks that ledger check only; it does not block independent SMT
analysis for Node 3. See “Correction (Stage 0.6)” in
[stage0-feasibility-report.md](stage0-feasibility-report.md).
