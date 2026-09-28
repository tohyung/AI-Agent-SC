# Stage 0 infrastructure feasibility report

Date: 2026-09-27 (Asia/Bangkok)

Scope: feasibility only. No file under `marlowe_ai_agent/` was changed and no
binary, Nix store, or generated testnet artifact was added to Git. Detailed
command evidence is in [stage0-command-log.md](stage0-command-log.md).

## Direct answers

### 1. Does this Codex environment retain state?

**Yes: this particular task is attached to the user's persistent Windows host,
not an ephemeral OpenAI-hosted sandbox.** Files are ordinary host files rather
than a per-task container volume. Persistence across turns and dates was
observed directly; persistence across an actual reboot was not performed as
part of this bounded test, though it follows normal host-filesystem semantics
unless the user or an external cleanup process removes the files. Evidence:

- The task operates on `D:\code\marlowe_ai_agent` and could read benchmark
  outputs created on 2026-09-25 and 2026-09-26 when checked on 2026-09-27.
- A marker was created outside Git at
  `C:\Users\Admin\.codex\stage0-cardano-persistence-marker.txt` and remained
  readable after the infrastructure experiments.
- Docker images, WSL2 files, and downloads are stored on the user's machine.

There is no separate Codex persistent-volume quota visible for this local
execution mode. The practical limits are the host filesystems: at measurement
time C: had 17.27 GB free of 225.25 GB, and D: had 93.59 GB free of 250 GB.
This conclusion applies to this local Codex desktop environment, not to every
Codex product mode. Official OpenAI documentation says OpenAI-hosted sandbox
files persist only while the sandbox exists and an idle sandbox can be deleted
after one hour, whereas self-hosted environments use compute and files managed
by the user:

- [OpenAI-hosted sandbox lifetime](https://developers.openai.com/api/docs/guides/agents-api/environments/openai-hosted)
- [Self-hosted environments](https://developers.openai.com/api/docs/guides/agents-api/environments/self-hosted)

### 2. Can cardano-node and marlowe-cli be installed or built here?

**They can be installed and executed here using official prebuilt artifacts;
a Nix source build was not feasible under the non-interactive permission
boundary tested.**

- Official cardano-node Docker image 11.1.2 pulled successfully in 32.05 s.
  It transferred 282,046,228 compressed bytes, uses 1.381 GB locally, and
  `cardano-node --version` ran successfully.
- Official Windows release 11.1.2 downloaded in 53.81 s (487,979,059 bytes),
  matched its published SHA-256, extracted in 4.42 s to 2,123,177,265 bytes,
  and successfully ran `cardano-node`, `cardano-cli`, and `cardano-testnet`.
- Official Marlowe release binary downloaded in 7.15 s (46,572,360 bytes).
  Under WSL2 it reported `marlowe-cli 0.2.0.0`; both `--version` and
  `run analyze --help` exited successfully.
- The Nix installer downloaded Nix 2.35.2 (25.87 MiB) but required sudo to
  create `/nix`. The normal WSL user has no passwordless sudo, so the attempt
  was stopped. `/nix` was not created. Steps 4 and 5 were therefore skipped;
  no honest source-build time or cache hit ratio can be reported.

Total directly observed network transfer for the successful artifacts was at
least about 816.6 MB (282.0 MB Docker layers + 488.0 MB Cardano ZIP + 46.6 MB
Marlowe binary), plus 25.9 MiB for the aborted Nix attempt and small metadata.

### 3. Is there a lighter route than a Nix build?

**Yes, and it was verified end to end. Use current official GitHub releases or
GHCR, not the old Docker Hub path.**

- Current cardano-node releases publish Linux/macOS/Windows archives and link
  `ghcr.io/intersectmbo/cardano-node:11.1.2`:
  [cardano-node releases](https://github.com/IntersectMBO/cardano-node/releases),
  [GHCR package](https://github.com/IntersectMBO/cardano-node/pkgs/container/cardano-node).
- `inputoutput/cardano-node:latest` on Docker Hub failed with “repository does
  not exist or may require login”; it should no longer be recommended.
- The latest GitHub release returned by `marlowe-lang/marlowe-cardano` includes
  a directly runnable Linux `marlowe-cli` asset:
  [Marlowe releases](https://github.com/marlowe-lang/marlowe-cardano/releases).

The Marlowe binary is older (release published 2024-05-05) even though it is
the latest release asset exposed by the repository. Its required
`run analyze --socket-path` syntax exists, but protocol compatibility with a
current 11.1.2 node was not proven by this Stage 0 run.

## Step results

| Step | Status | Measured result | Time |
|---|---|---|---:|
| 1. Persistence | Complete | Local Windows host is persistent; marker outside Git created; no Codex volume quota, host disk limits apply | < 5 min |
| 2. Lighter route | Complete | Old Docker Hub path failed; official GHCR image, Windows Cardano release, and Linux Marlowe release all downloaded and ran | GHCR 32.05 s; Cardano ZIP 53.81 s; Marlowe 7.15 s |
| 3. Install Nix | Blocked cleanly | Download succeeded; installer stopped at interactive sudo needed to create `/nix`; no partial installation | ~30 s |
| 4. Cache dry-run | Not eligible | Nix unavailable. Current IOG guide still specifies `https://cache.iog.io` and its Hydra public key | 0 |
| 5. Nix build | Not eligible | Gate from step 4 was not met; no build was started | 0 |
| 6. Run binaries | Complete for prebuilt route | Marlowe version/help passed; Cardano private 1-node testnet forged its first block and answered `query tip` at 100% sync | First block ~85.4 s after node start |

## Environment

| Property | Measured value |
|---|---|
| Host OS | Windows 11 Home 10.0.26200, 64-bit |
| Linux layer | WSL2, Ubuntu 26.04.1 LTS, kernel 6.18.33.2 |
| CPU | AMD Ryzen 7 8845H, 16 logical CPUs |
| RAM | 13.81 GB |
| C: | 225.25 GB total; 17.27 GB free after experiments |
| D: | 250.00 GB total; 93.59 GB free |
| WSL root filesystem | 1007 GB virtual capacity; 954 GB reported free |
| Docker | Desktop Linux engine 29.4.1 |

The latest cardano-node 11.1.2 release states 8 GB RAM for the on-disk backend
(pending confirmation), 24 GB for in-memory, and 300 GB free storage (350 GB
recommended for future growth). This host meets the CPU requirement and only
the on-disk RAM figure, but neither C: nor D: currently meets the mainnet
storage recommendation. The small private testnet itself used less than 0.4 MB
after the short run. See the
[cardano-node 11.1.2 release](https://github.com/IntersectMBO/cardano-node/releases/tag/11.1.2).

## Private testnet evidence

The official Windows bundle included `cardano-testnet`. A one-pool network was
started with testnet magic 42, 0.1-second slots, and active-slots coefficient
0.2. The generated genesis intentionally started 84.54 seconds in the future.
The first block was forged about 85.4 seconds after node start. A live query
returned Conway era, block 24, slot 133, and `syncProgress: 100.00`. All node
processes were stopped afterward.

The current Cardano Developer Portal describes a local devnet as a private,
fully configurable network intended for fast iteration, CI, and offline work:
[testnets and devnets](https://developers.cardano.org/docs/get-started/testnets-and-devnets/).

## Architecture recommendation

**Recommendation: a B+C hybrid. Run the blockchain toolchain on a persistent
user-controlled Linux environment, using official prebuilt artifacts rather
than Nix builds.**

This local Codex task is persistent, so ephemeral storage is not the blocker.
The blockers are operational separation, cross-OS socket semantics, available
disk, and reproducibility:

1. The verified `marlowe-cli` asset is a Linux binary running under WSL2.
2. The verified native Windows node exposes a Windows named pipe
   (`\\.\pipe\.\socket\node1\sock`), not a Unix socket. A Linux Marlowe CLI
   should not be assumed to consume that named pipe.
3. For a dependable `--socket-path`, run `cardano-node` and `marlowe-cli` in
   the same WSL2/Linux host, container composition, or dedicated Linux server,
   with a shared Unix-socket volume.
4. The current C: free space is too low for a full node, and neither host drive
   meets the published 300 GB mainnet figure. A private testnet remains small
   and practical.

Therefore:

- For local research/private-network deployment, option C is practical on this
  persistent machine using prebuilt releases, preferably consolidated inside
  WSL2/Linux.
- For an always-on node or any public-network synchronization, option B is
  safer: use a dedicated persistent Linux machine/server with sufficient disk.
- The Python agent should receive an explicit socket path (and network magic)
  through configuration. It should not own node installation or lifecycle.

## User-run setup recommended for the next stage

1. Provision Ubuntu Linux (native server or WSL2) with at least 4 CPU cores,
   16 GB RAM for development, and a dedicated SSD. For mainnet, allocate at
   least the release's 300 GB requirement plus growth headroom; 500 GB is a
   safer operational target. For a private testnet, tens of GB are ample.
2. Download the official cardano-node archive matching the target OS from the
   [IntersectMBO releases](https://github.com/IntersectMBO/cardano-node/releases)
   and verify it against `cardano-node-<version>-sha256sums.txt`. Expect roughly
   0.5 GB download and about 2.1 GB extracted for the measured Windows build;
   Linux sizes differ.
3. Download the official `marlowe-cli` release asset from
   [marlowe-lang/marlowe-cardano releases](https://github.com/marlowe-lang/marlowe-cardano/releases),
   mark it executable, and confirm `marlowe-cli --version` plus
   `marlowe-cli run analyze --help`. The measured download took 7.15 seconds.
4. Put both binaries on the same Linux PATH. Keep the node socket on a native
   Linux filesystem or a Docker volume shared with the Marlowe process.
5. For a private network, use the bundled `cardano-testnet` to create/start a
   one-pool network first. Set `CARDANO_CLI` and `CARDANO_NODE` explicitly if
   the tool cannot discover sibling binaries. Expect about 85 seconds to the
   first block with the measured defaults, dominated by the generated genesis
   start delay.
6. Verify connectivity with `cardano-cli query tip --testnet-magic <magic>
   --socket-path <socket>` before invoking Marlowe.
7. Run a real `marlowe-cli run analyze` against a known contract and the same
   socket. This compatibility test is the required next gate before Node 3 is
   integrated.
8. If Nix is still desired, perform it interactively on the Linux host with
   sudo available. Follow the current
   [IOG Nix setup guide](https://github.com/input-output-hk/iogx/blob/main/doc/nix-setup-guide.md):
   enable flakes, configure `https://cache.iog.io` and its published key, then
   run a dry-run before any build. Stop if Nix proposes building GHC locally.

## Artifacts deliberately kept outside Git

```text
C:\Users\Admin\.codex\stage0-cardano-persistence-marker.txt
C:\Users\Admin\.codex\stage0-infra\marlowe-cli
C:\Users\Admin\.codex\stage0-infra\cardano-node-11.1.2-win-amd64.zip
C:\Users\Admin\.codex\stage0-infra\cardano-node-11.1.2-win\
C:\Users\Admin\.codex\stage0-infra\private-testnet-2\
Docker image: ghcr.io/intersectmbo/cardano-node:11.1.2
```

These consume approximately 2.66 GB of ordinary files plus 1.381 GB in Docker
image storage. They were not staged for Git.

## Stage 0.5: marlowe-cli run analyze compatibility

### Correction (Stage 0.6 — 2026-09-28)

The experiment and Conway decoding error below are real, but the original
gate overstated their scope. Source inspection at `marlowe-cardano` main commit
`99f432d8ef9dbd1b52b7fa089254de15913b490f` shows that `marlowe-cli run
analyze` is a **ledger-limit and state-precondition checker, not the Marlowe
SMT safety analyzer**. Its implementation imports
`Language.Marlowe.Analysis.Safety.{Ledger,Transaction,Types}`, queries protocol
parameters, and checks such properties as value size, minimum UTxO, execution
units, transaction size, role/token name length, and state preconditions. The
`marlowe-cli` package has no `sbv` dependency.

The SMT entry point is instead
`Language.Marlowe.Analysis.FSSemantics.warningsTraceWithState` (or
`warningsTraceCustom`), in the `marlowe` package whose Cabal file depends on
`sbv ^>=9.2`. It accepts a slot length, Core V1 contract, and optional state,
and invokes Z3 without a cardano-node connection. The source confirms
`Right Nothing` means no warning and `Right (Just ...)` contains an interpreted
counterexample. Direct callers were found in `marlowe-test` and
`marlowe-contracts`; the claimed `marlowe-symbolic` service was not present in
this checkout and therefore remains **not verified** here.

Consequently, the v0.2.0.0/Node 11.1.2 mismatch blocks only the optional
ledger-limit check before deployment. It does **not** block independent SMT
safety analysis or Node 3. Whether that SMT path builds, accepts the agent's
Core V1 JSON, and completes within the required resource limits is the subject
of Stage 0.6.

### Verdict

**Blocked by a protocol/API compatibility mismatch.** The released
`marlowe-cli 0.2.0.0` cannot decode the Conway protocol-parameter response from
`cardano-node 11.1.2`. The failure occurs after a valid Marlowe file is decoded
and while `run analyze` queries `GetCurrentPParams` through the live Unix
socket:

```text
DeserialiseFailure 5 "Size mismatch when decoding Record RecD.\nExpected 31, but found 30."
```

This is not a contract-specific or raw-JSON-format failure:

- The audit contract from
  `marlowe_ai_agent/bench/audit/en-escrow_2party-L1-010-full.json` was exported
  outside Git and embedded in a structurally valid Conway `marlowe-file`.
- A second structurally valid file used only the minimal contract `"close"`.
- Both files passed Aeson decoding and then failed at the same node query, with
  the same complete error and exit code 1 in about 0.5 seconds.
- `run initialize` failed at that same protocol-parameter query before it
  could generate a Marlowe file, independently confirming the boundary.

The complete evidence and exact commands are in
[stage05-command-log.md](stage05-command-log.md).

### Linux/node setup actually tested

The exact official Linux asset
`cardano-node-11.1.2-linux-amd64.tar.gz` was downloaded into the WSL home
directory. Its 233,771,973-byte archive matched the published SHA-256:

```text
fd872fbeb9cc663e67088ca47ed01aa01d18a77d7dbee694e2444bb23d833759
```

The extracted binaries reported `cardano-node 11.1.2`, `cardano-cli
11.2.3.0`, and a bundled `cardano-testnet` built against `cardano-api
11.6.0.0`. The previously verified Marlowe binary was copied into the same WSL
filesystem and retained SHA-256
`464f14957aafeefc86aa868074e200f700aefc070f1ecb32466d999110e58939`.

A one-pool private network used magic 42 and a 0.2-second slot length. Its
node-to-client endpoint was verified as an actual Linux socket:

```text
/home/tohung/stage05-infra/private-testnet/socket/node1/sock: socket
mode=socket permissions=srwxr-xr-x
```

`cardano-cli query tip` succeeded over that socket and returned Conway era and
`syncProgress: 100.00`. Thus the failure is not caused by the earlier
cross-OS Windows named-pipe problem. The testnet and CLI ran in the same WSL
distribution against the same native Unix socket. The node/testnet processes
were stopped after the experiment; the generated files remain outside Git in
`/home/tohung/stage05-infra/`.

### Marlowe file initialization and controls

The v0.2.0.0 help establishes that `run analyze` requires a JSON file holding
both state and contract, not a bare contract. `run initialize` is the supplied
initializer, but on this node it failed before writing output because it also
queries the current protocol parameters.

For the two controlled `analyze` executions, the wrapper and validator fields
came from the release tag's checked-in
`marlowe-cli/doc/simple-1.marlowe`. The wrapper was set to Conway, the audit
contract or `"close"` was substituted, and the generated template state was
used. An initially missing `openRolesValidator` field in that older checked-in
sample was filled from its roles validator so the v0.2.0.0 decoder would accept
the file. The subsequent node-query failure in both cases proves that contract
parsing completed.

### Upstream release and source-build assessment

GitHub's complete release listing (100 releases requested) exposed no newer
prebuilt `marlowe-cli` than the 46,572,360-byte asset in `runtime@v1.0.0`,
published 2024-05-05. That asset is the tested v0.2.0.0 binary. The previous
assets were `runtime@v0.0.6`, `marlowe-cli@v0.1.0.0`, and older releases.

The release-tag source pins `cardano-api ^>=8.39.2.0` and GHC 9.2.8. The
current `main` at commit
`99f432d8ef9dbd1b52b7fa089254de15913b490f` still labels marlowe-cli as
0.2.0.0, pins GHC 9.2.8, and raises the dependency only to `cardano-api
^>=9.2`. Its Cabal project also depends on the Intersect CHaP repository and
fixed Hackage/CHaP index states. By contrast, the tested cardano-node bundle's
`cardano-testnet` reports `cardano-api 11.6.0.0`. A source build was deliberately
not attempted; the inspected dependency gap does not justify spending build
time without an upstream compatibility branch or a deliberate Cardano-version
alignment plan.

### Gate for the next stage

Proceed to Stage 0.6 using the node-independent
`Language.Marlowe.Analysis.FSSemantics` SMT path for Node 3. Do not wait for a
Cardano 11-compatible `marlowe-cli`: no such released binary was found.

The separate ledger-limit check should be postponed until deployment work and
run only in an isolated, version-pinned devnet. Source pins identify two
candidates that still require testing: cardano-node 8.9.0 with the existing
`runtime@v1.0.0` binary (`cardano-api ^>=8.39.2.0`), or cardano-node 9.1.1 with
a CLI built from `runtime@v1.1.0-rc1`/the same commit as current main
(`cardano-api ^>=9.2`). Neither combination was executed in Stage 0.5 or this
correction, so compatibility remains **not verified**.

## Follow-up

- [Stage 0.6 — standalone Marlowe SMT analysis](stage06-smt-report.md)
- [Stage 0.7 — packaged and verified Marlowe SMT analysis](stage07-smt-packaging-report.md)
