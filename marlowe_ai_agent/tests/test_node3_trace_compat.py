from __future__ import annotations

import json

from bench.report import generate


def test_additive_node3_trace_schema_remains_report_compatible(tmp_path) -> None:
    event_data = {
        "findings": ["semantic failure", "lint warning"],
        "errors": ["semantic failure"],
        "warnings": ["lint warning"],
        "verification_backend": "marlowe-smt",
        "smt_status": "Counterexample",
        "smt_warnings": [{"type": "TransactionPartialPay", "paid": 5, "expected": 6}],
        "counterexample": {"transactions": []},
        "analysis_notes": [],
    }
    record = {
        "case_id": "trace-compat", "attempt": 1, "type": "escrow",
        "difficulty": 1, "language": "vi", "info_mode": "complete",
        "challenges": [], "status": "done", "stop_reason": "ok",
        "converged": True, "iterations": 1, "wall_seconds": 0.1,
        "cost_usd": None, "call_log": [], "judge": None,
        "evaluation": {"strict_correct": True, "false_convergence": False, "overall_accuracy": 1.0},
        "convergence_path": "S+S+L+", "prompt": "trace compatibility",
        "qa_transcript": [], "contract_description": "close",
        "trace": [{
            "node": "node_3_logic_graph_verification", "status": "fail",
            "message": "Đã kiểm Node 3.", "data": event_data,
        }],
    }
    (tmp_path / "runs.jsonl").write_text(
        json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8",
    )

    summary = generate(tmp_path)

    assert summary["counts"]["strict_correct"] == 1
    stored = json.loads((tmp_path / "runs.jsonl").read_text(encoding="utf-8"))
    data = stored["trace"][0]["data"]
    assert data["findings"] == data["errors"] + data["warnings"]
    assert data["verification_backend"] == "marlowe-smt"
    assert data["smt_status"] == "Counterexample"
    assert data["smt_warnings"][0]["expected"] == 6
    assert data["counterexample"] == {"transactions": []}
    assert data["analysis_notes"] == []
