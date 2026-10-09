# Production Route Transition (Work In Progress)

The default CLI now uses Stage 2B intent extraction, explicit Stage 2C user review,
LLM generation of a Marlowe Core V1 candidate, structural validation, the pinned
SMT driver, and reference comparison. The old Node 1/2/3 route is no longer
exposed by the supported CLI. This is **not** a production authorization.

## Current Gate Semantics

- A model-generated AST has `MODEL_CANDIDATE` authority only. SMT `Valid` means
  no modeled Marlowe transaction warnings, not business-intent equivalence.
- SMT counterexamples are replay-mapped to an AST path when possible and rendered
  in Vietnamese. Unmapped findings retain an explicit unmapped status.
- Claim/AST alignment compares exact supported fields. Scope path existence is
  `INCONCLUSIVE`; it never proves behavioral equivalence. A separately reviewed
  reference scenario can establish only its observed trace.
- Stage 4 explores bounded, declared transactions through the pinned reference;
  no payment transaction is invented when none was declared. Empty or wholly
  unevaluated exploration/oracle evidence is `INCONCLUSIVE`. Stage 5 keeps
  candidate property records and a local, unadjudicated observation dataset,
  but has no general independent property checker. Dataset export requires
  pinned replay, two concordant reviews and asserted data-use rights; see
  [Stage 5 dataset](../../research/stage5/README.md).
- The ledger port currently checks transaction size against a pinned CLI and a
  synchronized local node when explicitly configured. It does not sign or submit.

## External Readiness

- SMT/reference Haskell binaries and Z3 were exercised through the Windows-to-WSL
  bridge. Linux/WSL execution does not invoke `wsl.exe`.
- A local private Cardano node exists outside this repo, but its observed
  `syncProgress` was below the ledger adapter's 99% threshold at this update.
  It is not public preprod evidence.
- No testnet wallet, signing route, or funded address has been configured. The
  testnet and deployment ports remain disabled. No transaction was signed,
  submitted, or observed on a public testnet.
- The canonical AST validator, graph lint, warning renderer and SMT finding
  mapper now live in `research/marlowe_core/`. Legacy import paths remain as
  compatibility aliases for historical tests and benchmarks. The old Node
  1/2/3 implementation now lives in `research/legacy/`; the supported CLI
  and assurance stages no longer depend on it.

## Reproducibility

Run from the repository root:

```powershell
python -m pytest -q
python -m compileall -q research marlowe_ai_agent tools
uvx ruff check --select F401,F841
```

The CLI's `runs/<timestamp>.jsonl` record contains requirement history,
stage execution history, immutable artifact snapshots, sanitized model-call
metadata, and the first blocking stage. It does not contain API keys or raw
model chain-of-thought. Real LLM calls and testnet submission are not part of
the default test suite.
