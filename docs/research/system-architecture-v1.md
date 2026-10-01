# Research assurance architecture v1

Status: `ARCHITECTURE_SPECIFIED_AND_SCAFFOLDED`. This is not model, compiler,
reference, oracle, ledger, or production validation. Legacy Node 1/2/3 remains
the default production route.

## Dataflow and trust boundaries

```text
requirement-history
  -> Stage 2B ShadowSemanticCore + deterministic IntentSpec projection
     [MODEL_CANDIDATE]
  -> Stage 2C review, clarification, explicit human decision
     [USER_ACCEPTED_INTENT; immutable snapshot, not correctness proof]
  -> Stage 3 exact profile -> typed CompilationIR -> deterministic plugin
     -> structural Core V1 AST gate [COMPILER_CANDIDATE]
  -> independent BehaviorExpectation + pinned reference execution
  -> profile/version/evidence-scoped promotion policy [default CANDIDATE_ONLY]
  -> Stage 4 bounded reference exploration -> trace oracles -> coverage
     -> adversarial finding candidates
  -> Stage 5 property candidates -> external checker/review -> registry
  -> ledger -> testnet -> deployment [all disabled]
```

`research.architecture` contains only shared models, ports, artifact identity,
provenance, status and orchestration. It never imports concrete stages at module
import time. `research.architecture.bootstrap` is the composition root; stage
imports and the live model transport are lazy. Stage modules depend on shared
primitives, not on the concrete orchestrator. The production CLI is the opt-in
route: `--research-mode legacy|shadow|candidate|authorized`. `legacy` remains
the default and retains its output. `--research-live` is required before the
sidecar/candidate route may call the model. `authorized` fails closed until a
profile-scoped promotion policy and evidence are reviewed and configured.
The CLI research snapshot includes readable candidate/review/contract artifacts,
but no CLI reviewer-policy provider or profile compiler is configured in v1;
it cannot issue a production-authorized contract.

## Artifact and status ADRs

- `canonical_json_v1` is UTF-8 JSON with sorted keys and compact separators.
  Payloads allow string keys, arrays, strings, integers, booleans and null; no
  float, NaN, implicit Unicode normalization or newline conversion.
- `content_hash = SHA256(canonical_json_v1(payload))`.
  `artifact_id = artifact_type:schema_version:cj1:content_hash`. Type and schema
  separate domains. Envelope, timestamps, producer, run metadata and lineage
  are not hashed. Semantic source/version facts belong inside payload.
- Provenance edges are independent records, so identical content can occur in
  separate runs without losing lineage. Corrections create new artifacts; no
  in-place mutation or self-referential envelope hash.
- All stages use `ImplementationStatus` for lifecycle and `StageRunStatus` for
  execution. Domain statuses such as `CompileStatus` and `PropertyStatus` do
  not substitute for either. Assurance verdict, method, coverage, authority,
  limitations and evidence are separate axes. A `SUCCEEDED` stage means only
  that its port returned a structured result.
- Expected provider/model/parser failures are infrastructure errors; unresolved
  business intent is a review issue. Unsupported profile, unavailable reference,
  timeout and inconclusive comparison never become user business questions.
- `AUTHORIZED_FOR_PROFILE` is valid only for its profile/version, compiler,
  intent schema, Core V1 format, pinned reference and evidence-policy scope.
  It authorizes deterministic mapping only, not Stage 4/5 behavior or ledger
  validity. No promotion policy is registered by default. A finite differential
  trace alone is insufficient for promotion.
- Stage 2C also needs an injected reviewer-authorization policy. A self-reported
  reviewer ID and consent flag alone cannot grant `USER_ACCEPTED_INTENT`.

## Interfaces and current implementation

| Component | Boundary | Lifecycle | Default outcome |
| --- | --- | --- | --- |
| Shared artifacts, status, provenance, orchestrator | Pure Python, injected `StagePort` | IMPLEMENTED_UNVALIDATED | Typed run/checkpoint |
| Stage 2A frozen corpus adapter | Read-only, verify frozen candidate corpus | IMPLEMENTED_UNVALIDATED | No user authority |
| Stage 2B adapter | Existing shadow extractor/projector/validators | IMPLEMENTED_UNVALIDATED | NOT_EVALUATED without model |
| Stage 2C | Deterministic review and explicit consent | IMPLEMENTED_UNVALIDATED | WAITING_USER |
| Stage 3 profile/IR/compiler | Exact profile and injected deterministic plugin | IMPLEMENTED_UNVALIDATED | UNSUPPORTED without profile |
| Stage 3 reference comparison | Independent reviewed expectation and pinned driver | IMPLEMENTED_UNVALIDATED | INCONCLUSIVE without executor/expectation |
| Stage 3 authority | Explicit policy + decision + evidence | IMPLEMENTED_UNVALIDATED | CANDIDATE_ONLY |
| Stage 4 explorer/oracles/coverage | Explicit transaction domain and reference executor | IMPLEMENTED_UNVALIDATED | NOT_EVALUATED without domain |
| Stage 4 adversarial search | Finding selection only; search strategy unimplemented | SCAFFOLDED | No automatic repair |
| Stage 5 property checker | Candidate registry; no checker integration | SCAFFOLDED | INCONCLUSIVE |
| Node 3 SMT adapter | Existing SMT statuses; opt-in | IMPLEMENTED_UNVALIDATED | Not run by default |
| Ledger/testnet/deployment | Disabled ports, no network/signing | SCAFFOLDED | NOT_EVALUATED |

The reference adapter uses the pinned `tools/marlowe_smt/run_reference.py`
wrapper. Its `Success`/`TransactionError` are trace results, while
`Unavailable`/`Timeout`/`InvalidInput`/`Unsupported` cannot establish a pass.
The expectation source must be an accepted intent or independently reviewed
profile/scenario; it is never derived from the compiled AST. Comparison also
requires a separate content-addressed `behavior-expectation` artifact and an
injected reviewer policy. The expectation cannot carry an AST; an option string
naming a source is not enough. Explorer successors use `final_state` and
`final_contract` only on `Success`; failed
transactions do not commit state. It does not deduplicate path-sensitive
histories. Coverage remains `BOUNDED` even if the supplied domain enumeration
ends; completeness requires a separately checked finite-domain argument.
The explicit domain template supports Deposit, Choice, Notify and timeout
transactions with POSIX-millisecond intervals. Before `T` means `to < T`,
after `T` means `from >= T`, and `from < T <= to` is straddling, not before or
after. The template never infers missing actors, values or deadlines.

## Checkpoint and side-effect policy

`ResearchOrchestrator` persists stage results, artifact IDs and provenance in
memory. `stop_after` and `resume` support a human wait without a busy process;
resuming requires the same source artifact and store. This is not yet a durable
cross-process event store. Missing ports and upstream blockers produce typed
`NOT_EVALUATED`, not synthetic success. The authority stage can still emit
`CANDIDATE_ONLY` after an inconclusive/unavailable reference comparison.
The CLI candidate route does not silently fall back to LLM-generated AST.
No profile plugin, live model, SMT, reference executor, domain, ledger adapter,
wallet, testnet connection or deployment credentials are configured by default.

## Validation backlog

1. Durable checkpoint store, replay/idempotency and side-effect budget policy.
2. Stage 2C human UX, corrected history provenance and acceptance tests.
3. Golden compiler profiles with complete mapping and differential evidence.
4. Independent trace expectations, pinned reference and SMT campaigns.
5. Explorer domain soundness, oracle applicability, path coverage and interval cases.
6. Adversarial search, formal property checker and versioned proof evidence.
7. Stage 2B semantic evaluation on reviewed data, not draft candidate labels.
8. Ledger/testnet integration and operator-reviewed deployment gates.

Do not describe this architecture as verified, proven or production-ready.
