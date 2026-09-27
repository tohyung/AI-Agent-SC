# Stage 0 command log

Recorded on 2026-09-27 in the local Codex desktop environment. Commands were
run from PowerShell unless prefixed with `wsl -d Ubuntu`. Secrets and `.env`
files were not read or printed.

## 1. Host and persistence marker

```powershell
Get-CimInstance Win32_OperatingSystem
Get-CimInstance Win32_Processor
Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:' OR DeviceID='D:'"
```

Relevant output:

```text
OS: Microsoft Windows 11 Home 10.0.26200, 64-bit
CPU: AMD Ryzen 7 8845H w/ Radeon 780M Graphics
Logical CPUs: 16
RAM: 13.81 GB
C: 225.25 GB total, 17.27 GB free after the experiments
D: 250.00 GB total, 93.59 GB free
```

The marker was created outside the repository at
`C:\Users\Admin\.codex\stage0-cardano-persistence-marker.txt`:

```text
created_at=2026-09-27T22:39:32.5612668+07:00
host=Windows 11 Home
purpose=Stage 0 persistence check outside git repository
```

The same local filesystem also retained benchmark outputs from 2026-09-25 and
2026-09-26 when inspected on 2026-09-27.

## 2. Tool inventory and Docker

```text
docker=C:\Program Files\Docker\Docker\resources\bin\docker.exe
wsl=C:\WINDOWS\system32\wsl.exe
nix=NOT_FOUND
nix-env=NOT_FOUND
cabal=NOT_FOUND
ghc=NOT_FOUND
cardano-node=NOT_FOUND
cardano-testnet=NOT_FOUND
marlowe-cli=NOT_FOUND
WSL default distribution: Ubuntu; default version: 2
```

Docker CLI was installed but the daemon was initially stopped:

```text
failed to connect to the docker API at
npipe:////./pipe/dockerDesktopLinuxEngine
```

After starting Docker Desktop in the background, `docker info` became ready in
0.9 seconds and reported server version 29.4.1.

The obsolete Docker Hub path did not work:

```powershell
docker pull inputoutput/cardano-node:latest
```

```text
pull access denied for inputoutput/cardano-node, repository does not exist or
may require 'docker login'
exit: 1; elapsed: 1.75 seconds
```

The image linked by the current cardano-node 11.1.2 release did work:

```powershell
docker pull ghcr.io/intersectmbo/cardano-node:11.1.2
docker run --rm --entrypoint cardano-node `
  ghcr.io/intersectmbo/cardano-node:11.1.2 --version
```

```text
Digest: sha256:6365403f44713d0a046865fb0466503ef207b71beae1b1ffece7f4399356db9f
pull exit: 0; elapsed: 32.05 seconds
linux/amd64 compressed layers: 282,046,228 bytes
Docker unique image size: 1.381 GB
cardano-node 11.1.2 - linux-x86_64 - ghc-9.6
git rev fef83fed01d7926f3de83b3b917be5a4a48768b5
```

The image contains `cardano-node` and `cardano-cli`, but no
`cardano-testnet` executable.

## 3. Official Marlowe binary

The GitHub API for the latest `marlowe-lang/marlowe-cardano` release returned:

```text
tag: runtime@v1.0.0
published: 2024-05-05
asset: marlowe-cli
asset size: 46,572,360 bytes
```

Download command and result:

```powershell
curl.exe -L --fail -o C:\Users\Admin\.codex\stage0-infra\marlowe-cli `
  https://github.com/marlowe-lang/marlowe-cardano/releases/download/runtime%40v1.0.0/marlowe-cli
```

```text
elapsed: 7.15 seconds
bytes: 46,572,360
SHA-256: 464F14957AAFEEFC86AA868074E200F700AEFC070F1ECB32466D999110E58939
```

Execution through Ubuntu WSL2:

```text
Linux 6.18.33.2-microsoft-standard-WSL2 x86_64
Ubuntu 26.04.1 LTS
marlowe-cli 0.2.0.0
```

`marlowe-cli run analyze --help` exited 0 and showed these required inputs:

```text
Usage: marlowe-cli run analyze (--mainnet | --testnet-magic INTEGER)
                               --socket-path SOCKET_FILE
                               --marlowe-file MARLOWE_FILE
```

It also listed `--preconditions`, `--roles`, `--tokens`, `--maximum-value`,
`--minimum-utxo`, `--execution-cost`, `--transaction-size`, `--best`, and
`--verbose`.

## 4. Nix installation attempt

WSL2 used systemd, had 954 GB free in its virtual filesystem, and `/nix` did
not exist. The normal user did not have passwordless sudo.

```powershell
wsl -d Ubuntu -- bash -lc \
  'timeout 300 sh -c "curl -L --fail --show-error https://nixos.org/nix/install | sh -s -- --no-daemon --yes"'
```

Relevant output after approximately 30 seconds:

```text
downloaded installer: 4,499 bytes
downloaded Nix 2.35.2 x86_64-linux tarball: 25.87 MiB
performing a single-user installation of Nix...
directory /nix does not exist; creating it by running
'mkdir -m 0755 /nix && chown tohung /nix' using sudo
```

The command waited for an interactive sudo password and was interrupted. A
follow-up check reported `/nix-not-created` and no `nix` command. No root
workaround was attempted. Consequently cache dry-run and source builds were not
eligible to run.

## 5. Official cardano-node Windows release

GitHub API reported cardano-node release 11.1.2 with an official Windows ZIP:

```text
cardano-node-11.1.2-win-amd64.zip
release asset size: 487,979,059 bytes
```

Measured download and checksum:

```text
elapsed: 53.81 seconds
downloaded: 487,979,059 bytes
SHA-256: e54f133771c40e98b65f90571f6e0284813d1c6a295708f545b49c1a9e1f5333
expected: e54f133771c40e98b65f90571f6e0284813d1c6a295708f545b49c1a9e1f5333
```

Extraction took 4.42 seconds and occupied 2,123,177,265 bytes. The archive
contained `cardano-node.exe`, `cardano-cli.exe`, and `cardano-testnet.exe`.

```text
cardano-node 11.1.2 - mingw32-x86_64 - ghc-9.12
cardano-cli 11.2.3.0 - mingw32-x86_64 - ghc-9.12
cardano-testnet version:
  cardano-node 11.1.1 - mingw32-x86_64 - ghc-9.12
  built against cardano-api 11.6.0.0
  built against cardano-cli 11.2.3.0
```

## 6. Private testnet

The first launch failed in 0.57 seconds because the release binary did not
automatically locate its sibling `cardano-cli.exe`:

```text
Could not find plan.json in dist-newstyle/cache/plan.json.
Otherwise define CARDANO_CLI and have it point to the executable you want.
```

The second launch set `CARDANO_CLI`, `CARDANO_NODE`, and `PATH` to the release
`bin` directory:

```powershell
cardano-testnet.exe cardano --num-pool-nodes 1 --testnet-magic 42 `
  --slot-length 0.1 --active-slots-coeff 0.2 `
  --output-dir C:\Users\Admin\.codex\stage0-infra\private-testnet-2
```

The node started at approximately `2026-09-27T15:46:17.45Z`. Its generated
genesis configured a start 84.54 seconds in the future. The first block was
forged at `2026-09-27T15:47:42.8178853Z`, approximately 85.4 seconds after node
start:

```text
Forge.Loop.ForgedBlock
blockNo: 0
slot: 8
block: 6b49b2399ce59835408d2a41a305e8b88e89cb967f357103487368be98ec3ab1
```

The Windows socket was `\\.\pipe\.\socket\node1\sock`. A live query returned:

```json
{
  "block": 24,
  "epoch": 0,
  "era": "Conway",
  "slot": 133,
  "syncProgress": "100.00"
}
```

After Ctrl-C, checks found no `cardano-node` or `cardano-testnet` process.
The generated testnet directory occupied 389,890 bytes.

Docker Desktop was then stopped with `docker desktop stop`, restoring its
initial stopped state. A follow-up `docker info` failed on the absent engine
pipe as expected; the downloaded image remains cached on disk.
