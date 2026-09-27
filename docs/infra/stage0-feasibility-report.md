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
