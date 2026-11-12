from research.orchestration.cli_runner import RESTATE_MARK, restate_question

HISTORY = [{"version": 1, "messages": ["Tôi (Lan) nạp 40 ADA trước 23:59 ngày 01/02/2027 giờ VN."]}]


def test_draft_items_left_unrepaired_become_one_restate_question():
    question = restate_question(["p_lan: name 'x' not in its evidence",
                                 "i_d1: hour 23 not in evidence", "steps: expected one first step"],
                                HISTORY)
    assert question.startswith(RESTATE_MARK)
    assert "tên và vai của từng bên" in question and "các mốc thời gian" in question


def test_a_failure_naming_no_draft_item_is_not_the_users_to_fix():
    assert restate_question(["model output is not canonical JSON"], HISTORY) is None


def test_an_unsupported_part_asked_again_after_an_answer_is_kept():
    from research.orchestration.cli_runner import kept_unsupported

    question = 'This part cannot be represented yet: "Pull the price automatically.". Can it be dropped or restated?'
    transcript = [{"question": 'What is the name of "I"?\n' + question, "answer": "I still need it."}]
    assert kept_unsupported(["What is the name of \"Me\"?", question], transcript)
    assert not kept_unsupported([question], [])
    assert not kept_unsupported(['This part cannot be represented yet: "something else".'], transcript)
