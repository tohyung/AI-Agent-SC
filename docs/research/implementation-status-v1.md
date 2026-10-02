# Architecture v1: implementation and evidence status

Baseline: `3294c703f0636614c12daaaae8bb9d63ca4f886f`. The official
architecture status is `ARCHITECTURE_SPECIFIED_AND_SCAFFOLDED` in
[`manifest.json`](../../research/architecture/manifest.json). This document is
an evidence inventory for a research report, not a promotion decision. The
default production route remains legacy Node 1/2/3.

## Evidence labels used here

These E0-E6 labels are **project-specific reporting labels**, not universal
standards or a linear certification ladder. A test at one level supports only
its stated scope.

| Label | Meaning in this report |
| --- | --- |
| E0 | Interface, model, policy or algorithm is present in source. |
| E1 | Deterministic offline contract/smoke test exercises a stated invariant or boundary. |
| E2 | Real component behavior evaluated on representative, human-reviewed cases. |
| E3 | Profile/behavior compared against pinned reference semantics with recorded scope. |
| E4 | Independent reviewed/hidden evaluation under a frozen protocol. |
| E5 | Actual ledger or testnet transaction evidence. |
| E6 | Observation of an authorized deployed system. |

The new architecture has primarily E0/E1 evidence. No E2-E6 result is claimed
for its new Stage 2C-5 path. Prior Stage 2A reference work is scoped to its
own explicit traces; it does not transfer E3 to the new Stage 3/4 adapters.
The frozen 32-case Stage 2A corpus has **32 draft candidate annotations**, not
human-reviewed ground truth; its public validation split is not blind
([protocol](../../research/stage2a/protocol.md),
[freeze manifest](../../research/stage2a/freeze/stage2a-v1.manifest.json)).
Stage 2B comparisons with those annotations remain exploratory
([Stage 2B README](../../research/stage2b/README.md)).

## Component evidence matrix

States below describe the current prototype, not a claim about the intended
future system. `IMPLEMENTED_UNVALIDATED` means code exists but representative
behavior/correctness has not been established. `SCAFFOLDED` means a boundary or
limited candidate-selection mechanism exists without the full stage behavior.

| Component | Implementation state | Observed evidence | What it establishes | What remains unverified |
| --- | --- | --- | --- | --- |
| Shared artifact identity | IMPLEMENTED_UNVALIDATED | E0 [artifacts](../../research/architecture/artifacts.py); E1 metadata/hash smoke | Canonical payload hash is separate from type/schema prefix and envelope metadata; nested payload mutation is blocked. | Cross-runtime migration, durable storage, arbitrary external payload compatibility. |
| Provenance model | IMPLEMENTED_UNVALIDATED | E0 [edge model](../../research/architecture/provenance.py); E1 synthetic DAG/run-ID smoke | Run identity and edge records are separate from content identity. | Durable cross-process lineage, independent audit of real-stage evidence. |
| Assurance model | IMPLEMENTED_UNVALIDATED | E0 [assurance](../../research/architecture/assurance.py); E1 evidence/hash and missing-evidence smoke | Conclusive claim objects require evidence; artifact hash can be checked against the in-memory store. | Soundness of any domain claim, external evidence resolution, independent review. |
| Research orchestrator | IMPLEMENTED_UNVALIDATED | E0 [DAG](../../research/architecture/orchestrator.py); E1 synthetic ports, resume, budget/blocker smoke | Stage ordering, artifact propagation, in-memory resume, typed downstream blocking and execution-count budget. | Concrete full-path run, durable checkpoints, external side-effect replay. |
| Stage 2A candidate/reference foundation | EXISTING; candidate annotations | E0 [protocol](../../research/stage2a/protocol.md) and [freeze](../../research/stage2a/freeze/stage2a-v1.manifest.json); read-only [adapter](../../research/integrations/stage2a.py) | Versioned candidate corpus and separate pinned-reference trace methodology exist. | Human-reviewed ground truth, blind evaluation, transfer of reference evidence to new stages. |
| Stage 2B shadow semantic extraction | IMPLEMENTED; UNDER EVALUATION | E0 [extractor](../../research/stage2b/shadow_extractor.py), [adapter](../../research/integrations/stage2b.py); E1 default-offline smoke | Core-v1 model interface, prompt contract and model-candidate boundary exist; no live model is instantiated by default. | Accurate intent extraction, reliable live output, reviewed-case behavioral quality. |
| Stage 2B deterministic projection | IMPLEMENTED; UNDER EVALUATION | E0 [projector](../../research/stage2b/projector.py), [validator](../../research/stage2b/intent_spec.py) and [README](../../research/stage2b/README.md) | Core-to-rich projection and structural diagnostics exist; no direct production authority. | Semantic correctness of the source core or projected interpretation against reviewed intent. |
| Stage 2C review | IMPLEMENTED_UNVALIDATED | E0 [review](../../research/stage2c/review.py); E1 invalid-candidate/wait smoke | Issues are surfaced deterministically; invalid Stage 2B candidates block acceptance. | Usability and completeness of real human review. |
| Stage 2C acceptance gate | IMPLEMENTED_UNVALIDATED | E0 [ReviewerPolicy seam](../../research/stage2c/acceptance.py); E1 pause/resume and self-reported-ID rejection smoke | Acceptance requires explicit decision and injected reviewer-authorization policy; default fails closed. | Reviewer identity verification, deployed authorization provider, actual consent provenance. |
| Stage 2C intent freeze | IMPLEMENTED_UNVALIDATED | E0 [freeze](../../research/stage2c/freeze.py); E1 synthetic accepted-answer/resume smoke | Content-addressed accepted snapshot, answer artifacts and manifest can be created after an injected test policy approves. | Real-user acceptance and semantic correctness of approved intent. |
| Stage 3 profile registry | IMPLEMENTED_UNVALIDATED | E0 [profiles](../../research/stage3/profiles.py); E1 unsupported-profile smoke | Exact/ambiguous/unsupported result vocabulary and fail-closed empty registry exist. | Real profile completeness or adequacy for Marlowe constructs. |
| Stage 3 deterministic compiler interface | IMPLEMENTED_UNVALIDATED | E0 [typed IR/compiler port](../../research/stage3/compiler.py); E1 fake-plugin interface smoke | An injected deterministic plugin, not an LLM AST fallback, is required; structural Core V1 gate is present. | Any real compiler plugin, profile behavior, semantic faithfulness. |
| Stage 3 mapping-evidence gate | IMPLEMENTED_UNVALIDATED | E0 [coverage check](../../research/stage3/compiler.py); E1 missing-mapping smoke | Nonempty `ast_path` plus `source_kind/source_id` must structurally cover expected claims, scopes and rich objects. | Whether paths exist in the AST or represent the intended semantics. |
| Stage 3 reference semantics adapter | IMPLEMENTED_UNVALIDATED | E0 lazy [adapter](../../research/stage3/reference.py) to pinned [driver](../../tools/marlowe_smt/run_reference.py); E1 unavailable-response smoke uses a fake executor | Request/response boundary and unavailable taxonomy are wired without import-time driver execution. | New-path execution against the real pinned binary and representative traces. |
| Stage 3 semantic comparison | IMPLEMENTED_UNVALIDATED | E0 [comparison](../../research/stage3/comparison.py); E1 unavailable/identity smoke | Separate reviewed expectation artifact and policy are required; missing reference data is inconclusive. | Correctness and independence of reviewed expectations; real differential coverage. |
| Stage 3 compiler authority gate | IMPLEMENTED_UNVALIDATED | E0 [authority](../../research/stage3/authority.py); E1 candidate-only and other-contract rejection smoke | Profile/compiler/schema/reference/policy scope is checked; default is `CANDIDATE_ONLY`. | Promotion policy, evidence sufficiency, any authorized profile. |
| Stage 4 transaction domain | IMPLEMENTED_UNVALIDATED | E0 [explicit templates](../../research/stage4/domains.py); E1 interval/shape smoke | Deposit/Choice/Notify/Timeout templates and before/after/straddle categories exist. | Soundness or completeness of a real domain generator. |
| Stage 4 reference explorer | IMPLEMENTED_UNVALIDATED | E0 [bounded explorer](../../research/stage4/explorer.py); E1 default-not-configured/interface DAG smoke only | Source defines bounded successors from reference `Success`; failed transactions are not advanced. | Concrete exploration against pinned reference, state/trace coverage and path-sensitive correctness. |
| Stage 4 runtime oracle layer | IMPLEMENTED_UNVALIDATED | E0 [trace oracle](../../research/stage4/oracles.py); E1 missing-warning-schema smoke | Observed-trace warning check returns `INCONCLUSIVE` on malformed warning data. | Real trace behavior, other oracle families, universal safety. |
| Stage 4 coverage accounting | IMPLEMENTED_UNVALIDATED | E0 [coverage port](../../research/stage4/coverage.py), [explorer](../../research/stage4/explorer.py); E1 interface DAG only | The source records declared domain, trace counts and `BOUNDED` label. | Exhaustiveness, domain adequacy, meaningful behavioral coverage. |
| Stage 4 adversarial stage | SCAFFOLDED | E0 [candidate selector](../../research/stage4/adversarial.py) | `VIOLATED` findings can be forwarded as candidates; `search_performed=False`, no auto-repair. | Search strategies, mutations, independent counterexample discovery. |
| Stage 5 property candidate/registry | SCAFFOLDED | E0 [registry/port](../../research/stage5/registry.py); E1 idempotency/evidence requirement smoke | Candidate history exists; scoped validation status requires evidence IDs and reviewer ID. | Property formalization, checker invocation, proof artifact validation, promotion. |
| Node 3/SMT integration seam | IMPLEMENTED_UNVALIDATED | E0 lazy [SMT adapter](../../research/integrations/smt.py) and existing production backend | Research adapter can map existing backend's status and findings if invoked. | New research-path solver execution and assurance significance of SMT outcomes. |
| Ledger validation | SCAFFOLDED / DISABLED | E0 [disabled port](../../research/final_validation/adapters.py) | Returns `NOT_EVALUATED` by design when reached. | Ledger transaction validity, role tokens, signer/UTxO/budget conditions. |
| Testnet | SCAFFOLDED / DISABLED | E0 [disabled port](../../research/final_validation/adapters.py) | No wallet, signing or network action is implemented. | Any testnet observation. |
| Deployment | SCAFFOLDED / DISABLED | E0 [disabled port](../../research/final_validation/adapters.py) | No deployment action is implemented. | Deployed behavior or operational readiness. |
| Research CLI / opt-in route | IMPLEMENTED_UNVALIDATED | E0 [CLI](../../marlowe_ai_agent/marlowe_agent/cli.py), [bootstrap](../../research/architecture/bootstrap.py); E1 offline-candidate smoke | Legacy remains default; candidate route can return typed offline `NOT_EVALUATED` without constructing the model. | Real accepted-intent/compiled-contract CLI workflow; `authorized` mode is blocked. |

## What the offline smoke file actually exercises

The 17 source-present tests in
[`test_contract_smoke.py`](../../research/architecture/test_contract_smoke.py)
are offline interface tests, not accuracy or deployment tests:

- Import of the new packages/composition root is exercised without a live transport call.
- Same semantic payload under different envelope metadata has the same content
  identity; type/schema changes alter artifact ID; evidence hash and nested
  immutability checks are exercised.
- Invalid Stage 2B candidate blocks Stage 2C; compiler is not evaluated.
- A synthetic review pauses, resumes with an answer artifact under an injected
  **test-only** reviewer policy, then reaches unsupported profile (no AST).
- A self-reported reviewer ID cannot grant acceptance without a policy.
- Missing expectation/reference evidence leaves comparison inconclusive and
  authority candidate-only; a fake unavailable executor remains inconclusive.
- Even an injected permissive promotion policy cannot use a comparison tagged
  to another contract.
- Missing warning schema cannot become a `SATISFIED` trace oracle verdict.
- Registry candidate insertion is idempotent; scoped property validation status
  rejects missing evidence/reviewer inputs.
- The same requirement content yields the same source artifact ID but a
  different run ID.
- Explicit timeout intervals distinguish before, after and straddling.
- A fake compiler plugin lacking typed mapping coverage produces no contract.
- Synthetic ports exercise all DAG interfaces, stage order, artifact propagation,
  provenance, serialization and resume **without assurance claims**.
- An execution-count budget blocks subsequent stage invocation.
- Offline candidate CLI routing does not construct the legacy LLM reasoner.
- Default bootstrap does not configure a live model or grant authority.

These tests do **not** execute the concrete research pipeline from natural
language through deployment. For this documentation task, the local offline
command `python -m pytest research/architecture/test_contract_smoke.py -q`
returned `17 passed in 0.09s`. No LLM/API, reference binary, SMT, testnet or
deployment operation was invoked by that command. This is local test execution,
not independent CI/workflow evidence; none is used in this document.

## Authority matrix

The second column is an intended upper boundary, not a status already earned.
Enum names come from [status.py](../../research/architecture/status.py).

| Artifact / result | Maximum intended authority | Current default authority | Evidence needed before promotion |
| --- | --- | --- | --- |
| Shadow Semantic Core | `MODEL_CANDIDATE` | Model candidate if emitted; none without model | Human review before intent acceptance; structural validity alone is insufficient. |
| IntentSpec Candidate | `MODEL_CANDIDATE` | `MODEL_CANDIDATE` if emitted | Explicit authorized human decision on a validated, reviewed spec. |
| AcceptedIntentSpec | `USER_ACCEPTED_INTENT` | Not emitted without injected reviewer policy and explicit consent | Authorized reviewer decision; reviewer identity verification is outside this prototype. |
| CompileResult | Structured compiler outcome, not an authority level | `NO_AUTHORITY` | Exact profile/plugin, structural gate and mapping evidence before any contract candidate. |
| Contract Candidate | `DETERMINISTIC_COMPILER_CANDIDATE` | Not emitted without profile/plugin; candidate only if emitted | Profile-specific independent comparison and explicit promotion policy for mapping authority. |
| Reference Comparison | Scoped `REFERENCE_SEMANTICS_AUTHORITY` for an actual pinned trace, not intent/ledger authority | Artifact `NO_AUTHORITY`; no executor/expectation by default | Reviewed independent expectation and real pinned execution with recorded identity/scope. |
| Compiler Authority Decision | `PROFILE_COMPILER_AUTHORITY` for exact profile/version/evidence-policy scope | Status `CANDIDATE_ONLY`, artifact `NO_AUTHORITY` | Explicit reviewed promotion decision and policy with adequate verifiable evidence; policy not configured. |
| Exploration Result | Bounded behavioral observation, not global authority | `NO_AUTHORITY`; not evaluated without domain/reference | Explicit domain/state/reference traces and coverage accounting; no automatic global promotion. |
| Oracle Finding | Verdict for an observed trace only | `NO_AUTHORITY`; oracle list empty by default | Applicable, checked trace evidence within the stated scope; not a theorem. |
| Property Candidate | Candidate for later formalization | `NO_AUTHORITY` | Separate checker/review integration; currently absent. |
| Validated Property | Scoped property-checking result, never blanket production authority | Not produced by current port | Checker evidence and explicit review are required by registry seam; proof format/policy remain unspecified. |
| Ledger Result | `LEDGER_AUTHORITY` only for the exact validated transaction/context | Not produced; port disabled | Real ledger validation integration and scoped evidence; not designed in this prototype. |
| Testnet Observation | Scoped network observation, not general correctness | Not produced; port disabled | Actual testnet execution/evidence and operator controls; adapter absent. |
| Deployment Observation | Scoped operational observation, not an authority shortcut | Not produced; port disabled | Authorized deployment and monitoring evidence; adapter absent. |

`PROFILE_COMPILER_AUTHORITY` authorizes only deterministic mapping for the
stated profile/version/compiler/intent schema/Core V1/reference/evidence-policy
scope. It does not authorize Stage 4/5 claims or imply `LEDGER_AUTHORITY`.
`REFERENCE_SEMANTICS_AUTHORITY` is limited to the pinned executable semantics
and explicit trace/model; the current comparison artifact itself is stored
with `NO_AUTHORITY`.

## Failure and uncertainty propagation

| Condition | Current stage outcome | Downstream limit |
| --- | --- | --- |
| Stage 2B emits invalid core/full candidate | Stage 2C `BLOCKED` | Compiler `NOT_EVALUATED`; no accepted intent. |
| Human has not accepted, or reviewer policy is absent/denies | `WAITING_USER` or `BLOCKED` | No `AcceptedIntentSpec`; compiler `NOT_EVALUATED`. |
| No exact supported profile or plugin | Compile `UNSUPPORTED_FEATURE`/`UNSUPPORTED` | No contract candidate or reference comparison. |
| Structural AST or mapping-evidence gate fails | Compile `FAILED` or `UNSUPPORTED` | No contract candidate; no semantic/ledger inference. |
| No reviewed independent expectation or reference executor | Comparison `INCONCLUSIVE` | Authority stage may record `CANDIDATE_ONLY`; no profile authority. |
| Reference `Unavailable`, `Timeout` or invalid result | Comparison `UNAVAILABLE`/`INCONCLUSIVE` | No reference pass; compiler authority remains `CANDIDATE_ONLY`. |
| No exploration domain/state/reference executor | Exploration `NOT_EVALUATED` | No concrete oracle/coverage result. |
| Oracle returns `SATISFIED` for an observed trace | Trace-local result only | Does not establish universal property or exhaustiveness. |
| No checker/formalization/review | Property stage `INCONCLUSIVE`, candidate only | No validated property or proof claim. |
| External ports disabled | `NOT_EVALUATED` when reached | No ledger, testnet or deployment claim. |

## Current report-safe status

```text
Architecture specification:              PRESENT
Architecture interface DAG:              IMPLEMENTED
Offline interface/contract smoke evidence: SOURCE-PRESENT; 17/17 passed locally
Concrete end-to-end execution:           NOT DEMONSTRATED
Stage 2B semantic quality:               UNDER EVALUATION
Stage 2C:                                IMPLEMENTED_UNVALIDATED
Stage 3:                                 IMPLEMENTED_UNVALIDATED
Stage 4A/4B:                             IMPLEMENTED_UNVALIDATED
Stage 4C:                                SCAFFOLDED
Stage 5:                                 SCAFFOLDED
Ledger/Testnet/Deployment:               SCAFFOLDED / DISABLED
Reviewer identity verification:          NOT IMPLEMENTED
Mapping semantic correctness:            NOT ESTABLISHED
Production authority:                    NOT GRANTED
```

The architecture can be described in a system-design chapter. The current
prototype cannot be described as semantically accurate, formally proven,
ledger-valid, end-to-end validated or production-ready on this evidence.
