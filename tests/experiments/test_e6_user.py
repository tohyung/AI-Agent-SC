"""E6 automatic simulated user: fixed reply sequence from the fact sheet."""

from research.experiments import e6_user


def test_reply_sequence_with_a_fact_sheet():
    view = e6_user.user_view(2)  # v3-en-escrow-002 has four facts
    assert set(view) == {"id", "prompt", "language", "fact_sheet"}
    first = e6_user.reply(view, 0)
    assert first.startswith("More details:") and "I'm Priya." in first and first.count("\n- ") == 4
    assert e6_user.reply(view, 1) == "I don't have any other information."
    assert e6_user.reply(view, 2) is None


def test_reply_sequence_with_an_empty_fact_sheet():
    view = e6_user.user_view(1)
    assert view["fact_sheet"] == []
    assert e6_user.reply(view, 0).startswith("Tôi không có thêm thông tin; hãy làm")
    assert e6_user.reply(view, 1) == "Tôi không có thêm thông tin nào khác."
