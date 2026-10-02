# Offline end-to-end flow simulation v1

This is a concrete interface integration simulation. It establishes that typed
artifacts can traverse the research DAG with explicitly injected deterministic
dependencies. It does not establish semantic accuracy, compiler correctness,
reference semantics correctness, property safety, ledger validity, or production
readiness. The deterministic 13-stage simulation used no LLM, pinned Marlowe
executable, wallet, network, testnet, or real deployment. Separate real
pinned-reference integration tests below did execute the Haskell binary.

## Architectural bottlenecks

| ID | Symptom and cause | Patch and regression | Remaining limit |
| --- | --- | --- | --- |
| B1 | Compiler mapping gate required participants, parameters, states, transitions, and outcomes absent from `CompilationIR`. | Typed IR now carries every required object and mapping expectations derive from IR. The clean-flow plugin inspects all sections and returns full structural mapping evidence. | An AST path in mapping evidence does not prove semantic faithfulness. |
| B2 | Reviewed `behavior-expectation` could not enter `ResearchOrchestrator.run()` or a resume. | Explicit `external_artifacts` injection persists IDs in the run, uses `ArtifactStore` collision checks, and creates no requirement-to-external edge. Tests cover resume, duplicate injection, and collision. | Payload restoration across processes is not implemented; resume requires the same store. |
| B3 | Composition root exposed only model wiring. | `ResearchPipelineWiring` injects stage policies, profile/compiler, reference, exploration, oracle, checker/registry, and final ports. Clean/finding flows use `build_research_pipeline()`. | Default composition deliberately remains offline and fail-closed. |
| B4 | Stage 5 ignored its checker and rejected status events at the same candidate version. | Typed `PropertyCheckResult`; checker executes per candidate; registry stores immutable chronological events. Tests cover candidate-to-`REFUTED`, duplicate events, candidate-content collision, and older-version rejection. | Synthetic checker evidence is not a formal proof. Stage success reports completed evaluation, not property satisfaction. |
| B5 | Authority and property ports read additional artifacts without declaring them as inputs. | Authority now declares comparison and contract; property stage declares adversarial candidates and contract. Clean-flow provenance assertions cover these plus every other executed internal stage. | Provenance records declared input consumption, not authenticity of external evidence. |
| B7 | The synthetic reference accepted `state={}`, which the Haskell bridge rejects. This was an integration-fixture/reference-seam mismatch, not an established production bug. | The separate real-reference seam uses exact `accounts`, `choices`, `boundValues`, and `minTime` fields. The real driver accepts that state and returns `InvalidInput` for `{}`. | Request compatibility is observed only for the tested Notify trace. |
| B8 | Comparison of only status and final contract could accept a wrong `Close` refund in place of a Pay to Bob. | Optional final-state, warning, and payment observables now preserve legacy expectation identity; the real-reference wrong-compiler regression reports `VIOLATED` with `payments` mismatched. | One reviewed scenario does not establish general semantic equivalence. |
| B9 | A Pay reduction needs an empty-input transaction, but `Timeout` was the only empty-input domain label. | `NoInput` now represents an empty-input transaction without changing `Timeout`; unit and real-reference tests exercise it. | Transaction-domain coverage remains explicit and bounded. |

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

## Real pinned-reference seam

This is a separate evidence layer from the deterministic 13-stage simulation
above. That full-flow test still uses `FakeReferenceExecutor`; it has not been
replaced with the Haskell driver. The real seam test uses the exact Core V1
`When` / `Notify(True)` / `Close` JSON contract, a Notify input at interval
`[0, 0]`, and the bridge's exact empty state:

```json
{"accounts": [], "choices": [], "boundValues": [], "minTime": 0}
```

The pinned identity observed from the real executable was
`7b5b1e900ec53a8eb18747992bec73470704dfcb:0.1.0`. A direct request
returned `Success`, `final_contract="close"`, and no warnings. The same request
with `state={}` returned `InvalidInput`. `PinnedMarloweReference`, the real
`SemanticComparisonPort`, `ExplorationPort`, and `NoWarningsOracle` were then
exercised in the WSL Python/Linux-binary environment: comparison was
`SATISFIED`, exploration coverage remained `BOUNDED`, and the oracle was
`SATISFIED` for its single observed reference trace. The integration file had
6 passing tests (one adapter-plumbing unit test and five real-seam checks);
the Haskell reference driver unittest file had 20 passing tests (17 real
semantics tests and three mocked wrapper checks).

The binary was built with Cabal 3.10.3.0 and GHC 9.6.7 under WSL Ubuntu;
`cabal build exe:marlowe-reference --offline` reported `Up to date`. The WSL
Python 3.14.4 process loaded an already-installed pytest package from a
mounted local path because pytest was not installed in the WSL interpreter.
No Python process tried to execute a binary across an OS boundary. This seam
result does not establish compiler semantic faithfulness, general Marlowe
correctness, ledger validation, or production readiness.

## Direct payment compiler to pinned reference

The explicitly wired research profile `direct-payment`/`v1` uses compiler
`deterministic-direct-payment`/`0.1.0`. It supports exactly one payment from an
existing account, with the claim kinds `payment_source_account_owner`,
`payment_recipient`, `amount_lovelace`, and `asset`. Only ADA is supported. The
profile represents a participant/account name as a Marlowe Role with that text;
this is a representation rule, not a wallet address, token-ownership proof, or
ledger authorization rule. No default profile registration or compiler authority
promotion occurred.

A synthetic, validated accepted-intent fixture specifies a payment of 10 ADA
from Alice's funded account to Bob. It is an integration input, not evidence of
reviewer authentication. `CompilerPort` generated a Pay-to-Bob Core V1 AST with
structural mapping evidence. With Alice's account initially funded with exactly
10 ADA, the real pinned reference
`7b5b1e900ec53a8eb18747992bec73470704dfcb:0.1.0` returned `Success`, a
payment to Bob, no warnings, empty final accounts, and `close`. The independent
behavior expectation compared status, final contract, final state, warnings,
and payments and returned `SATISFIED`.

A deliberately wrong, test-only compiler instead produced structurally valid
`close` with complete structural mapping evidence. The same real reference
returned `Success` and `close`, but refunded Alice. Behavioral comparison
returned `VIOLATED` with `payments` in its mismatch diagnostics. Thus mapping
evidence completeness is not mapping semantic correctness, and status plus
final contract alone would have missed this error.

Bounded exploration used the compiler-produced contract, a `NoInput` transaction,
depth one, and one trace. The real reference trace succeeded with the Bob payment
and no warning; `NoWarningsOracle` returned `SATISFIED` for this observed trace
only. This does not prove general compiler correctness, all traces, ledger
validity, or production readiness. The full 13-stage simulation still uses
`FakeReferenceExecutor`.
