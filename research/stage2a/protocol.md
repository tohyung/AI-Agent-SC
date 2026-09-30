# Stage 2A evaluation protocol (draft)

## Authority and review

The corpus is schema-neutral behavioral research data. It is not a production
`IntentSpec` schema, and an exact Marlowe AST is never the oracle for user
intent. Different ASTs can realize the same accepted behavior. Conversely, an
AST can pass structural and SMT-warning checks while violating a requirement.

Every record is initially a **candidate**. `draft` means model-authored proposal,
not human validation. A reviewer decides approve, edit or reject for each case
and its claims, then a separate adjudication task updates metadata. No
`reviewed`, `adjudicated` or `user_confirmed` annotation is claimed here. A
synthetic later user message inside a case is part of that case's requirement
history; it is not approval of the annotation by this project's user.

## Record semantics

- `case_id`, `split`, `family`, `group_id`: identity and leakage control.
- `requirement_history`: consecutive versions starting at 1. Each version has
  ordered messages. Later explicit corrections can supersede earlier claims.
- `behavior_scopes`: canonical-case registry of stable, case-local business
  scopes. Types are `global`, `transition`, `branch`, `timeout`, and
  `terminal_outcome`. Branches identify their decision and branch; timeouts
  have a distinct timeout identity and may reference a deadline claim. A scope
  ID is not a Marlowe AST path or a future compiler node ID. `global` is for
  genuinely branch-independent facts, not a default for missing context.
- `expected_resolution`: `accepted_interpretation`,
  `clarification_required`, `conflict_requires_resolution`, or
  `unsupported_for_current_study`. Ambiguity is a valid answer.
- `claims`: proposed normalized semantic facts. `evidence` names a version,
  message index and exact source span, but lexical grounding alone does not
  prove the interpretation. Each claim references one `scope_id` in its
  canonical case; two equal values in different branches remain two distinct
  claims. Active-value conflicts are keyed by `(kind, scope_id)`, while
  supersession also requires the same scope and later requirement evidence.
  Derived financial values also require a
  `normalization_basis`. `superseded_by` links an old claim to its later current
  successor. Critical roles distinguish Choice owner, depositing party,
  destination account owner, payment source account owner, recipient and
  transaction submitter; an unspecified submitter is valid and must not be
  inferred from the Choice or Deposit party.
- `required_clarifications` and `forbidden_assumptions`: what cannot be silently
  decided. Contradictory statements require user resolution, not a tie-breaker.
- `behavior_expectations`: proposed accepted/rejected abstract traces and
  terminal outcomes. They are not machine-checked gold until reviewed and
  executed against the pinned reference semantics where expressible.
- `mutation`: a controlled candidate implementation deviation. A mutation
  shares its parent's exact requirement history, family, group, split,
  resolution and required clarifications. Its own claims and scopes are empty;
  effective claims/scopes come from its canonical parent. It records an
  expected behavioral difference, not a new user intent. Behavior expectations,
  forbidden assumptions and review notes may differ.
- `annotation`: author and review status. All records in this seed are `draft`.
  `ground_truth_source` is coupled to status: `draft` to
  `candidate_research_annotation`, `reviewed` to
  `reviewed_research_annotation`, `adjudicated` to `expert_adjudicated`, and
  `user_confirmed` to `user_confirmed`. Drafts cannot claim human review.

The validator rejects duplicate identifiers, split/group leakage, invalid
versions, broken evidence references/spans, unsuperseded conflicting active
claims, unresolved critical facts in accepted cases, missing clarification or
conflict evidence, invalid mutation parents, and unsupported annotation status.
It checks structure and internal consistency; it **cannot** certify that the
proposed interpretation is what a human meant.

## Development/public-validation split

Canonical case and its controlled mutations remain in the same `group_id` and
split. Distinct development and validation groups use different requirement
texts, parties, amounts and deadlines. Identical requirement histories crossing
splits are rejected. The former public `evaluation` split is now `validation`:
it has already been exposed during schema development. It is useful for
debugging, regression and model selection, but is **not** a blind or
independent test set. Freezing and versioning this public set cannot reverse
prior exposure. The 32 cases remain a schema/protocol seed, not a statistically
adequate production benchmark.

A future hidden evaluation set must be created after the schema stabilizes,
reviewed/adjudicated by humans, versioned independently, and kept outside the
development/tuning agent's context (preferably outside its ordinary repo
visibility). Do not place a supposedly hidden JSONL in this public repo.
Schema hardening plus genuine human review of a meaningful candidate subset
and a sufficiently frozen development/public-validation protocol are required
before Stage 2B shadow experiments begin. A hidden set is not necessary for
every shadow experiment; it **is** required before accuracy/quality metrics
support production promotion. No reviewed-case count or promotion threshold is
invented in this patch.

## Reference execution and coverage

The reference harness calls pinned `Language.Marlowe.Semantics.computeTransaction`
sequentially with an explicit initial state. A failed transaction is recorded
at its index and stops the trace without committing its failed state. The
output records warning, payment, state and full remaining contract for each
successful step. `minTime` and each transaction interval are explicit. Before,
after and straddling-timeout interval classes are distinct; no wall-clock
timeout causes autonomous execution. The harness rejects Merkleized contracts
or inputs as `Unsupported` rather than guessing continuation bodies.

The authority is the pinned executable Core V1 semantics for **these explicit
traces**, not a universal proof, a signer/role-token authorization check, a
Cardano ledger validity check, or a testnet result. Choice owner and Deposit
party are semantic identities, not the physical transaction submitter. Future
coverage records must identify contracts, initial states, intervals, inputs and
trace depth actually executed. A historical transaction-count theorem is a
research lead, not a current completeness guarantee.

## Future prediction scoring

Metrics below apply only to human-reviewed, frozen cases with a versioned
prediction format. A critical claim match requires the same normalized kind,
value, `scope_id`/semantic scope and active requirement version. The referenced
scope carries branch or timing identity, so claims do not duplicate it. Mutations are
grouped with their parent when scoring, not counted as independent user-intent
observations. A zero denominator is reported as `N/A`, never as perfect score.

- **Critical Claim Precision:** number of predicted critical claims matching
  active reviewed claims / number of predicted critical claims. Invented or
  contradicted financial facts count as false positives.
- **Critical Claim Recall:** number of active reviewed critical claims recovered
  / number of active reviewed critical claims in accepted cases.
- **Unsafe Assumption Rate:** finalized cases containing at least one critical
  claim unsupported by active user evidence or required confirmation / all
  finalized cases. No finalization means the case is not in this denominator.
- **Required Clarification Recall:** cases labeled clarification/conflict that
  the system holds for user resolution / all reviewed clarification/conflict
  cases. Field-level question quality is audited separately.
- **Unnecessary Clarification Rate:** reviewed fully specified accepted cases
  where the system asks a question before acceptance / all reviewed fully
  specified accepted cases. Unsupported cases are excluded.
- **Unsafe Freeze Rate:** reviewed clarification/conflict cases that the system
  freezes without matching user resolution / all reviewed cases requiring user
  resolution. This safety metric takes priority over reducing extra questions.
- **Provenance Completeness:** predicted critical claims with a valid active
  source reference, exact span and, for derived values, a documented
  normalization basis / all predicted critical claims. Completeness does not
  imply semantic correctness.

Promotion thresholds will be set after baseline measurement, not invented from
this seed. Development/public-validation scores can guide research iteration,
but cannot alone substantiate production promotion. Reporting must include
denominators and confidence/coverage limits; promotion evidence needs an
independent hidden-evaluation protocol.

## Future assurance records

Assurance is multi-axis: `verdict` (`satisfied`, `violated`, `inconclusive`,
`unsupported`, `not_evaluated`), `method` (e.g. user confirmation, deterministic
validation, LLM review, SMT, reference execution, bounded exploration,
differential testing or ledger validation), `scope`, `coverage`, `evidence`, and
`assumptions`. `tested` is a method, not a verdict. SMT warning-freedom is not
intent correctness. A reference trace is an observation for that trace, not
exhaustive behavior. An `exhaustive` coverage label needs a proof that the
enumerated domain is complete. None of this is added to production models in
Stage 2A.
