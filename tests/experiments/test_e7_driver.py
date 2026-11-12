import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def driver(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / "tools" / "e6"))
    spec = importlib.util.spec_from_file_location("e7_auto", ROOT / "tools" / "e7" / "auto.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    view = {"prompt": "Lan nạp 40 ADA trước 23:59 ngày 01/02/2027 giờ VN, trả cho Tú.",
            "language": "vi", "facts": ["Không ai bấm thì hoàn cho Lan."]}
    monkeypatch.setattr(module, "user_view", lambda index, dataset="v4": view)
    monkeypatch.setattr(module, "PIPE_DIR", tmp_path / "pipe")
    monkeypatch.setattr(module, "BASE_DIR", tmp_path / "base")
    (tmp_path / "pipe" / "case-001").mkdir(parents=True)
    return module


def _case(driver):
    return driver.PIPE_DIR / "case-001"


def test_need_writes_the_input_and_reply_records_an_accept(driver):
    assert driver._need(_case(driver), 1, "result", "Tôi hiểu hợp đồng như sau: ...") == 5
    text = (_case(driver) / "simuser-input.txt").read_text(encoding="utf-8")
    assert "YOUR LANGUAGE: Vietnamese" in text and "[RESULT" in text
    assert driver.reply("pipe", 1, '{"action": "accept", "message": ""}') == 0
    decision = driver._decision(_case(driver))
    assert decision["kind"] == "accept" and decision["for"] == "result"


def test_a_message_on_a_result_is_an_objection_whatever_the_label(driver):
    driver._need(_case(driver), 1, "result", "Tôi hiểu: Lan nạp 40 ADA trước 01/02/2026.")
    driver.reply("pipe", 1, '{"action": "answer", "message": "Sai năm, phải là 2027."}')
    decision = driver._decision(_case(driver))
    assert decision == {"kind": "message", "text": "Sai năm, phải là 2027.", "for": "result",
                        "shown": decision["shown"]}
    assert driver._log(_case(driver))["user_messages"] == 1


def test_a_rejected_reply_is_retried_twice_then_replaced(driver):
    driver._need(_case(driver), 1, "question", "Bạn có muốn bỏ phần hoàn tiền không?")
    bad = '{"action": "answer", "message": "Đồng ý bỏ phần đó, và trả 999 ADA."}'
    assert driver.reply("pipe", 1, bad) == 6
    assert driver.reply("pipe", 1, bad) == 6
    assert driver.reply("pipe", 1, bad) == 0
    decision = driver._decision(_case(driver))
    assert decision["text"] == driver.FALLBACK["vi"]
    turns = driver._log(_case(driver))["turns"]
    assert len(turns) == 3 and all(turn["problems"] for turn in turns)


def test_give_up_is_recorded(driver):
    driver._need(_case(driver), 1, "question", "Hạn là khi nào?")
    driver.reply("pipe", 1, '{"action": "give_up", "message": ""}')
    assert driver._decision(_case(driver))["kind"] == "give_up"


def test_a_message_that_only_agrees_accepts(driver):
    assert driver.plain_agreement("Yes, these are what I mean. Sam receiving the 250 ADA is fine with me.")
    assert driver.plain_agreement("Đúng rồi, như vậy là được.")
    assert not driver.plain_agreement("Yes, but the year should be 2027.")
    assert not driver.plain_agreement("Đúng, nhưng sai năm.")
    assert not driver.plain_agreement("The year is wrong.")


def _attempt(case_dir, number, record):
    (case_dir / f"attempt-{number:03d}.json").write_text(json.dumps(record), encoding="utf-8")


def test_a_compile_with_no_model_response_reruns_the_review_on_resume(driver, monkeypatch):
    case_dir = _case(driver)
    (case_dir / "scenarios.json").write_text(json.dumps({"intent_id": "c1", "scenarios": {}}),
                                             encoding="utf-8")
    failed = {"status": "BLOCKED", "stop_reason": "llm_error", "reviewed_candidate_id": "c1",
              "steps": {"compile": {"run_status": "FAILED",
                                    "safe_error": {"code": "provider_request_failed"}}}}
    _attempt(case_dir, 1, failed)
    compiled = {"status": "WAITING_RESEARCH_REVIEW", "reviewed_candidate_id": "c1",
                "steps": {"compile": {"run_status": "SUCCEEDED", "output_artifacts": ["k1"]}}}
    runs, seen = [], []
    monkeypatch.setattr(driver, "_pipe_run", lambda index, *args: (runs.append(args), (None, compiled))[1])
    monkeypatch.setattr(driver, "_scenarios",
                        lambda index, case_dir, record, candidate, spec: seen.append(record) or 0)
    assert driver._resume_scenarios(1, case_dir, failed) == 0
    assert runs == [("--review-candidate-id", "c1")]
    assert seen == [compiled]


def test_a_compiled_contract_resumes_its_scenarios_without_a_new_review(driver, monkeypatch):
    case_dir = _case(driver)
    (case_dir / "scenarios.json").write_text(json.dumps({"intent_id": "c1", "scenarios": {}}),
                                             encoding="utf-8")
    compiled = {"status": "BLOCKED", "reviewed_candidate_id": "c1",
                "steps": {"compile": {"run_status": "SUCCEEDED", "output_artifacts": ["k1"]}}}
    _attempt(case_dir, 1, compiled)
    monkeypatch.setattr(driver, "_pipe_run", lambda *a: pytest.fail("no new review expected"))
    monkeypatch.setattr(driver, "_scenarios", lambda index, case_dir, record, candidate, spec: 0)
    assert driver._resume_scenarios(1, case_dir, compiled) == 0
