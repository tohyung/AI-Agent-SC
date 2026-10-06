# Marlowe AI Agent

The supported CLI runs one assurance route: requirement -> Stage 2B intent
extraction -> explicit Stage 2C approval -> LLM-generated Marlowe Core V1
candidate -> structural lint and pinned SMT -> reference comparison -> bounded
exploration, oracles and property records -> ledger-size check when configured.
There is no legacy Node 1/2/3 mode or deterministic profile-compiler fallback in
the user-facing CLI. A generated contract remains a candidate; reaching a gate
does not authorize deployment.

## Run

From `marlowe_ai_agent/`:

```powershell
python -m pip install -r .\requirements.txt
python .\main.py
```

The CLI reads the model and endpoint configuration from `.env` through
`research.integrations.model_transport.ModelTransport`. Run without `--prompt`
for an interactive session, or use `--interactive` with a supplied prompt.
Noninteractive calls stop when clarification or explicit intent approval is
needed.
The main route requests Stage 2B Core V3 by default; use
`--core-schema-version v2` only when reproducing a V2 run. A model response
with the wrong core version is repaired or blocked, never silently downgraded.

```powershell
python .\main.py --prompt "Alice ký quỹ 250 ADA cho Bob ..." --interactive --out .\result.json
```

`--max-iterations` defaults to 8, `--max-llm-calls` to 40 and
`--stop-on-stall` to 2. The model may regenerate a candidate after structural
or SMT findings, but it cannot silently change an already approved intent.
The run log at `runs/<timestamp>.jsonl` records requirement history, stage
executions, artifacts and sanitized model-call metadata, not API keys or raw
chain-of-thought. `--run-log-dir` and `--no-run-log` control that output.

An independent behavior scenario can be supplied with `--expectation PATH`.
The CLI asks for separate confirmation before using it for reference
comparison and bounded exploration. The pinned SMT and reference drivers are
required for their respective gates; an unavailable driver does not become a
business clarification or a pass.

The optional ledger adapter needs all `MARLOWE_LEDGER_*` configuration values,
a synchronized node and pinned binaries. It checks transaction size; it does
not sign or submit. No testnet wallet or signing route is configured, so
testnet/deployment cannot currently produce a real pass. The CLI reports the
first blocking stage and never labels a candidate as deployed.

## Tests and History

From the repository root:

```powershell
python -m pytest -q
python -m compileall -q research marlowe_ai_agent tools
uvx ruff check --select F401,F841
```

`research/marlowe_core/` owns the shared AST validator, graph lint and SMT
finding mapper. Historical Node 1/2/3 code lives in `research/legacy/` for
benchmark reproducibility; the supported CLI does not import or invoke it.
The old README is preserved at `docs/research/legacy-pipeline-readme.md`.
