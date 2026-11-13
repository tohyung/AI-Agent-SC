"""Dataset v3: reference contracts and scenarios built from per-case specs.

A case author writes a structured `spec` (docs/archive/E6-Dataset-Design.md, section 6); nothing here
is written as Marlowe JSON by hand. Every builder returns (contract, scenarios). Each scenario's
expected payouts are computed from the spec, not by running the contract, so `validate.py` can
catch a builder that encodes the spec wrongly.

Scenario steps use absolute POSIX-ms times and the shape `dataset.marlowe_sim.run_scenario` takes.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from itertools import permutations
from typing import Any, Callable

ADA = {"currency_symbol": "", "token_name": ""}
DAY = 86_400_000
HOUR = 3_600_000


# ---------------------------------------------------------------- spec helpers

def ms(text: str) -> int:
    """'2027-03-20T23:59+07:00' -> POSIX milliseconds."""
    return int(datetime.fromisoformat(text).timestamp() * 1000)


def lovelace(ada: str | int | float) -> int:
    return int(Decimal(str(ada)) * 1_000_000)


def token(spec: dict[str, Any], token_id: str) -> dict[str, str]:
    if token_id == "ADA":
        return dict(ADA)
    item = spec["tokens"][token_id]
    return {"currency_symbol": item["policy"], "token_name": item["name"]}


def tok_key(spec: dict[str, Any], token_id: str) -> str:
    """Token key as `marlowe_sim` reports payouts (token_name only; '' for ADA)."""
    return "" if token_id == "ADA" else spec["tokens"][token_id]["name"]


def amt(spec: dict[str, Any], token_id: str, value: Any) -> int:
    return lovelace(value) if token_id == "ADA" else int(value)


# ---------------------------------------------------------------- contract nodes

def role(name: str) -> dict[str, str]:
    return {"role_token": name}


def when(cases: list[dict[str, Any]], timeout: int, otherwise: Any = "close") -> dict[str, Any]:
    return {"when": cases, "timeout": timeout, "timeout_continuation": otherwise}


def on_deposit(party: str, amount: Any, tok: dict[str, str], then: Any,
               account: str | None = None) -> dict[str, Any]:
    return {"case": {"party": role(party), "deposits": amount, "of_token": tok,
                     "into_account": role(account or party)}, "then": then}


def on_choice(name: str, owner: str, bounds: list[tuple[int, int]], then: Any) -> dict[str, Any]:
    return {"case": {"for_choice": {"choice_name": name, "choice_owner": role(owner)},
                     "choose_between": [{"from": a, "to": b} for a, b in bounds]}, "then": then}


def on_notify(observation: Any, then: Any) -> dict[str, Any]:
    return {"case": {"notify_if": observation}, "then": then}


def pay(source: str, to: str, amount: Any, tok: dict[str, str], then: Any = "close",
        to_account: bool = False) -> dict[str, Any]:
    payee = {"account": role(to)} if to_account else {"party": role(to)}
    return {"pay": amount, "from_account": role(source), "to": payee, "token": tok, "then": then}


def if_(observation: Any, then: Any, otherwise: Any) -> dict[str, Any]:
    return {"if": observation, "then": then, "else": otherwise}


def let(name: str, value: Any, then: Any) -> dict[str, Any]:
    return {"let": name, "be": value, "then": then}


def choice_value(name: str, owner: str) -> dict[str, Any]:
    return {"value_of_choice": {"choice_name": name, "choice_owner": role(owner)}}


def chain(*pays: Callable[[Any], Any], end: Any = "close") -> Any:
    node = end
    for make in reversed(pays):
        node = make(node)
    return node


# ---------------------------------------------------------------- scenarios

def dep(party: str, amount: int, tok_name: str, time: int) -> dict[str, Any]:
    return {"kind": "deposit", "party": party, "amount": amount, "token": tok_name, "time": time}


def cho(party: str, name: str, value: int, time: int) -> dict[str, Any]:
    return {"kind": "choice", "party": party, "name": name, "value": value, "time": time}


def ntf(time: int) -> dict[str, Any]:
    return {"kind": "notify", "time": time}


def adv(time: int) -> dict[str, Any]:
    return {"kind": "advance", "time": time}


def scenario(name: str, steps: list[dict[str, Any]], received: dict[str, dict[str, int]]) -> dict[str, Any]:
    clean = {p: {t: a for t, a in toks.items() if a} for p, toks in received.items()}
    return {"name": name, "steps": steps, "received": {p: t for p, t in clean.items() if t},
            "closed": True}


def add(total: dict[str, dict[str, int]], party: str, tok_name: str, amount: int) -> None:
    if amount:
        bucket = total.setdefault(party, {})
        bucket[tok_name] = bucket.get(tok_name, 0) + amount


def before(t: int) -> int:
    return t - HOUR


def after(t: int) -> int:
    return t + HOUR


# ---------------------------------------------------------------- families

def escrow(spec: dict[str, Any]) -> tuple[Any, list[dict[str, Any]]]:
    """Payer deposits; one decider picks an outcome; timeout outcome is stated.

    spec: payer, payee, decider, amount, token, deposit_by, decide_by, on_timeout ('payer'|'payee'),
    options: [{name, values:[[lo,hi]], to: 'payer'|'payee'}]  (one Choice case per option)
    """
    r, t = spec["roles"], spec.get("token", "ADA")
    a, tk, key = amt(spec, t, spec["amount"]), token(spec, t), tok_key(spec, t)
    t1, t2 = ms(spec["deposit_by"]), ms(spec["decide_by"])
    payer, decider = r["payer"], r["decider"]
    cases = [on_choice(o["name"], decider, [tuple(v) for v in o["values"]],
                       pay(payer, r[o["to"]], a, tk)) for o in spec["options"]]
    contract = when([on_deposit(payer, a, tk, when(cases, t2, pay(payer, r[spec["on_timeout"]], a, tk)))],
                    t1)
    sc = [scenario("no_deposit", [adv(after(t1))], {})]
    for o in spec["options"]:
        got: dict[str, dict[str, int]] = {}
        add(got, r[o["to"]], key, a)
        sc.append(scenario(f"choose_{o['name']}_{o['values'][0][0]}", [dep(payer, a, key, before(t1)),
                                                   cho(decider, o["name"], o["values"][0][0], before(t2))], got))
    got = {}
    add(got, r[spec["on_timeout"]], key, a)
    sc.append(scenario("no_decision", [dep(payer, a, key, before(t1)), adv(after(t2))], got))
    return contract, sc


def swap(spec: dict[str, Any]) -> tuple[Any, list[dict[str, Any]]]:
    """first deposits token_a by t1, second deposits token_b by t2, then both are exchanged."""
    r = spec["roles"]
    ta, tb = spec["token_a"], spec["token_b"]
    aa, ab = amt(spec, ta, spec["amount_a"]), amt(spec, tb, spec["amount_b"])
    ka, kb = tok_key(spec, ta), tok_key(spec, tb)
    t1, t2 = ms(spec["first_by"]), ms(spec["second_by"])
    f, s = r["first"], r["second"]
    contract = when([on_deposit(f, aa, token(spec, ta), when(
        [on_deposit(s, ab, token(spec, tb), pay(f, s, aa, token(spec, ta), pay(s, f, ab, token(spec, tb))))],
        t2, pay(f, f, aa, token(spec, ta))))], t1)
    both: dict[str, dict[str, int]] = {}
    add(both, s, ka, aa)
    add(both, f, kb, ab)
    refund: dict[str, dict[str, int]] = {}
    add(refund, f, ka, aa)
    return contract, [
        scenario("exchange", [dep(f, aa, ka, before(t1)), dep(s, ab, kb, before(t2))], both),
        scenario("second_absent", [dep(f, aa, ka, before(t1)), adv(after(t2))], refund),
        scenario("first_absent", [adv(after(t1))], {}),
    ]


def loan(spec: dict[str, Any]) -> tuple[Any, list[dict[str, Any]]]:
    """lender funds by t1 -> borrower; borrower repays by t2 -> lender; default just closes."""
    r = spec["roles"]
    p, q = lovelace(spec["principal"]), lovelace(spec["repay"])
    t1, t2 = ms(spec["fund_by"]), ms(spec["repay_by"])
    lender, borrower = r["lender"], r["borrower"]
    contract = when([on_deposit(lender, p, ADA, pay(lender, borrower, p, ADA, when(
        [on_deposit(borrower, q, ADA, pay(borrower, lender, q, ADA))], t2)))], t1)
    ok: dict[str, dict[str, int]] = {}
    add(ok, borrower, "", p)
    add(ok, lender, "", q)
    default: dict[str, dict[str, int]] = {}
    add(default, borrower, "", p)
    return contract, [
        scenario("repaid", [dep(lender, p, "", before(t1)), dep(borrower, q, "", before(t2))], ok),
        scenario("default", [dep(lender, p, "", before(t1)), adv(after(t2))], default),
        scenario("never_funded", [adv(after(t1))], {}),
    ]


def schedule(spec: dict[str, Any]) -> tuple[Any, list[dict[str, Any]]]:
    """Vesting: funder deposits the total; parts release at times, no one has to act.

    Optional 'cancel': {name, owner} lets that role stop before each release; the unreleased rest
    then goes back to the funder.
    """
    r = spec["roles"]
    funder, worker = r["funder"], r["worker"]
    parts = [(ms(p["at"]), lovelace(p["amount"])) for p in spec["parts"]]
    total = sum(a for _, a in parts)
    t0 = ms(spec["deposit_by"])
    cancel = spec.get("cancel")

    def tail(i: int) -> Any:
        if i == len(parts):
            return "close"
        at, a = parts[i]
        release = pay(funder, worker, a, ADA, tail(i + 1))
        cases = []
        if cancel:
            cases = [on_choice(cancel["name"], r[cancel["owner"]], [(1, 1)],
                               pay(funder, funder, sum(x for _, x in parts[i:]), ADA))]
        return when(cases, at, release)

    contract = when([on_deposit(funder, total, ADA, tail(0))], t0)
    full: dict[str, dict[str, int]] = {}
    add(full, worker, "", total)
    sc = [scenario("all_released", [dep(funder, total, "", before(t0)), adv(after(parts[-1][0]))], full),
          scenario("never_funded", [adv(after(t0))], {})]
    if cancel and len(parts) > 1:
        got: dict[str, dict[str, int]] = {}
        add(got, worker, "", parts[0][1])
        add(got, funder, "", total - parts[0][1])
        sc.append(scenario("cancel_after_first", [dep(funder, total, "", before(t0)),
                                                  adv(after(parts[0][0])),
                                                  cho(r[cancel["owner"]], cancel["name"], 1,
                                                      before(parts[1][0]))], got))
    return contract, sc


def milestones(spec: dict[str, Any]) -> tuple[Any, list[dict[str, Any]]]:
    """Client deposits the total; client approves each stage before its deadline.

    independent=False: a missed stage refunds everything still held and stops.
    independent=True: a missed stage refunds only that stage and the next stage can still be approved.
    """
    r = spec["roles"]
    client, worker = r["client"], r["worker"]
    stages = [(s["name"], ms(s["by"]), lovelace(s["amount"])) for s in spec["stages"]]
    total = sum(a for *_, a in stages)
    t0 = ms(spec["deposit_by"])
    independent = spec.get("independent", False)

    def stage(i: int) -> Any:
        if i == len(stages):
            return "close"
        name, by, a = stages[i]
        approved = pay(client, worker, a, ADA, stage(i + 1))
        if independent:
            missed = pay(client, client, a, ADA, stage(i + 1))
        else:
            missed = pay(client, client, sum(x for *_, x in stages[i:]), ADA)
        return when([on_choice(name, client, [(1, 1)], approved)], by, missed)

    contract = when([on_deposit(client, total, ADA, stage(0))], t0)
    all_ok: dict[str, dict[str, int]] = {}
    add(all_ok, worker, "", total)
    steps = [dep(client, total, "", before(t0))] + [cho(client, n, 1, before(by)) for n, by, _ in stages]
    first_missed: dict[str, dict[str, int]] = {}
    if independent:
        add(first_missed, client, "", stages[0][2])
        add(first_missed, worker, "", total - stages[0][2])
        miss_steps = [dep(client, total, "", before(t0)), adv(after(stages[0][1]))] + [
            cho(client, n, 1, before(by)) for n, by, _ in stages[1:]]
    else:
        add(first_missed, client, "", total)
        miss_steps = [dep(client, total, "", before(t0)), adv(after(stages[0][1]))]
    return contract, [scenario("all_approved", steps, all_ok),
                      scenario("first_stage_missed", miss_steps, first_missed),
                      scenario("never_funded", [adv(after(t0))], {})]


def pooled(spec: dict[str, Any]) -> tuple[Any, list[dict[str, Any]]]:
    """Contributors deposit in the stated order, each by its own deadline; when all are in, the
    beneficiary is paid. A missed deadline closes, refunding everyone who paid (via Close)."""
    r = spec["roles"]
    rows = [(r[c["role"]], lovelace(c["amount"]), ms(c["by"])) for c in spec["contributions"]]
    ben = r["beneficiary"]

    release_by = ms(spec["release_by"]) if spec.get("release_by") else None

    def step(i: int) -> Any:
        if i == len(rows):
            payout = chain(*[(lambda nxt, who=who, a=a: pay(who, ben, a, ADA, nxt)) for who, a, _ in rows])
            # Optional: anyone must send Notify before release_by, otherwise Close refunds everyone.
            return when([on_notify(True, payout)], release_by) if release_by else payout
        who, a, by = rows[i]
        return when([on_deposit(who, a, ADA, step(i + 1))], by)

    contract = step(0)
    full: dict[str, dict[str, int]] = {}
    add(full, ben, "", sum(a for _, a, _ in rows))
    all_in = [dep(w, a, "", before(by)) for w, a, by in rows]
    sc = [scenario("all_contribute", all_in + ([ntf(before(release_by))] if release_by else []), full),
          scenario("last_missing", all_in[:-1] + [adv(after(rows[-1][2]))], _refund_all(rows[:-1])),
          scenario("first_missing", [adv(after(rows[0][2]))], {})]
    if release_by:
        sc.append(scenario("nobody_releases", all_in + [adv(after(release_by))], _refund_all(rows)))
    return contract, sc


def _refund_all(rows: list[tuple[str, int, int]]) -> dict[str, dict[str, int]]:
    got: dict[str, dict[str, int]] = {}
    for who, a, _ in rows:
        add(got, who, "", a)
    return got


def threshold(spec: dict[str, Any]) -> tuple[Any, list[dict[str, Any]]]:
    """Payer deposits; a reporter (a person) picks a number; >= threshold pays payee else refund."""
    r = spec["roles"]
    payer, payee, rep = r["payer"], r["payee"], r["reporter"]
    a, t1, t2 = lovelace(spec["amount"]), ms(spec["deposit_by"]), ms(spec["report_by"])
    lo, hi, th, name = spec["low"], spec["high"], spec["threshold"], spec["choice"]
    decide = if_({"value": choice_value(name, rep), "ge_than": th},
                 pay(payer, payee, a, ADA), pay(payer, payer, a, ADA))
    contract = when([on_deposit(payer, a, ADA, when([on_choice(name, rep, [(lo, hi)], decide)], t2,
                                                     pay(payer, payer, a, ADA)))], t1)
    up: dict[str, dict[str, int]] = {}
    add(up, payee, "", a)
    down: dict[str, dict[str, int]] = {}
    add(down, payer, "", a)
    return contract, [
        scenario("at_threshold", [dep(payer, a, "", before(t1)), cho(rep, name, th, before(t2))], up),
        scenario("below", [dep(payer, a, "", before(t1)), cho(rep, name, th - 1, before(t2))], down),
        scenario("no_report", [dep(payer, a, "", before(t1)), adv(after(t2))], down),
    ]


def keep_part(spec: dict[str, Any]) -> tuple[Any, list[dict[str, Any]]]:
    """Rental deposit or cancellation fee: payer deposits; a chooser picks an option that splits the
    deposit between keeper and payer; timeout outcome stated.

    options: [{name, value, keeper_share}]; on_timeout: keeper share on timeout.
    """
    r = spec["roles"]
    payer, keeper, chooser = r["payer"], r["keeper"], r["chooser"]
    a, t1, t2 = lovelace(spec["amount"]), ms(spec["deposit_by"]), ms(spec["decide_by"])
    name = spec["choice"]

    def split(share: Any) -> Any:
        k = lovelace(share)
        if k == 0:
            return pay(payer, payer, a, ADA)
        if k == a:
            return pay(payer, keeper, a, ADA)
        return pay(payer, keeper, k, ADA, pay(payer, payer, a - k, ADA))

    opts = spec["options"]
    body: Any = split(opts[-1]["keeper_share"])
    for o in reversed(opts[:-1]):
        body = if_({"value": choice_value(name, chooser), "equal_to": o["value"]}, split(o["keeper_share"]), body)
    values = sorted(o["value"] for o in opts)
    contract = when([on_deposit(payer, a, ADA, when([on_choice(name, chooser, [(v, v) for v in values], body)],
                                                     t2, split(spec["on_timeout"])))], t1)
    sc = [scenario("no_deposit", [adv(after(t1))], {})]
    for o in opts:
        got: dict[str, dict[str, int]] = {}
        add(got, keeper, "", lovelace(o["keeper_share"]))
        add(got, payer, "", a - lovelace(o["keeper_share"]))
        sc.append(scenario(f"choose_{o['value']}", [dep(payer, a, "", before(t1)),
                                                   cho(chooser, name, o["value"], before(t2))], got))
    got = {}
    add(got, keeper, "", lovelace(spec["on_timeout"]))
    add(got, payer, "", a - lovelace(spec["on_timeout"]))
    sc.append(scenario("no_choice", [dep(payer, a, "", before(t1)), adv(after(t2))], got))
    return contract, sc


def installments(spec: dict[str, Any]) -> tuple[Any, list[dict[str, Any]]]:
    """Buyer pays each installment by its deadline; each goes to the seller at once; a miss stops."""
    r = spec["roles"]
    buyer, seller = r["buyer"], r["seller"]
    rows = [(ms(i["by"]), lovelace(i["amount"])) for i in spec["installments"]]

    def step(k: int) -> Any:
        if k == len(rows):
            return "close"
        by, a = rows[k]
        return when([on_deposit(buyer, a, ADA, pay(buyer, seller, a, ADA, step(k + 1)))], by)

    full: dict[str, dict[str, int]] = {}
    add(full, seller, "", sum(a for _, a in rows))
    part: dict[str, dict[str, int]] = {}
    add(part, seller, "", sum(a for _, a in rows[:2]))
    return step(0), [
        scenario("all_paid", [dep(buyer, a, "", before(by)) for by, a in rows], full),
        scenario("stops_after_two", [dep(buyer, a, "", before(by)) for by, a in rows[:2]]
                 + [adv(after(rows[2][0]))], part),
    ]


def k_of_n(spec: dict[str, Any]) -> tuple[Any, list[dict[str, Any]]]:
    """Funders deposit (any order); then any k of the approvers approve (any order) before the
    deadline to pay the recipient; otherwise every funder gets back their own deposit (Close)."""
    r = spec["roles"]
    funders = [(r[f["role"]], lovelace(f["amount"])) for f in spec["funders"]]
    approvers = [r[a] for a in spec["approvers"]]
    k, recipient = spec["k"], r["recipient"]
    t_fund, t_approve = ms(spec["fund_by"]), ms(spec["approve_by"])
    name = spec.get("choice", "approve")

    def release() -> Any:
        return chain(*[(lambda nxt, w=w, a=a: pay(w, recipient, a, ADA, nxt)) for w, a in funders])

    def approvals(done: tuple[str, ...]) -> Any:
        if len(done) == k:
            return release()
        rest = [a for a in approvers if a not in done]
        return when([on_choice(name, a, [(1, 1)], approvals(done + (a,))) for a in rest], t_approve)

    def deposits(done: tuple[str, ...]) -> Any:
        if len(done) == len(funders):
            return approvals(())
        rest = [(w, a) for w, a in funders if w not in done]
        return when([on_deposit(w, a, ADA, deposits(done + (w,))) for w, a in rest], t_fund)

    contract = deposits(())
    total = sum(a for _, a in funders)
    paid: dict[str, dict[str, int]] = {}
    add(paid, recipient, "", total)
    funding = [dep(w, a, "", before(t_fund) - i * HOUR) for i, (w, a) in enumerate(reversed(funders))]
    funding.sort(key=lambda s: s["time"])
    yes = [cho(a, name, 1, before(t_approve)) for a in approvers[-k:]]
    short = [cho(a, name, 1, before(t_approve)) for a in approvers[:k - 1]]
    return contract, [
        scenario("k_approve_reverse_order", funding + yes, paid),
        scenario("one_short", funding + short + [adv(after(t_approve))], _refund_all([(w, a, 0) for w, a in funders])),
        scenario("funding_incomplete", funding[:-1] + [adv(after(t_fund))],
                 _refund_all([(s["party"], s["amount"], 0) for s in funding[:-1]])),
    ]


def first_come(spec: dict[str, Any]) -> tuple[Any, list[dict[str, Any]]]:
    """Several buyers race; the first deposit of the price wins and is paid to the seller."""
    r = spec["roles"]
    seller, buyers = r["seller"], [r[b] for b in spec["buyers"]]
    a, t1 = lovelace(spec["price"]), ms(spec["offer_until"])
    contract = when([on_deposit(b, a, ADA, pay(b, seller, a, ADA)) for b in buyers], t1)
    got: dict[str, dict[str, int]] = {}
    add(got, seller, "", a)
    return contract, [
        scenario("last_listed_buyer_first", [dep(buyers[-1], a, "", before(t1))], got),
        scenario("no_buyer", [adv(after(t1))], {}),
    ]


def bond(spec: dict[str, Any]) -> tuple[Any, list[dict[str, Any]]]:
    """Investor deposits the price (paid to issuer at once); issuer then deposits each coupon, the
    last together with the face value, each paid to the investor; a missed payment just closes."""
    r = spec["roles"]
    inv, iss = r["investor"], r["issuer"]
    price, t0 = lovelace(spec["price"]), ms(spec["buy_by"])
    rows = [(ms(c["by"]), lovelace(c["amount"])) for c in spec["payments"]]

    def step(k: int) -> Any:
        if k == len(rows):
            return "close"
        by, a = rows[k]
        return when([on_deposit(iss, a, ADA, pay(iss, inv, a, ADA, step(k + 1)))], by)

    contract = when([on_deposit(inv, price, ADA, pay(inv, iss, price, ADA, step(0)))], t0)
    full: dict[str, dict[str, int]] = {}
    add(full, iss, "", price)
    add(full, inv, "", sum(a for _, a in rows))
    first: dict[str, dict[str, int]] = {}
    add(first, iss, "", price)
    add(first, inv, "", rows[0][1] if len(rows) > 1 else 0)
    steps_full = [dep(inv, price, "", before(t0))] + [dep(iss, a, "", before(by)) for by, a in rows]
    sc = [scenario("all_paid", steps_full, full), scenario("never_bought", [adv(after(t0))], {})]
    if len(rows) > 1:
        sc.append(scenario("issuer_stops_after_first", steps_full[:2] + [adv(after(rows[1][0]))], first))
    else:
        default: dict[str, dict[str, int]] = {}
        add(default, iss, "", price)
        sc.append(scenario("issuer_defaults", [dep(inv, price, "", before(t0)), adv(after(rows[0][0]))], default))
    return contract, sc


def split(spec: dict[str, Any]) -> tuple[Any, list[dict[str, Any]]]:
    """Payer deposits the total; then (optionally after anyone sends Notify, or after a release time)
    it is split among recipients by the stated amounts; Notify can be required."""
    r = spec["roles"]
    payer = r["payer"]
    shares = [(r[s["role"]], lovelace(s["amount"])) for s in spec["shares"]]
    total = sum(a for _, a in shares)
    t0 = ms(spec["deposit_by"])
    payout = chain(*[(lambda nxt, w=w, a=a: pay(payer, w, a, ADA, nxt)) for w, a in shares])
    trigger = spec.get("trigger", "deposit")
    if trigger == "notify":
        t1 = ms(spec["trigger_by"])
        body = when([on_notify(True, payout)], t1, pay(payer, payer, total, ADA))
    elif trigger == "time":
        body = when([], ms(spec["release_at"]), payout)
    else:
        body = payout
    contract = when([on_deposit(payer, total, ADA, body)], t0)
    got: dict[str, dict[str, int]] = {}
    for w, a in shares:
        add(got, w, "", a)
    steps = [dep(payer, total, "", before(t0))]
    if trigger == "notify":
        steps.append(ntf(before(ms(spec["trigger_by"]))))
    elif trigger == "time":
        steps.append(adv(after(ms(spec["release_at"]))))
    sc = [scenario("split", steps, got), scenario("never_funded", [adv(after(t0))], {})]
    if trigger == "notify":
        back: dict[str, dict[str, int]] = {}
        add(back, payer, "", total)
        sc.append(scenario("no_trigger", [dep(payer, total, "", before(t0)), adv(after(ms(spec["trigger_by"])))], back))
    return contract, sc


def collateral_loan(spec: dict[str, Any]) -> tuple[Any, list[dict[str, Any]]]:
    """Borrower posts collateral (a token) by t1; lender funds by t2 (paid to borrower); borrower
    repays by t3 -> repayment to lender and collateral back. On default the collateral is moved
    to the lender's account and the contract closes (Close pays it out to the lender)."""
    r = spec["roles"]
    bor, len_ = r["borrower"], r["lender"]
    ct = spec["collateral_token"]
    ca, ck = amt(spec, ct, spec["collateral"]), tok_key(spec, ct)
    p, q = lovelace(spec["principal"]), lovelace(spec["repay"])
    t1, t2, t3 = ms(spec["collateral_by"]), ms(spec["fund_by"]), ms(spec["repay_by"])
    ctk = token(spec, ct)
    repaid = pay(bor, len_, q, ADA, pay(bor, bor, ca, ctk))
    default = pay(bor, len_, ca, ctk, "close", to_account=True)
    funded = pay(len_, bor, p, ADA, when([on_deposit(bor, q, ADA, repaid)], t3, default))
    contract = when([on_deposit(bor, ca, ctk, when([on_deposit(len_, p, ADA, funded)], t2,
                                                    pay(bor, bor, ca, ctk)))], t1)
    ok: dict[str, dict[str, int]] = {}
    add(ok, bor, "", p)
    add(ok, bor, ck, ca)
    add(ok, len_, "", q)
    bad: dict[str, dict[str, int]] = {}
    add(bad, bor, "", p)
    add(bad, len_, ck, ca)
    nofund: dict[str, dict[str, int]] = {}
    add(nofund, bor, ck, ca)
    base = [dep(bor, ca, ck, before(t1)), dep(len_, p, "", before(t2))]
    return contract, [
        scenario("repaid", base + [dep(bor, q, "", before(t3))], ok),
        scenario("default", base + [adv(after(t3))], bad),
        scenario("lender_never_funds", [dep(bor, ca, ck, before(t1)), adv(after(t2))], nofund),
    ]


def deduction(spec: dict[str, Any]) -> tuple[Any, list[dict[str, Any]]]:
    """Payer deposits; inspector picks a deduction amount in lovelace (0..max); that amount goes to
    the keeper and the rest back to the payer; no choice refunds all."""
    r = spec["roles"]
    payer, keeper, insp = r["payer"], r["keeper"], r["inspector"]
    a, cap = lovelace(spec["amount"]), lovelace(spec["max_deduction"])
    t1, t2, name = ms(spec["deposit_by"]), ms(spec["decide_by"]), spec["choice"]
    rest = pay(payer, payer, {"value": a, "minus": {"use_value": "deduct"}}, ADA)
    # A zero payment is a Marlowe warning (non-positive pay), so pay the keeper only when > 0.
    body = let("deduct", choice_value(name, insp),
               if_({"value": {"use_value": "deduct"}, "gt": 0},
                   pay(payer, keeper, {"use_value": "deduct"}, ADA, rest), pay(payer, payer, a, ADA)))
    contract = when([on_deposit(payer, a, ADA, when([on_choice(name, insp, [(0, cap)], body)], t2,
                                                     pay(payer, payer, a, ADA)))], t1)
    mid = cap // 2
    some: dict[str, dict[str, int]] = {}
    add(some, keeper, "", mid)
    add(some, payer, "", a - mid)
    maxed: dict[str, dict[str, int]] = {}
    add(maxed, keeper, "", cap)
    add(maxed, payer, "", a - cap)
    none: dict[str, dict[str, int]] = {}
    add(none, payer, "", a)
    return contract, [
        scenario("half_of_cap", [dep(payer, a, "", before(t1)), cho(insp, name, mid, before(t2))], some),
        scenario("cap", [dep(payer, a, "", before(t1)), cho(insp, name, cap, before(t2))], maxed),
        scenario("zero", [dep(payer, a, "", before(t1)), cho(insp, name, 0, before(t2))], none),
        scenario("no_choice", [dep(payer, a, "", before(t1)), adv(after(t2))], none),
    ]


def matching(spec: dict[str, Any]) -> tuple[Any, list[dict[str, Any]]]:
    """Donors deposit in order; then the sponsor deposits min(total, cap); everything goes to the
    beneficiary. A missing donor or sponsor closes (Close refunds whoever paid)."""
    r = spec["roles"]
    donors = [(r[d["role"]], lovelace(d["amount"]), ms(d["by"])) for d in spec["donors"]]
    sponsor, ben = r["sponsor"], r["beneficiary"]
    cap, ts = lovelace(spec["cap"]), ms(spec["sponsor_by"])
    total = sum(a for _, a, _ in donors)
    matched = {"if": {"value": total, "gt": cap}, "then": cap, "else": total}

    def step(i: int) -> Any:
        if i == len(donors):
            payout = chain(*[(lambda nxt, w=w, a=a: pay(w, ben, a, ADA, nxt)) for w, a, _ in donors],
                           end=pay(sponsor, ben, {"use_value": "match"}, ADA))
            return let("match", matched, when([on_deposit(sponsor, {"use_value": "match"}, ADA, payout)], ts))
        who, a, by = donors[i]
        return when([on_deposit(who, a, ADA, step(i + 1))], by)

    m = min(total, cap)
    full: dict[str, dict[str, int]] = {}
    add(full, ben, "", total + m)
    steps = [dep(w, a, "", before(by)) for w, a, by in donors]
    return step(0), [
        scenario("matched", steps + [dep(sponsor, m, "", before(ts))], full),
        scenario("sponsor_absent", steps + [adv(after(ts))], _refund_all(donors)),
    ]


BUILDERS: dict[str, Callable[[dict[str, Any]], tuple[Any, list[dict[str, Any]]]]] = {
    "escrow": escrow, "escrow_arbiter": escrow, "swap": swap, "loan": loan, "vesting": schedule,
    "milestone": milestones, "crowdfunding": pooled, "third_party": threshold,
    "rental_deposit": keep_part, "cancellation_fee": keep_part, "installment": installments,
    "k_of_n": k_of_n, "first_come": first_come, "zero_coupon_bond": bond, "coupon_bond": bond,
    "split": split, "collateral_loan": collateral_loan, "deduction": deduction, "matching": matching,
}


def build(family: str, spec: dict[str, Any]) -> tuple[Any, list[dict[str, Any]]]:
    return BUILDERS[family](spec)


__all__ = ["BUILDERS", "build", "ms", "lovelace", "permutations"]
