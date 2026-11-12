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
