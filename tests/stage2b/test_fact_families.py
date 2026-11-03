"""One hand-written, fully specified draft per dev contract family.

The drafts are synthetic (not dataset text). Each must build, pass the v4
validator and projector, denote, and on every path of ⟦D⟧ pay exactly the core's
outcome claims; with the Haskell toolchain also on the reference semantics and
SMT analyzer. They cover what the seeded generator does not: ge/lt guards,
native tokens, sums, several depositors and wait_until chains.
"""

import os
import shutil

import pytest

from research.integrations import reference_driver, smt_driver
from research.stage2b.fact_builder import FACT_DRAFT_VERSION, build_core
from research.stage2b.fact_semantics import denote, paths
from research.stage2b.intent_spec import validate_intent_spec, validate_shadow_semantic_core
from research.stage2b.projector import classify_projection, project_intent_spec
from tests.stage2b import test_fact_builder as tb
from tests.stage2b.fact_draft_gen import core_path

EMPTY_STATE = {"accounts": [], "choices": [], "boundValues": [], "minTime": 0}


class D:
    def __init__(self):
        self.spans = []
        self.d = {"schema_version": FACT_DRAFT_VERSION, "parties": [], "asset": {},
                  "quantities": [], "instants": [], "steps": [], "outcomes": [], "notes": {}}

    def ev(self, text):
        if text not in self.spans:
            self.spans.append(text)
        return [{"requirement_version": 1, "message_index": 0, "span": text,
                 "relation": "supports"}]

    def party(self, pid, name):
        self.d["parties"].append({"id": pid, "name": name, "evidence": self.ev(f"bên {name}")})

    def ada(self, phrase):
        self.d["asset"] = {"ada": True, "evidence": self.ev(phrase)}

    def q(self, qid, expr, phrase):
        self.d["quantities"].append({"id": qid, "expr": expr, "evidence": self.ev(phrase)})

    def date(self, iid, y, m, d):
        self.d["instants"].append({"id": iid, "expr": {"date": {
            "y": y, "m": m, "d": d, "h": 12, "min": 0, "tz": "+07:00"}},
            "evidence": self.ev(f"12:00 ngày {d:02d}/{m:02d}/{y} (UTC+7)")})

    def offset(self, iid, base, days):
        self.d["instants"].append({"id": iid, "expr": {"offset": {"from": base, "days": days}},
                                   "evidence": self.ev(f"{days} ngày sau hạn đầu")})

    def step(self, sid, **fields):
        self.d["steps"].append({"id": sid, **fields, "evidence": self.ev(f"bước {sid}")})

    def out(self, oid, kind, src, to, amount):
        self.d["outcomes"].append({"id": oid, "kind": kind, "from_account": src, "to": to,
                                   "amount": amount, "evidence": self.ev(f"khoản {oid}")})

    def done(self):
        return self.d, [{"version": 1, "messages": ["; ".join(self.spans) + "."]}]


def common(names, total):
    g = D()
    for i, name in enumerate(names):
        g.party(f"p{i}", name)
    g.ada(f"tổng {total} ADA")
    g.q("q_total", {"ada": str(total)}, f"tổng {total} ADA")
    g.date("i1", 2027, 1, 3)
    return g


def third_party():
    g = common(["Bình", "Giang", "Lan"], 20)
    g.offset("i2", "i1", 7)
    g.step("s1", kind="deposit", by="p0", into="p0", amount="q_total", deadline="i1",
           then="s2", on_timeout="end")
    g.step("s2", kind="choice", by="p2", bounds={"from": 0, "to": 100}, deadline="i2",
           branches=[{"guard": {"op": "ge", "value": 50}, "then": ["o_pay"]},
                     {"guard": {"op": "lt", "value": 50}, "then": ["o_back"]}],
           on_timeout=["o_back"])
    g.out("o_pay", "payment", "p0", "p1", "q_total")
    g.out("o_back", "refund", "p0", "p0", "remaining")
    return g.done()


def escrow_2party():
    g = common(["Nga", "Sơn"], 30)
    g.offset("i2", "i1", 7)
    g.step("s1", kind="deposit", by="p0", into="p0", amount="q_total", deadline="i1",
           then="s2", on_timeout="end")
    g.step("s2", kind="choice", by="p0", bounds={"from": 1, "to": 1}, deadline="i2",
           branches=[{"guard": {"op": "eq", "value": 1}, "then": ["o_pay"]}],
           on_timeout=["o_back"])
    g.out("o_pay", "payment", "p0", "p1", "q_total")
    g.out("o_back", "refund", "p0", "p0", "remaining")
    return g.done()


def escrow_3party():
    g = common(["Dũng", "Huy", "Nga"], 26)
    g.offset("i2", "i1", 7)
    g.step("s1", kind="deposit", by="p0", into="p0", amount="q_total", deadline="i1",
           then="s2", on_timeout="end")
    g.step("s2", kind="choice", by="p2", bounds={"from": 0, "to": 1}, deadline="i2",
           branches=[{"guard": {"op": "eq", "value": 1}, "then": ["o_pay"]},
                     {"guard": {"op": "eq", "value": 0}, "then": ["o_back"]}],
           on_timeout=["o_back"])
    g.out("o_pay", "release", "p0", "p1", "q_total")
    g.out("o_back", "refund", "p0", "p0", "remaining")
    return g.done()


def rental_deposit():
    g = common(["Chi", "Hà"], 23)
    g.q("q_fee", {"ada": "3"}, "giữ 3 ADA")
    g.offset("i2", "i1", 7)
    g.step("s1", kind="deposit", by="p0", into="p0", amount="q_total", deadline="i1",
           then="s2", on_timeout="end")
    g.step("s2", kind="choice", by="p1", bounds={"from": 0, "to": 1}, deadline="i2",
           branches=[{"guard": {"op": "eq", "value": 0}, "then": ["o_back"]},
                     {"guard": {"op": "eq", "value": 1}, "then": ["o_fee", "o_back"]}],
           on_timeout=["o_back"])
    g.out("o_fee", "payment", "p0", "p1", "q_fee")
    g.out("o_back", "refund", "p0", "p0", "remaining")
    return g.done()


def vesting():
    g = common(["Huy", "Nga"], 35)
    g.q("q_half", {"fraction": {"of": "q_total", "num": 1, "den": 2}}, "một nửa")
    g.q("q_rest", {"subtract": {"from": "q_total", "minus": ["q_half"]}}, "nửa còn lại")
    g.offset("i2", "i1", 7)
    g.offset("i3", "i1", 14)
    g.step("s1", kind="deposit", by="p0", into="p0", amount="q_total", deadline="i1",
           then="s2", on_timeout="end")
    g.step("s2", kind="wait_until", at="i2", then=["o_a", "s3"])
    g.step("s3", kind="wait_until", at="i3", then=["o_b"])
    g.out("o_a", "release", "p0", "p1", "q_half")
    g.out("o_b", "release", "p0", "p1", "q_rest")
    return g.done()


def loan():
    g = common(["Chi", "Hà"], 83)
    g.q("q_fee", {"ada": "2"}, "thêm 2 ADA")
    g.q("q_repay", {"sum": ["q_total", "q_fee"]}, "cả gốc và thêm 2 ADA")
    g.date("i2", 2027, 1, 13)
    g.step("s1", kind="deposit", by="p0", into="p0", amount="q_total", deadline="i1",
           then=["o_lend", "s2"], on_timeout="end")
    g.step("s2", kind="deposit", by="p1", into="p1", amount="q_repay", deadline="i2",
           then=["o_repay"], on_timeout="end")
    g.out("o_lend", "payment", "p0", "p1", "q_total")
    g.out("o_repay", "payment", "p1", "p0", "q_repay")
    return g.done()


def cancellation_fee():
    g = common(["Dũng", "Huy"], 86)
    g.q("q_fee", {"ada": "3"}, "phí cố định 3 ADA")
    g.offset("i2", "i1", 7)
    g.step("s1", kind="deposit", by="p0", into="p0", amount="q_total", deadline="i1",
           then="s2", on_timeout="end")
    g.step("s2", kind="choice", by="p0", bounds={"from": 1, "to": 1}, deadline="i2",
           branches=[{"guard": {"op": "eq", "value": 1}, "then": ["o_fee", "o_back"]}],
           on_timeout=["o_all"])
    g.out("o_fee", "payment", "p0", "p1", "q_fee")
    g.out("o_back", "refund", "p0", "p0", "remaining")
    g.out("o_all", "payment", "p0", "p1", "remaining")
    return g.done()


def crowdfunding():
    g = common(["An", "Dũng", "Huy"], 77)
    g.q("q_half", {"fraction": {"of": "q_total", "num": 1, "den": 2}}, "mỗi người một nửa")
    g.offset("i2", "i1", 7)
    g.step("s1", kind="deposit", by="p0", into="p0", amount="q_half", deadline="i1",
           then="s2", on_timeout="end")
    g.step("s2", kind="deposit", by="p1", into="p1", amount="q_half", deadline="i2",
           then=["o_a", "o_b"], on_timeout=["o_back"])
    g.out("o_a", "payment", "p0", "p2", "q_half")
    g.out("o_b", "payment", "p1", "p2", "q_half")
    g.out("o_back", "refund", "p0", "p0", "remaining")
    return g.done()


FAMILIES = {
    "third_party": third_party, "escrow_2party": escrow_2party,
    "escrow_3party": escrow_3party, "rental_deposit": rental_deposit,
    "vesting": vesting, "loan": loan, "cancellation_fee": cancellation_fee,
    "crowdfunding": crowdfunding,
    "milestone": lambda: (tb.milestone_draft(), tb.HISTORY),
    "swap": lambda: (tb.swap_draft(f"native:{tb.POLICY}/474f4c44"), tb.SWAP_HISTORY),
}


def _built(name):
    draft, history = FAMILIES[name]()
    core = build_core(draft, history)
    return draft, history, core


@pytest.mark.parametrize("name", sorted(FAMILIES))
def test_family_draft_builds_passes_v4_and_pays_what_the_core_claims(name):
    draft, history, core = _built(name)
    errors = validate_shadow_semantic_core(core, expected_history=history)
    projection = project_intent_spec(core, expected_history=history)
    full = validate_intent_spec(projection.intent_spec.to_dict(), expected_history=history,
                                projected_core=core)
    assert classify_projection(errors, full, projection.projection_diagnostics) == "PASS"
    assert core["predicted_resolution"] == "accepted_interpretation"
    for run in paths(denote(draft)):
        outcomes, _ = core_path(core, run.moves)
        assert run.payments[:len(outcomes)] == outcomes, run.moves
        assert not run.partial_pays


def _toolchain():
    if os.environ.get("MARLOWE_REFERENCE_VIA_WSL") != "1" and (
            shutil.which("cabal") is None or shutil.which("ghc") is None):
        pytest.skip("cabal/GHC unavailable; real Haskell reference not exercised")


@pytest.mark.parametrize("name", sorted(FAMILIES))
def test_family_draft_on_reference_semantics_and_smt(name):
    _toolchain()
    draft, _history, _core = _built(name)
    contract = denote(draft)
    for run in paths(contract):
        result = reference_driver.execute({"contract": contract, "state": EMPTY_STATE,
                                           "transactions": run.transactions})
        assert result["status"] == "Success" and result["final_contract"] == "close"
        assert [step["warnings"] for step in result["steps"] if step["warnings"]] == []
        paid = [(payment["source_account"]["role_token"],
                 payment["payee"]["party"]["role_token"], payment["amount"])
                for step in result["steps"] for payment in step["payments"]]
        assert paid == run.payments, run.moves
    assert smt_driver.analyze(contract)["status"] == "Valid"
