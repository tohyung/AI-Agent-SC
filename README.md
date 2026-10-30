# Marlowe AI Agent

Turns a natural-language request into a Marlowe Core V1 contract candidate and
collects evidence about it. One route:

requirement → Stage 2B intent extraction → Stage 2C explicit approval →
LLM-generated Core V1 candidate → structural lint and pinned SMT → reference
comparison → bounded exploration, oracles and property records →
transaction-size check when a ledger is configured.

A generated contract stays a candidate (`CANDIDATE_ONLY`). Reaching a gate does
not authorize deployment; testnet and deployment are disabled.

## Layout

```text
main.py                CLI entry point
research/              all runtime code (package name kept until the full rename)
  architecture/        artifacts, ports, status, cli_runner, cli, orchestrator, manifest.json
  marlowe_core/        Core V1 AST builders, structural validator, graph lint, SMT finding mapper
  integrations/        model transport and replay, SMT gate/driver, reference driver, WSL
  stage2a/             frozen research corpus and protocol (stage2a-v1)
  stage2b/             intent extraction: core v4 validator, projector, extractor; A2 fact builder
  stage2c/             review and explicit acceptance
  stage3/              contract generation, reference comparison, profile compilers
  stage4/              bounded exploration and oracles
  stage5/              property observation store (SQLite)
  final_validation/    marlowe-cli transaction-size adapter
  experiments/         evaluation arms, scorer, replay, roleplay runner, batch tooling
dataset/               frozen 100-case benchmark and its offline validator
tests/                 all tests, mirroring research/ plus dataset/
tools/marlowe_smt/     pinned Haskell SMT analyzer and reference executor
docs/HISTORY.md        research history (one file)
docs/A2.md             current work: Stage 2B fact-draft design and evaluation protocol
docs/papers/           papers and slides
runs/                  local run data, not in git
```

## Run

```powershell
python -m pip install -r requirements.txt
python main.py
```

The CLI reads the model endpoint and key from `.env` at the repository root
(see `.env.example`). Run without `--prompt` for an interactive session, or
pass `--prompt "..." --interactive`. Noninteractive runs stop when
clarification or explicit intent approval is needed. Stage 2B uses core v4 by
default; `--core-schema-version v3|v2` only reproduces older runs.

Defaults: `--max-iterations 8`, `--max-llm-calls 40`, `--stop-on-stall 2`. The
model may regenerate a candidate after lint or SMT findings but cannot change
an approved intent. Each run writes `runs/<timestamp>.jsonl` (requirement
history, stage executions, artifacts, sanitized call metadata; no keys or raw
chain-of-thought); `--run-log-dir` and `--no-run-log` control it.

`--expectation PATH` supplies an independent behavior scenario; the CLI asks
for confirmation before using it for reference comparison and exploration.
The pinned SMT and reference binaries are required for their gates; an
unavailable driver is never turned into a pass or a business question. The
ledger adapter needs every `MARLOWE_LEDGER_*` setting, a synchronized node and
pinned binaries; it measures transaction size and never signs or submits.

## Property observations (Stage 5)

Oracle observations go to `runs/property-dataset.sqlite3`
(`--property-dataset PATH`, `--no-property-dataset`). They are observations,
not training labels: export requires a matching pinned-reference replay, two
consenting reviewers who agree, and an explicit data-use grant; simulated runs
are never exported. The store may contain names and amounts; keep it local.

```bash
python -m research.stage5.dataset audit
python -m research.stage5.dataset ingest-run runs/<run-file>.jsonl
python -m research.stage5.dataset replay <example_id> --binary <reference-binary>
python -m research.stage5.dataset review <example_id> --reviewer <id> --label SATISFIED --rationale "..." --consent-for-training
python -m research.stage5.dataset authorize-use <example_id> --grantor <id> --rationale "..."
python -m research.stage5.dataset export runs/property-reviewed.jsonl
```

## Evaluation and experiments

```bash
python -m research.experiments.stage2b_eval --arm BASE --out-dir runs/eval/<arm-dir>
python -m research.experiments.stage2b_score runs/eval/<arm-dir>
python -m research.experiments.stage2b_replay --output runs/replay/<file>.json
```

The protocol, metrics and the dev/test split are in [docs/A2.md](docs/A2.md).
Finished run folders are bundled 20 cases per file with
`python -m research.experiments.run_bundles bundle runs/<batch>`; `extract`
restores the original files.
Stage 2A commands: `python research/stage2a/foundation.py validate|stats`, and
`python research/stage2a/verify_freeze.py research/stage2a/freeze/stage2a-v1.manifest.json`
to check the frozen corpus hashes.

## Tests

```powershell
python -m pytest -q
uvx ruff check --select F401,F841
```

Tests that need the WSL reference binary or a ledger node skip unless their
environment variables are set; a skip is not a pass.
