"""E6 baseline arm: request cap, forwarded errors, waiting states and request counting."""

from __future__ import annotations

import json

import pytest

from research.adapters.model_transport import ModelTransportError
from research.experiments import baseline_llm as bl

GOOD = {"when": [], "timeout": 1, "timeout_continuation": "close"}


class FakeModel:
    """Returns queued replies; an exception in the queue is raised like the transport would."""

    model = "fake"

    def __init__(self, replies):
        self.replies = list(replies)
        self.call_log = []
        self.budget = None

    def set_call_budget(self, limit):
        self.budget = limit

    def generate(self, system, user):
        reply = self.replies.pop(0)
        self.call_log.append({"phase": "generation", "status": "ok", "prompt_tokens": 10,
                              "completion_tokens": 5, "total_tokens": 15})
        if isinstance(reply, Exception):
            self.call_log[-1]["status"] = "error"
            raise reply
        return reply


def check_ok_if_good(contract):
    if contract == GOOD:
        return {"passed": True, "stage": "ledger", "messages": [], "ledger": "REACHED_LEDGER_PASS"}
    return {"passed": False, "stage": "structure", "messages": ["root: bad shape"]}


def contract(value, message="Hợp đồng ký quỹ."):
    return {"type": "contract", "message": message, "contract": value}


def test_failed_checks_are_forwarded_until_a_contract_passes(tmp_path):
    model = FakeModel([contract({"bad": 1}), {"nope": 1}, contract(GOOD)])
    session = bl.run(1, cap=5, run_dir=tmp_path, model=model, check=check_ok_if_good)
    assert session["status"] == "awaiting_review"
    assert session["delivered_contract"] == GOOD
    assert session["forwarded_errors"] == 2 and session["user_turns"] == 0
    forwarded = [turn["content"] for turn in session["transcript"]
                 if turn.get("source") == "forwarded_error"]
    assert "root: bad shape" in forwarded[0] and "Sửa lại" in forwarded[0]
    assert '"type"' in forwarded[1]
    assert bl.counted_requests(session["call_log"]) == 3
    stored = json.loads((tmp_path / "case-001" / "session.json").read_text(encoding="utf-8"))
    assert stored == session


def test_cap_stops_the_arm_and_bounds_the_transport_budget(tmp_path):
    model = FakeModel([contract({"bad": 1})] * 3)
    session = bl.run(1, cap=2, run_dir=tmp_path, model=model, check=check_ok_if_good)
    assert session["status"] == "cap_reached"
    assert bl.counted_requests(session["call_log"]) == 2
    assert session["delivered_contract"] is None
    assert model.budget == 1  # the second call may use only what is left of the cap
    with pytest.raises(ValueError, match="already ended"):
        bl.run(1, message="tiếp", run_dir=tmp_path, model=model, check=check_ok_if_good)


def test_question_waits_for_the_simulated_user_and_the_answer_resumes(tmp_path):
    model = FakeModel([{"type": "question", "message": "Hạn nạp là khi nào?"}, contract(GOOD)])
    session = bl.run(2, cap=4, run_dir=tmp_path, model=model, check=check_ok_if_good)
    assert session["status"] == "awaiting_answer"
    with pytest.raises(ValueError, match="waits for the simulated user"):
        bl.run(2, run_dir=tmp_path, model=model, check=check_ok_if_good)
    session = bl.run(2, message="Trước 18:00 ngày 10/04/2027 UTC.", run_dir=tmp_path,
                     model=model, check=check_ok_if_good)
    assert session["status"] == "awaiting_review" and session["user_turns"] == 1
    session = bl.run(2, finish="accept", run_dir=tmp_path, model=model, check=check_ok_if_good)
    assert session["status"] == "accepted"
    assert bl.summary(session)["requests"] == 2 and bl.summary(session)["delivered"]


def test_quota_errors_are_not_counted_and_the_run_resumes(tmp_path):
    model = FakeModel([ModelTransportError("provider_limit", "generation"), contract(GOOD)])
    session = bl.run(1, cap=1, run_dir=tmp_path, model=model, check=check_ok_if_good)
    assert session["status"] == "provider_limit"
    assert bl.counted_requests(session["call_log"]) == 0
    session = bl.run(1, run_dir=tmp_path, model=model, check=check_ok_if_good)
    assert session["status"] == "awaiting_review"
    assert bl.counted_requests(session["call_log"]) == 1


def test_model_errors_with_a_response_are_counted_and_forwarded(tmp_path):
    model = FakeModel([ModelTransportError("invalid_json_after_repair", "model_output_parse"),
                       contract(GOOD)])
    session = bl.run(1, cap=3, run_dir=tmp_path, model=model, check=check_ok_if_good)
    assert session["status"] == "awaiting_review"
    assert bl.counted_requests(session["call_log"]) == 2 and session["forwarded_errors"] == 1


def test_a_new_session_needs_a_cap_and_a_started_cap_is_fixed(tmp_path):
    model = FakeModel([{"type": "decline", "message": "Không làm được."}])
    with pytest.raises(ValueError, match="needs --cap"):
        bl.run(1, run_dir=tmp_path, model=model, check=check_ok_if_good)
    session = bl.run(1, cap=3, run_dir=tmp_path, model=model, check=check_ok_if_good)
    assert session["status"] == "awaiting_reaction"
    with pytest.raises(ValueError, match="cannot change"):
        bl.run(1, cap=4, finish="accept", run_dir=tmp_path, model=model, check=check_ok_if_good)
    assert bl.run(1, finish="accept", run_dir=tmp_path, model=model,
                  check=check_ok_if_good)["status"] == "accepted"


def test_the_arm_sees_only_id_prompt_and_language():
    assert set(bl.load_case(1)) == {"id", "prompt", "language"}
    assert set(bl.load_case(56, "dev")) == {"id", "prompt", "language"}
    with pytest.raises(ValueError, match="dev cases 1-56"):
        bl.load_case(57, "dev")


def test_structure_checker_reports_validator_errors_without_a_ledger():
    check = bl.make_checker(None)
    assert check("close")["passed"] is True
    result = check({"pay": "x"})
    assert result["passed"] is False and result["stage"] == "structure" and result["messages"]


def test_one_counting_rule_skips_calls_without_a_response():
    log = [{"status": "ok"}, {"status": "error", "exception_type": "RateLimitError"},
           {"status": "error", "provider_error_code": 429}, {"status": "error", "provider_error_code": 500},
           {"status": "error", "exception_type": "APIConnectionError"}, {"status": "empty"},
           {"status": "error", "exception_type": "InternalServerError"},
           {"status": "error", "provider_error_code": 400}]
    assert bl.counted_requests(log) == 3


def test_pipeline_requests_sum_over_attempt_records(tmp_path):
    for number, log in ((1, [{"status": "ok"}, {"status": "error", "exception_type": "RateLimitError"}]),
                        (2, [{"status": "ok"}, {"status": "ok"}])):
        (tmp_path / f"attempt-{number:03d}.json").write_text(
            json.dumps({"model_call_log_this_attempt": log}), encoding="utf-8")
    assert bl.pipeline_requests(tmp_path) == 3
    with pytest.raises(ValueError, match="no pipeline attempt"):
        bl.pipeline_requests(tmp_path / "missing")
