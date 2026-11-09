"""Draft meaning against a reference contract: paths compared, choice labels ignored."""

import json

from research.experiments.formalization_semantics import compare_draft, fill_withheld, inline_lets
from research.formalization.fact_semantics import denote
from tests.formalization import test_fact_builder as tb


def _reference():
    return denote(tb.milestone_draft())


def test_same_behavior_matches_even_with_other_choice_names():
    text = json.dumps(_reference()).replace("s2", "first").replace("s3", "finish")
    assert compare_draft(tb.milestone_draft(), json.loads(text))["verdict"] == "MATCH"


def test_a_wrong_payee_is_different():
    draft = tb.milestone_draft()
    draft["outcomes"][0]["to"] = "p_lan"
    assert compare_draft(draft, _reference())["verdict"] == "DIFFERENT"


def test_an_open_time_is_not_denotable_until_it_is_filled():
    draft = tb.milestone_draft()
    draft["instants"][0]["expr"]["date"].update({"h": None, "min": None, "tz": None})
    assert compare_draft(draft, _reference())["verdict"] == "NOT_DENOTABLE"
    assert fill_withheld(draft)["instants"][0]["expr"]["date"]["tz"] == "+00:00"


def test_let_is_inlined():
    node = {"let": "x", "be": 5, "then": {"pay": {"use_value": "x"}, "then": "close"}}
    assert inline_lets(node) == {"pay": 5, "then": "close"}
