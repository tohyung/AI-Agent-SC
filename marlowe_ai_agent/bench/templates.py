"""Reference contracts and hand-specified behavioral expectations."""

from __future__ import annotations

from typing import Any

from marlowe_agent.marlowe_ast import (ada, case, choice_action, close, deposit,
                                       escrow_contract, if_, let, pay, role, when)


def _token(name: str) -> dict[str, str]:
    return ada() if not name else {"currency_symbol": "benchmark", "token_name": name}


def _deposit(account: str, party: str, amount: int, token: str = "") -> dict[str, Any]:
    action = deposit(account, party, amount)
    action["of_token"] = _token(token)
    return action


def _pay(account: str, party: str, amount: int, then: Any = "close", token: str = "") -> dict[str, Any]:
    node = pay(account, party, amount, then)
    node["token"] = _token(token)
    return node


def _step(kind: str, at: str, who: str = "", amount: int = 0, token: str = "",
          name: str = "", value: int = 0) -> dict[str, Any]:
    out: dict[str, Any] = {"kind": kind, "at": at}
    if who:
        out["party"] = who
    if kind == "deposit":
        out.update(amount=amount, token=token)
    if kind == "choice":
        out.update(name=name, value=value)
    return out


def _scenario(name: str, steps: list[dict[str, Any]], received: dict[str, dict[str, int]],
              closed: bool = True) -> dict[str, Any]:
    return {"name": name, "steps": steps, "received": received, "closed": closed}


def build(kind: str, p: dict[str, Any]) -> tuple[Any, list[dict[str, Any]]]:
    """p.roles maps business IDs to concrete role names; amounts are base units."""
    r = p["roles"]
    amount, t1, t2, t3 = p["amount"], p["t1"], p["t2"], p["t3"]
    b = "before_t1"
    m = "after_t1_before_t2"
    a = "after_all"
    if kind == "infeasible":
        return close(), [_scenario("no_fabricated_transfer", [], {})]
    if kind == "escrow_2party":
        contract = escrow_contract(r["buyer"], r["seller"], amount, t1, t2)
        dep = _step("deposit", b, r["buyer"], amount)
        scenarios = [
            _scenario("approved", [dep, _step("choice", m, r["buyer"], name="approve", value=1)],
                      {r["seller"]: {"": amount}}),
            _scenario("rejected", [dep, _step("choice", m, r["buyer"], name="reject", value=0)],
                      {r["buyer"]: {"": amount}}),
            _scenario("decision_timeout", [dep, _step("advance", a)], {r["buyer"]: {"": amount}}),
            _scenario("no_deposit", [_step("advance", a)], {}),
        ]
    elif kind == "escrow_3party":
        decision = when([
            case(choice_action("release", r["arbiter"], 1, 1), _pay(r["buyer"], r["seller"], amount)),
            case(choice_action("refund", r["arbiter"], 0, 0), _pay(r["buyer"], r["buyer"], amount)),
        ], t2, _pay(r["buyer"], r["buyer"], amount))
        contract = when([case(deposit(r["buyer"], r["buyer"], amount), decision)], t1)
        dep = _step("deposit", b, r["buyer"], amount)
        scenarios = [
            _scenario("arbiter_release", [dep, _step("choice", m, r["arbiter"], name="release", value=1)],
                      {r["seller"]: {"": amount}}),
            _scenario("arbiter_refund", [dep, _step("choice", m, r["arbiter"], name="refund", value=0)],
                      {r["buyer"]: {"": amount}}),
            _scenario("arbiter_silent", [dep, _step("advance", a)], {r["buyer"]: {"": amount}}),
        ]
    elif kind == "swap":
        units = p["units"]
        second = when([case(_deposit(r["seller"], r["seller"], units, "GOLD"),
                            _pay(r["buyer"], r["seller"], amount,
                                 _pay(r["seller"], r["buyer"], units, token="GOLD")))], t2)
        contract = when([case(deposit(r["buyer"], r["buyer"], amount), second)], t1)
        dep1 = _step("deposit", b, r["buyer"], amount)
        scenarios = [
            _scenario("exchange", [dep1, _step("deposit", m, r["seller"], units, "GOLD")],
                      {r["buyer"]: {"GOLD": units}, r["seller"]: {"": amount}}),
            _scenario("other_side_absent", [dep1, _step("advance", a)], {r["buyer"]: {"": amount}}),
            _scenario("first_side_absent", [_step("advance", a)], {}),
        ]
    elif kind == "loan":
        repayment = amount + p["fee"]
        contract = when([case(deposit(r["lender"], r["lender"], amount),
                              _pay(r["lender"], r["borrower"], amount,
                                   when([case(_deposit(r["borrower"], r["borrower"], repayment),
                                              _pay(r["borrower"], r["lender"], repayment))], t2)))], t1)
        scenarios = [
            _scenario("repaid", [_step("deposit", b, r["lender"], amount),
                                  _step("deposit", m, r["borrower"], repayment)],
                      {r["borrower"]: {"": amount}, r["lender"]: {"": repayment}}),
            _scenario("not_repaid", [_step("deposit", b, r["lender"], amount), _step("advance", a)],
                      {r["borrower"]: {"": amount}}),
        ]
    elif kind == "vesting":
        first = amount // 2
        contract = when([case(deposit(r["employer"], r["employer"], amount),
                              when([], t2, _pay(r["employer"], r["worker"], first,
                                                when([], t3, _pay(r["employer"], r["worker"], amount - first)))))], t1)
        scenarios = [
            _scenario("first_tranche", [_step("deposit", b, r["employer"], amount),
                                        _step("advance", "after_t2_before_t3")],
                      {r["worker"]: {"": first}}, False),
            _scenario("all_tranches", [_step("deposit", b, r["employer"], amount), _step("advance", a)],
                      {r["worker"]: {"": amount}}),
        ]
    elif kind == "milestone":
        first = amount // 2
        second = when([case(choice_action("finish", r["client"], 1, 1),
                            _pay(r["client"], r["worker"], amount - first))], t3)
        first_stage = when([case(choice_action("first", r["client"], 1, 1),
                                 _pay(r["client"], r["worker"], first, second))], t2)
        contract = when([case(deposit(r["client"], r["client"], amount), first_stage)], t1)
        scenarios = [
            _scenario("both_accepted", [_step("deposit", b, r["client"], amount),
                                        _step("choice", m, r["client"], name="first", value=1),
                                        _step("choice", "after_t2_before_t3", r["client"], name="finish", value=1)],
                      {r["worker"]: {"": amount}}),
            _scenario("first_only", [_step("deposit", b, r["client"], amount),
                                     _step("choice", m, r["client"], name="first", value=1),
                                     _step("advance", a)],
                      {r["worker"]: {"": first}, r["client"]: {"": amount - first}}),
        ]
    elif kind == "crowdfunding":
        half = amount // 2
        second = when([case(deposit(r["funder_b"], r["funder_b"], amount - half),
                            _pay(r["funder_a"], r["project"], half,
                                 _pay(r["funder_b"], r["project"], amount - half)))], t2)
        contract = when([case(deposit(r["funder_a"], r["funder_a"], half), second)], t1)
        scenarios = [
            _scenario("threshold_met", [_step("deposit", b, r["funder_a"], half),
                                        _step("deposit", m, r["funder_b"], amount - half)],
                      {r["project"]: {"": amount}}),
            _scenario("threshold_missed", [_step("deposit", b, r["funder_a"], half), _step("advance", a)],
                      {r["funder_a"]: {"": half}}),
        ]
    elif kind == "third_party":
        cid = {"choice_name": "price", "choice_owner": role(r["reporter"])}
        decision = when([case(choice_action("price", r["reporter"], 0, 100),
                              let("reported_price", {"value_of_choice": cid},
                                  if_({"value": {"use_value": "reported_price"}, "ge_than": p["threshold"]},
                                      _pay(r["buyer"], r["seller"], amount),
                                      _pay(r["buyer"], r["buyer"], amount))))], t2)
        contract = when([case(deposit(r["buyer"], r["buyer"], amount), decision)], t1)
        scenarios = [
            _scenario("above_threshold", [_step("deposit", b, r["buyer"], amount),
                                          _step("choice", m, r["reporter"], name="price", value=80)],
                      {r["seller"]: {"": amount}}),
            _scenario("below_threshold", [_step("deposit", b, r["buyer"], amount),
                                          _step("choice", m, r["reporter"], name="price", value=10)],
                      {r["buyer"]: {"": amount}}),
        ]
    elif kind == "rental_deposit":
        fee = p["fee"]
        decision = when([
            case(choice_action("damage", r["landlord"], 0, 0), _pay(r["tenant"], r["tenant"], amount)),
            case(choice_action("damage", r["landlord"], 1, 1),
                 _pay(r["tenant"], r["landlord"], fee,
                      _pay(r["tenant"], r["tenant"], amount - fee))),
        ], t2)
        contract = when([case(deposit(r["tenant"], r["tenant"], amount), decision)], t1)
        scenarios = [
            _scenario("undamaged", [_step("deposit", b, r["tenant"], amount),
                                      _step("choice", m, r["landlord"], name="damage", value=0)],
                      {r["tenant"]: {"": amount}}),
            _scenario("damaged", [_step("deposit", b, r["tenant"], amount),
                                    _step("choice", m, r["landlord"], name="damage", value=1)],
                      {r["landlord"]: {"": fee}, r["tenant"]: {"": amount - fee}}),
        ]
    elif kind == "cancellation_fee":
        fee = p["fee"]
        decision = when([
            case(choice_action("cancel", r["buyer"], 0, 0),
                 _pay(r["buyer"], r["seller"], fee,
                      _pay(r["buyer"], r["buyer"], amount - fee))),
            case(choice_action("complete", r["buyer"], 1, 1), _pay(r["buyer"], r["seller"], amount)),
        ], t2)
        contract = when([case(deposit(r["buyer"], r["buyer"], amount), decision)], t1)
        scenarios = [
            _scenario("cancel", [_step("deposit", b, r["buyer"], amount),
                                 _step("choice", m, r["buyer"], name="cancel", value=0)],
                      {r["buyer"]: {"": amount - fee}, r["seller"]: {"": fee}}),
            _scenario("complete", [_step("deposit", b, r["buyer"], amount),
                                   _step("choice", m, r["buyer"], name="complete", value=1)],
                      {r["seller"]: {"": amount}}),
        ]
    else:
        raise ValueError(kind)
    return contract, scenarios
