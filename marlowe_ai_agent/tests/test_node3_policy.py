from __future__ import annotations

from marlowe_agent.node3_policy import (
    Node3Result,
    StructuredWarning,
    next_inconclusive_state,
    semantic_fingerprint,
)


def result(status: str, *, lint_errors: list[str] | None = None,
           notes: list[str] | None = None, elapsed: float = 1.0,
           fields: dict[str, object] | None = None) -> Node3Result:
    warnings = [] if status != "counterexample" else [
        StructuredWarning("TransactionPartialPay", fields or {
            "account": {"role_token": "Alice"},
            "payee": {"party": {"role_token": "Bob"}},
            "paid": 5,
            "expected": 6,
        })
    ]
    return Node3Result(
        lint_errors or [], ["lint warning"], status, warnings,
        {"transactions": []} if status == "counterexample" else None,
        notes or [], elapsed, contract={"pay": 6, "then": "close"},
    )


def test_decision_policy_all_outcomes() -> None:
    assert result("valid").decision == "pass"
    assert result("valid", lint_errors=["bad lint"]).decision == "fail"
    semantic_failure = result("counterexample")
    assert semantic_failure.decision == "fail"
    assert semantic_failure.errors
    assert result("indeterminate").decision == "inconclusive"
    assert result("timeout").decision == "inconclusive"
    assert result("valid", notes=["Merkleized continuation was not analyzed"]).decision == "inconclusive"


def test_findings_are_exactly_errors_plus_warnings() -> None:
    value = result("counterexample", lint_errors=["lint error"], notes=["note"])
    assert value.findings == value.errors + value.warnings


def test_inconclusive_status_adds_note_without_fake_error() -> None:
    value = result("unavailable")
    assert value.errors == []
    assert value.analysis_notes == ["SMT chưa kết luận: semantic_status=unavailable."]


def test_semantic_fingerprint_is_stable_and_structured() -> None:
    base = {"account": {"role_token": "A"}, "payee": {"party": {"role_token": "B"}}}
    first = result("counterexample", elapsed=1.25, fields={**base, "paid": 5, "expected": 6})
    second = result("counterexample", elapsed=99.0, fields={"expected": 6, **base, "paid": 5})
    changed = result("counterexample", elapsed=1.25, fields={**base, "paid": 4, "expected": 6})
    assert semantic_fingerprint(first) == semantic_fingerprint(second)
    assert semantic_fingerprint(first) != semantic_fingerprint(changed)


def test_inconclusive_counter_is_not_stall_tracker() -> None:
    count, reason = next_inconclusive_state(0, "inconclusive")
    assert (count, reason) == (1, "")
    count, reason = next_inconclusive_state(count, "inconclusive")
    assert (count, reason) == (2, "logic_inconclusive")
    assert next_inconclusive_state(count, "pass") == (0, "")
    assert next_inconclusive_state(1, "fail") == (0, "")
