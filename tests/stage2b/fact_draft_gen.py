"""Seeded generator of resolved FactDraft v5 drafts, and a walker over built cores.

A seed fixes the draft, so any failing property names a reproducible input.
Drafts stay inside the A2 phase-1 fragment: ADA amounts built from one or two
literals with fraction/subtract/sum/times, dated or offset deadlines, and
deposit/choice/notify/wait_until steps with shared outcomes (a DAG). Every
literal, name and date sits in its own fragment of a synthetic requirement,
and every declared item is used, so a builder rejection is a finding.
"""

from __future__ import annotations

import random
from typing import Any

from research.stage2b.fact_builder import FACT_DRAFT_VERSION
from research.stage2b.fact_semantics import Move

NAMES = ["Lan", "Tú", "Minh", "Alice", "Bob", "Hà"]
DENOMINATORS = [2, 4, 5, 10, 20]


class _Gen:
    def __init__(self, seed: int):
        self.rng = random.Random(seed)
        self.fragments: list[str] = []
        self.draft: dict[str, Any] = {"schema_version": FACT_DRAFT_VERSION, "parties": [],
                                      "asset": {}, "quantities": [], "instants": [],
                                      "steps": [], "outcomes": [], "notes": {}}
        self.counter = 0
        self.steps_left = self.rng.randint(1, 4)
        self.day_instants: dict[int, str] = {}
        self.quantities: dict[str, int] = {}  # id -> lovelace
        self.remaining_refund: str | None = None

    def ev(self, text: str) -> list[dict[str, Any]]:
        if text not in self.fragments:
            self.fragments.append(text)
        return [{"requirement_version": 1, "message_index": 0, "span": text,
                 "relation": "supports"}]

    def fresh(self, prefix: str) -> str:
        self.counter += 1
        return f"{prefix}{self.counter}"

    # -- items --------------------------------------------------------------

    def quantity(self, expr: dict[str, Any], phrase: str, value: int) -> str:
        for item in self.draft["quantities"]:
            if item["expr"] == expr:
                return item["id"]
        qid = self.fresh("q")
        self.draft["quantities"].append({"id": qid, "expr": expr, "evidence": self.ev(phrase)})
        self.quantities[qid] = value
        return qid

    def instant(self, days: int) -> str:
        if days in self.day_instants:
            return self.day_instants[days]
        iid = self.fresh("i")
        expr = {"offset": {"from": self.day_instants[0], "days": days}}
        self.draft["instants"].append({"id": iid, "expr": expr,
                                       "evidence": self.ev(f"hạn thứ {iid} sau {days} ngày")})
        self.day_instants[days] = iid
        return iid

    def outcome(self, kind: str, source: str, target: str, amount: str) -> str:
        oid = self.fresh("o")
        self.draft["outcomes"].append({
            "id": oid, "kind": kind, "from_account": source, "to": target, "amount": amount,
            "evidence": self.ev(f"khoản {oid} cho {self.party_name(target)}")})
        return oid

    def party_name(self, party_id: str) -> str:
        return next(item["name"] for item in self.draft["parties"] if item["id"] == party_id)

    # -- continuations ------------------------------------------------------

    def payout(self, balance: int, account: str, others: list[str]) -> tuple[list[str], int]:
        """Some outcomes that never overdraw `account`; returns them and the balance left."""
        items: list[str] = []
        if balance > 0 and self.rng.random() < 0.7:
            total_id, total = next(iter(self.quantities.items()))
            den = self.rng.choice(DENOMINATORS)
            num = self.rng.randint(1, den - 1)
            part = total * num // den
            options = []
            if part <= balance:
                options.append((self.quantity({"fraction": {"of": total_id, "num": num, "den": den}},
                                              f"phần {num}/{den} của tổng", part), part))
            if total <= balance:
                options.append((total_id, total))
            if part <= balance and total - part <= balance and options:
                frac_id = options[0][0]
                options.append((self.quantity({"subtract": {"from": total_id, "minus": [frac_id]}},
                                              f"phần còn lại sau {num}/{den}", total - part),
                                total - part))
            if options:
                amount_id, value = self.rng.choice(options)
                kind = self.rng.choice(["payment", "release"])
                items.append(self.outcome(kind, account, self.rng.choice(others), amount_id))
                balance -= value
        if balance > 0 and self.rng.random() < 0.6:
            if self.remaining_refund is None or self.rng.random() < 0.5:
                self.remaining_refund = self.outcome("refund", account, account, "remaining")
            items.append(self.remaining_refund)
            balance = 0
        return items, balance

    def continuation(self, balance: int, account: str, others: list[str], day: int) -> Any:
        items, balance = self.payout(balance, account, others)
        if self.steps_left > 0 and self.rng.random() < 0.75:
            items.append(self.step(balance, account, others, day))
        return items or "end"

    def step(self, balance: int, account: str, others: list[str], day: int) -> str:
        self.steps_left -= 1
        sid = self.fresh("s")
        day += self.rng.randint(1, 10)
        kind = self.rng.choice(["choice", "choice", "notify", "wait_until", "deposit"])
        parties = [item["id"] for item in self.draft["parties"]]
        step: dict[str, Any] = {"id": sid, "kind": kind,
                                "evidence": self.ev(f"bước {sid} của hợp đồng")}
        self.draft["steps"].append(step)
        if kind == "wait_until":
            step["at"] = self.instant(day)
            step["then"] = self.continuation(balance, account, others, day)
            return sid
        step["deadline"] = self.instant(day)
        if kind == "choice":
            step["by"] = self.rng.choice(parties)
            low = self.rng.randint(0, 1)
            high = low + self.rng.randint(0, 2)
            step["bounds"] = {"from": low, "to": high}
            values = self.rng.sample(range(low, high + 1), self.rng.randint(1, high - low + 1))
            step["branches"] = [{"guard": {"op": "eq", "value": value},
                                 "then": self.continuation(balance, account, others, day)}
                                for value in sorted(values)]
        elif kind == "deposit":
            literal = self.rng.randint(1, 50)
            amount = self.quantity({"ada": str(literal)}, f"thêm {literal} ADA",
                                   literal * 1_000_000)
            step.update({"by": account, "into": account, "amount": amount})
            step["then"] = self.continuation(balance + literal * 1_000_000, account, others, day)
        else:
            step["then"] = self.continuation(balance, account, others, day)
        step["on_timeout"] = self.continuation(balance, account, others, day)
        return sid

    def build(self) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        names = self.rng.sample(NAMES, self.rng.randint(2, 3))
        for index, name in enumerate(names):
            self.draft["parties"].append({"id": f"p{index}", "name": name,
                                          "evidence": self.ev(f"bên {name}")})
        literal = self.rng.choice([10, 20, 60, 100, 250, 1000])
        total_phrase = f"tổng {literal} ADA"
        self.draft["asset"] = {"ada": True, "evidence": self.ev(total_phrase)}
        total = self.quantity({"ada": str(literal)}, total_phrase, literal * 1_000_000)
        y, m, d = self.rng.randint(2027, 2030), self.rng.randint(1, 12), self.rng.randint(1, 28)
        h, tz = self.rng.choice([0, 9, 12, 17]), self.rng.choice([0, 7, -5])
        tz_text = "+00:00" if tz == 0 else f"{'+' if tz > 0 else '-'}{abs(tz):02d}:00"
        date_phrase = f"{h:02d}:00 ngày {d:02d}/{m:02d}/{y} (UTC{'+' if tz >= 0 else '-'}{abs(tz)})"
        self.draft["instants"].append({
            "id": "i0", "expr": {"date": {"y": y, "m": m, "d": d, "h": h, "min": 0,
                                          "tz": tz_text}},
            "evidence": self.ev(date_phrase)})
        self.day_instants[0] = "i0"
        account, others = "p0", ["p1"] + (["p2"] if len(names) > 2 else [])
        root = {"id": "s0", "kind": "deposit", "by": account, "into": account, "amount": total,
                "deadline": "i0", "on_timeout": "end", "evidence": self.ev("bước đầu nạp tiền")}
        self.draft["steps"].append(root)
        root["then"] = self.continuation(literal * 1_000_000, account, others, 0)
        self._drop_unused()
        message = "; ".join(self.fragments) + "."
        return self.draft, [{"version": 1, "messages": [message]}]

    def _drop_unused(self) -> None:
        used = set()
        for step in self.draft["steps"]:
            for key in ("by", "into", "amount", "deadline", "at"):
                if isinstance(step.get(key), str):
                    used.add(step[key])
        for outcome in self.draft["outcomes"]:
            used.update({outcome["from_account"], outcome["to"], outcome["amount"]})
        # Only items reachable from steps and outcomes count, transitively.
        grew = True
        while grew:
            before = len(used)
            for item in self.draft["quantities"]:
                if item["id"] not in used:
                    continue
                for spec in item["expr"].values():
                    if isinstance(spec, dict):
                        used.update(ref for ref in (spec.get("of"), spec.get("from")) if ref)
                        used.update(spec.get("minus") or [])
            for item in self.draft["instants"]:
                if item["id"] in used and "offset" in item["expr"]:
                    used.add(item["expr"]["offset"]["from"])
            grew = len(used) > before
        for field in ("parties", "quantities", "instants"):
            self.draft[field] = [item for item in self.draft[field] if item["id"] in used]


def random_draft(seed: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """A resolved draft and its requirement history; equal seeds give equal drafts."""
    return _Gen(seed).build()


# -- walking a built core along a path of ⟦D⟧ ---------------------------------

def core_path(core: dict[str, Any], moves: tuple[Move, ...]) -> tuple[
        list[tuple[str, str, int | None]], list[int | None]]:
    """Outcome claims (source owner, recipient, amount) and deadlines met along `moves`."""
    scopes = {scope["scope_id"]: scope for scope in core["behavior_scopes"]}
    claims: dict[str, dict[str, Any]] = {}
    for claim in core["claims"]:
        claims.setdefault(claim["scope_id"], {})[claim["kind"]] = claim["value"]
    referenced = {scope.get("continuation_scope_id") for scope in scopes.values()}
    current = next(scope_id for scope_id, scope in scopes.items()
                   if scope["scope_type"] == "transition" and scope_id not in referenced)
    payments: list[tuple[str, str, int | None]] = []
    deadlines: list[int | None] = []
    queue = list(moves)
    while current is not None:
        scope = scopes[current]
        if scope["scope_type"] == "terminal_outcome":
            facts = claims[current]
            recipient = next(facts[kind] for kind in
                             ("payment_recipient", "refund_recipient", "release_recipient")
                             if kind in facts)
            payments.append((facts["payment_source_account_owner"], recipient,
                             facts.get("amount_lovelace")))
            current = scope.get("continuation_scope_id")
            continue
        if scope["scope_type"] != "transition":
            current = scope.get("continuation_scope_id")
            continue
        key = current[2:]
        facts = claims.get(current, {})
        if scope["transition_kind"] == "payment":  # wait_until: time passes, no decision
            deadlines.append(facts.get("payment_release_time_ms"))
            queue.pop(0)
            current = scope.get("continuation_scope_id")
            continue
        deadline_kind = {"deposit": "deposit_deadline_ms", "choice": "choice_deadline_ms",
                         "notify": "timeout_ms"}[scope["transition_kind"]]
        deadlines.append(facts.get(deadline_kind))
        move = queue.pop(0)
        if move.kind == "timeout":
            current = scopes[f"to_{key}"].get("continuation_scope_id")
        elif move.kind == "case":
            current = scope.get("continuation_scope_id")
        else:
            branch = next((branch for branch in scopes.values()
                           if branch["scope_type"] == "branch"
                           and branch["decision_id"] == current
                           and branch["choice_guard"]["operator"] == "eq"
                           and branch["choice_guard"]["value"] == move.chosen), None)
            current = None if branch is None else branch.get("continuation_scope_id")
    return payments, deadlines
