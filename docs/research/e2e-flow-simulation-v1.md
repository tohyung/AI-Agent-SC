# Offline end-to-end flow simulation v1

This is a concrete interface integration simulation. It establishes that typed
artifacts can traverse the research DAG with explicitly injected deterministic
dependencies. It does not establish semantic accuracy, compiler correctness,
reference semantics correctness, property safety, ledger validity, or production
readiness. No LLM, pinned Marlowe executable, wallet, network, testnet, or real
deployment was used.

## Architectural bottlenecks

| ID | Symptom and cause | Patch and regression | Remaining limit |
| --- | --- | --- | --- |
| B1 | Compiler mapping gate required participants, parameters, states, transitions, and outcomes absent from `CompilationIR`. | Typed IR now carries every required object and mapping expectations derive from IR. The clean-flow plugin inspects all sections and returns full structural mapping evidence. | An AST path in mapping evidence does not prove semantic faithfulness. |
| B2 | Reviewed `behavior-expectation` could not enter `ResearchOrchestrator.run()` or a resume. | Explicit `external_artifacts` injection persists IDs in the run, uses `ArtifactStore` collision checks, and creates no requirement-to-external edge. Tests cover resume, duplicate injection, and collision. | Payload restoration across processes is not implemented; resume requires the same store. |
| B3 | Composition root exposed only model wiring. | `ResearchPipelineWiring` injects stage policies, profile/compiler, reference, exploration, oracle, checker/registry, and final ports. Clean/finding flows use `build_research_pipeline()`. | Default composition deliberately remains offline and fail-closed. |
| B4 | Stage 5 ignored its checker and rejected status events at the same candidate version. | Typed `PropertyCheckResult`; checker executes per candidate; registry stores immutable chronological events. Tests cover candidate-to-`REFUTED`, duplicate events, candidate-content collision, and older-version rejection. | Synthetic checker evidence is not a formal proof. Stage success reports completed evaluation, not property satisfaction. |
| B5 | Authority and property ports read additional artifacts without declaring them as inputs. | Authority now declares comparison and contract; property stage declares adversarial candidates and contract. Clean-flow provenance assertions cover these plus every other executed internal stage. | Provenance records declared input consumption, not authenticity of external evidence. |

## Observed simulation paths

**Clean flow:** requirement history enters the real Stage 2B port. Stage 2C
returns `WAITING_USER`; the same orchestrator/store resumes with a synthetic
review decision. The real compiler port uses a synthetic profile/plugin and a
structurally valid `close` contract. A synthetic reviewed expectation is injected
on a further resume. Real comparison, authority, exploration, oracle, coverage,
adversarial, and property ports execute. Oracle findings are `SATISFIED` only
for the observed synthetic trace; Stage 5 returns `NO_CANDIDATES`. Three
simulation-only final ports then execute and emit `NO_AUTHORITY` artifacts.
All 13 stage names have an executed `SUCCEEDED` result; Stage 2C executes
twice, for 14 stage executions. Coverage remains `BOUNDED`.

**Finding flow:** the same real internal ports run with a synthetic warning.
`NoWarningsOracle` returns `VIOLATED`; adversarial candidate selection emits a
candidate; the real property port calls a synthetic checker. Registry history
records `CANDIDATE` then `REFUTED` on the same candidate version. Stage 5
reports completed evaluation with semantic status `REFUTED`. This path stops
before ledger, testnet, and deployment interfaces. No adversarial search is
claimed: the current adversarial port selects candidates only.

The default research composition cannot traverse this path without injections;
that is intentional. No production authority or default CLI route changed.
