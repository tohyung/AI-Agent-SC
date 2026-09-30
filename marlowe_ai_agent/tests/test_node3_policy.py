from __future__ import annotations

import pytest

from marlowe_agent.node3_policy import (
    Node3Finding,
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


@pytest.mark.parametrize(("status", "expected"), [
    ("valid", "pass"), ("counterexample", "fail"),
    ("indeterminate", "inconclusive"), ("timeout", "inconclusive"),
    ("invalid_input", "inconclusive"), ("unavailable", "inconclusive"),
])
def test_production_policy_statuses(status: str, expected: str) -> None:
    value = result(status)
    assert value.decision == expected
    assert value.findings == value.errors + value.warnings


def test_not_run_lint_failure_and_valid_with_notes() -> None:
    assert result("not_run", lint_errors=["bad lint"]).decision == "fail"
    assert result("not_run", lint_errors=["bad lint"]).analysis_notes == []
    assert result("valid", notes=["incomplete"]).decision == "inconclusive"


@pytest.mark.parametrize("warnings", [
    [], [StructuredWarning("FutureWarning", {})],
    [StructuredWarning("TransactionPartialPay", {"expected": 20})],
])
def test_counterexample_renderer_fallback_never_crashes(warnings) -> None:
    value = result("counterexample")
    value.semantic_warnings = warnings
    assert value.decision == "fail"
    assert value.errors
    assert value.findings == value.errors + value.warnings


def test_node3_result_serializes_compatible_fields_without_contract() -> None:
    value = result("counterexample")
    value.graph = {"nodes": [{"id": "root"}], "edges": []}
    value.paths_explored = 2
    payload = value.to_dict()
    assert {"passed", "findings", "graph", "errors", "warnings", "paths_explored",
            "verification_backend", "smt_status", "smt_warnings", "counterexample",
            "analysis_notes", "smt_elapsed_seconds", "lint_errors", "lint_warnings"} <= payload.keys()
    assert "contract" not in payload
    assert payload["smt_warnings"][0]["type"] == "TransactionPartialPay"
    assert payload["paths_explored"] == 2
    assert payload["structured_findings"] == []


def test_path_aware_error_only_uses_verified_location() -> None:
    value = result("counterexample")
    value.structured_findings = [Node3Finding(
        "smt", "TransactionPartialPay", {}, "partial payment", "root.pay", "verified",
        "counterexample_replay",
    )]
    assert value.errors == ["Tại `root.pay`: partial payment"]
    assert value.to_dict()["structured_findings"][0]["ast_path"] == "root.pay"
    value.structured_findings[0].path_status = "unmapped"
    assert value.errors == ["partial payment"]


def test_fingerprint_does_not_depend_on_mapper_metadata() -> None:
    first, second = result("counterexample", elapsed=1.0), result("counterexample", elapsed=99.0)
    first.structured_findings = [Node3Finding(
        "smt", "TransactionPartialPay", {}, "one", "root.pay", "verified", "counterexample_replay",
    )]
    second.structured_findings = [Node3Finding(
        "smt", "TransactionPartialPay", {}, "two", None, "unmapped", "replay_invalid",
    )]
    assert semantic_fingerprint(first) == semantic_fingerprint(second)
