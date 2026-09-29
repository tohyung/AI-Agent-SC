# Stage 0.8 — Logic Graph versus SMT coverage

## Conclusion

**SMT can replace the path-reasoning part of Logic Graph without losing
coverage, provided the deterministic lints listed below are retained.** On the
shared semantic warnings, SMT matched the concrete checks and uniquely found
symbolic partial pay, Let shadowing, and assertion failure. It also eliminated
the deliberately constructed infeasible-branch false positive. SMT does not
replace same-`When` overlap checks, undefined-reference diagnostics, draft/AST
consistency, structural warnings, graph construction, or continuation analysis
behind a `MerkleizedCase` hash.

This conclusion is based on 33 contracts run through both implementations: six
completed audits, all 15 Stage 0.7b corpus files, and 12 isolated hand-written
cases. The result table is
[`results.csv`](../../tools/marlowe_smt/compare/results.csv).

## What Logic Graph actually reports

The source review confirmed most of the Stage 0.8 premise, with three
corrections. `check_draft_consistency` blocks only unknown AST roles; missing
draft parties, amount, deposit timeout, and decision timeout are warnings.
`MerkleizedCase` is rejected by the Python validator before graph traversal,
not treated as an ordinary case. Finally, an undefined `use_value` is a precise
Logic Graph structural error, while SMT interprets the missing bound value as
zero and reports the downstream semantic warning (for the test, non-positive
pay), not the missing definition itself.

| Layer | Detection | Result class | Blocking? |
|---|---|---|---|
| Validation | Unsupported/malformed Core V1 shape | `errors` | yes |
| Python path reasoning | literal non-positive Deposit/Pay; literal partial Pay | `errors` | yes |
| Python path reasoning | symbolic value unsupported, path count truncated | `warnings` | no |
| Reference lint | undefined `use_value` | `errors` | yes |
| Reference lint | unchosen `value_of_choice` / `chose_something_for` | `warnings` | no |
| Same-When lint | duplicate action; overlapping bounds for one Choice ID | `errors` | yes |
| Structural lint | empty When, inner timeout not above outer timeout, positive balance at Close, constant-condition dead branch | `warnings` | no |
| Draft consistency | AST role absent from `draft.parties` | `errors` | yes |
| Draft consistency | unused draft party; amount/deposit/decision timeout absent from AST | `warnings` | no |
| Missing semantic checks | Let shadowing and Assert failure | no finding | no |

`passed` is exactly `not errors`; warnings never block.

## Experimental coverage matrix

“Always” below means for the isolated corpus case, not a universal proof over
all Marlowe programs.

| Error or feature | Logic Graph | SMT | Classification | Evidence |
|---|---|---|---|---|
| Deposit ≤ 0 | always, concrete value | always | SMT fully replaces path check | `01-nonpositive-deposit` |
| Pay ≤ 0 | always, concrete value | always | SMT fully replaces path check | `02-nonpositive-pay` |
| Partial Pay, concrete amount/balance | always | always | SMT fully replaces path check | `03-literal-partial-pay`, `C1-n1-k1` |
| Partial Pay, symbolic Choice amount | no blocking error; vague unknown warning | always | SMT only for semantic error | `04-symbolic-partial-pay` |
| Let shadowing | no | always | SMT only | `05-let-shadowing` |
| Assertion can fail | no | always | SMT only | `06-symbolic-assertion` |
| Duplicate action in one When | always | no | SMT replacement requires retained lint | `07-duplicate-action` |
| Overlapping bounds for same Choice ID | always | no | SMT replacement requires retained lint | `08-overlapping-choice-bounds` |
| Undefined `use_value` | precise structural error | only downstream value=0 warning | SMT replacement requires retained reference lint | `09-undefined-use-value` |
| Draft role mismatch | always | N/A by design | only `check_draft_consistency` | `10-draft-mismatch` |
| Draft amount/timeout mismatch | warning only | N/A by design | only `check_draft_consistency` | `10-draft-mismatch` |
| Infeasible symbolic If branch containing partial Pay | false blocking error | proves Valid | SMT fully replaces path check and removes false positive | `11-infeasible-if-partial-pay` |
| Merkleized continuation | rejects `merkleized_then` shape; no continuation analysis | accepts outer case, records analysis note, cannot inspect hash continuation | neither analyzes continuation | `12-merkleized-case` |

## False-positive hypothesis

The hypothesis is confirmed. Case 11 chooses `amount` in [0,10], then tests
`amount > 10`. Its Pay-from-empty branch is impossible. Logic Graph explores
both branches unconditionally and emits a blocking partial-pay error at
`root.when[0].then.then.pay`. SMT uses the Choice bound, proves the branch
unreachable, and returns `Valid` with no warnings.

No unintended instance occurred in the real/known-valid inputs:

- all six completed audits: Logic Graph passed and SMT returned Valid;
- all 12 F1–F5 representatives for which SMT returned Valid at 60/90 seconds:
  Logic Graph passed with no errors;
- four F3 representatives produced a nonblocking “unknown value” warning;
- the two C1 controls were correctly caught by both tools;
- F3 n=128,k=1 was not counted as SMT-confirmed Valid in this run because the
  current 90-second hard limit returned `Timeout`. Its Stage 0.7b unrestricted
  measurement was Valid, and Logic Graph passed it with one nonblocking unknown
  warning.

The Stage 0.8 premise that every `valid-corpus` file “by definition” returns
Valid needed correction: the corpus intentionally includes two C1
Counterexample controls, and the retained F3 n=128 endpoint exceeds the new
operating deadline.

## Logic Graph code that SMT can replace

Do not delete the traversal wholesale; several lints are path-sensitive. In a
future implementation, the following numeric/symbolic path-reasoning pieces can
be removed after SMT is wired in:

- `_evaluate()`;
- `PathState.balances` and numeric values in `PathState.bound_values`;
- the Deposit branch's amount evaluation, non-positive check, and balance
  update;
- the Pay branch's amount/balance evaluation, non-positive/partial-pay checks,
  transfer calculation, and account updates;
- the Let branch's value evaluation and numeric assignment (retain only a set
  of defined names for reference linting);
- the nonconstant If behavior as a feasibility approximation; traversal may
  still visit both children for structural linting but must not issue semantic
  balance errors;
- the shared `unknown` flag and “cannot fully statically evaluate” warning;
- semantic path enumeration solely for Pay/Deposit/Let/If state. The current
  Assert branch has no semantic check to preserve.

## Logic Graph code that must remain

- `validate_contract()` as the Python-side grammar gate, reconciled later with
  driver support for `MerkleizedCase`;
- `check_draft_consistency()`;
- `_check_case_overlap()`;
- `_inspect_refs()` for undefined `use_value` and unchosen Choice references;
- structural traversal for empty When, timeout nesting, Close remainder,
  constant dead branch, and MAX_PATHS/truncation policy;
- `_build_graph()` if downstream UI/audit consumers still require graph nodes
  and edges;
- a lightweight lint state containing defined Let names, chosen Choice IDs,
  deadline context, and any data needed for structural warnings.

The undefined-`use_value` result demonstrates why the reference lint must run
before SMT. The driver does not reject the term: Marlowe evaluates the missing
bound value as zero, producing `TransactionNonPositivePay`. That warning is
semantically real but loses the actionable cause and exact missing name
`missing` supplied by `_inspect_refs`.

## Proposed Node 3 shape (design only)

1. Run a deterministic AST/draft lint layer first. It returns path-addressed
   blocking structural errors and nonblocking warnings. Stop before SMT on
   malformed input, duplicate/overlapping cases, undefined references, or
   blocking draft inconsistency.
2. Run the packaged SMT process with the 60-second solver and 90-second hard
   deadline. Only `Valid` passes. `Counterexample` becomes a blocking semantic
   result; `Indeterminate`/`Timeout` remain inconclusive and request
   simplification/escalation rather than claiming the contract is wrong.
3. Merge the two layers into a new result type with explicit `lint_errors`,
   `lint_warnings`, `semantic_status`, `semantic_warnings`, `counterexample`,
   and `analysis_notes`. A compatibility adapter can populate
   `LogicGraphResult.passed`, `errors`, `warnings`, and `findings` while Node 1
   is migrated.
4. Add an AST-location mapper. SMT warnings identify semantic objects and a
   transaction trace, but not the source path. Case 4, for example, reports
   `TransactionPartialPay` with account Alice, `expected=6`, `paid=5`, and a
   trace choosing amount 6. Logic Graph supplies no error at all, while the
   repair prompt needs the AST location
   `root.when[0].then.when[0].then.pay`. The mapper should replay/match the trace
   against the AST and emit a suggestion such as “at PATH, cap Pay at available
   balance or strengthen the Choice bound.” Preserve the raw warning and trace
   for audit; never synthesize a path without a verified match.

## Verified and not verified

Verified: all 33 corpus entries, all five SMT warning constructors, same-When
lints, reference lint, draft mismatch behavior, infeasible-branch false
positive, MerkleizedCase boundary, six completed audits, all Stage 0.7b
representatives, current timeout behavior, build/tests, and pinned upstream
integrity.

Not verified: arbitrary contracts outside this corpus, initial non-empty state
interaction with Logic Graph (it has no state input), complete semantic parity,
mapping every SMT trace back to a unique AST path, behavior after Node 3
integration, and the hidden continuation of a MerkleizedCase. No production
code was changed.
