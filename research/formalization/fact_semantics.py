"""Denotational semantics of FactDraft v5, independent of the builder.

The meaning of a resolved draft is a Marlowe Core V1 contract, ⟦D⟧ = `denote(D)`.
The builder (`fact_builder`) computes a ShadowSemanticCore from the same draft
by a different route: it folds values to numbers and tracks balances itself.
The builder theorems in docs/archive/E4-Formalization-Comparison.md (Part III) are stated against ⟦D⟧, so tests
can check them two ways: offline with the small interpreter here, and against
the pinned Haskell reference semantics and SMT analyzer.

This module deliberately shares no code with `fact_builder`: quantities become
Marlowe `Value` terms (`DivValue`, `AvailableMoney`, ...) instead of numbers,
and instants are computed with `calendar.timegm` instead of `datetime`.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from typing import Any

ADA_TOKEN = {"currency_symbol": "", "token_name": ""}
GUARD_KEYS = {"eq": "equal_to", "ge": "ge_than", "gt": "gt", "le": "le_than", "lt": "lt"}


class NotDenotable(ValueError):
    """The draft leaves something open (unknown, dynamic, conflicting): no single ⟦D⟧."""


def _role(name: str) -> dict[str, str]:
    return {"role_token": name}


class _Denotation:
    def __init__(self, draft: dict[str, Any]):
        self.draft = draft
        self.items = {item["id"]: item for field in
                      ("parties", "assets", "quantities", "instants", "steps", "outcomes")
                      for item in draft.get(field) or []}
        # Side context creates no obligation, so it does not change the meaning.
        if any(not isinstance(item, dict) or item.get("kind") != "context"
               for item in (draft.get("notes") or {}).get("unsupported") or []):
            raise NotDenotable("unsupported notes")

    def name(self, party_id: Any) -> str:
        if not isinstance(party_id, str):
            raise NotDenotable("party list: the source names several parties")
        return self.items[party_id]["name"]

    def token(self, quantity_id: str) -> dict[str, str]:
        expr = self.items[quantity_id].get("expr") or {}
        for key in ("sum", "subtract", "times", "fraction"):
            if key in expr:
                spec = expr[key]
                ref = spec[0] if key == "sum" else spec.get("of", spec.get("from"))
                return self.token(ref)
        if "tokens" in expr:
            native = self.items[expr["asset"]].get("native")
            if not isinstance(native, str):
                raise NotDenotable("native token without a policy id")
            policy, hex_name = native.removeprefix("native:").split("/")
            return {"currency_symbol": policy, "token_name": bytes.fromhex(hex_name).decode()}
        return ADA_TOKEN

    # -- Value terms ------------------------------------------------------

    def value(self, quantity_id: str) -> Any:
        item = self.items[quantity_id]
        if "expr" not in item:
            raise NotDenotable(f"{quantity_id}: alternative readings")
        expr = item["expr"]
        if "ada" in expr:
            whole, _, frac = str(expr["ada"]).partition(".")
            return int(whole) * 1_000_000 + int((frac + "000000")[:6] or 0)
        if "lovelace" in expr or "tokens" in expr:
            return int(expr.get("lovelace", expr.get("tokens")))
        if "sum" in expr:
            terms = [self.value(ref) for ref in expr["sum"]]
            result = terms[0]
            for term in terms[1:]:
                result = {"add": result, "and": term}
            return result
        if "subtract" in expr:
            result = self.value(expr["subtract"]["from"])
            for ref in expr["subtract"]["minus"]:
                result = {"value": result, "minus": self.value(ref)}
            return result
        if "times" in expr:
            return {"multiply": self.value(expr["times"]["of"]), "times": expr["times"]["count"]}
        if "fraction" in expr:
            spec = expr["fraction"]
            return {"divide": {"multiply": self.value(spec["of"]), "times": spec["num"]},
                    "by": spec["den"]}
        raise NotDenotable(f"{quantity_id}: unknown or dynamic quantity")

    def amount(self, owner: dict[str, Any], account: str | None) -> tuple[Any, dict[str, str]]:
        if owner["amount"] == "remaining":
            unit = owner.get("asset")
            ada = unit in (None, "lovelace") or self.items[unit].get("ada") is True
            token = ADA_TOKEN if ada else self.token_of_asset(unit)
            return {"in_account": _role(self.name(account)), "amount_of_token": token}, token
        return self.value(owner["amount"]), self.token(owner["amount"])

    def token_of_asset(self, asset_id: str) -> dict[str, str]:
        native = self.items[asset_id].get("native")
        if not isinstance(native, str):
            raise NotDenotable("native token without a policy id")
        policy, hex_name = native.removeprefix("native:").split("/")
        return {"currency_symbol": policy, "token_name": bytes.fromhex(hex_name).decode()}

    # -- instants ---------------------------------------------------------

    def instant(self, instant_id: str) -> int:
        item = self.items[instant_id]
        expr = item.get("expr") or {}
        if "date" in expr:
            spec = expr["date"]
            if not isinstance(spec.get("tz"), str) or spec.get("h") is None:
                raise NotDenotable(f"{instant_id}: time of day or timezone not stated")
            sign = -1 if spec["tz"][0] == "-" else 1
            hours, minutes = int(spec["tz"][1:3]), int(spec["tz"][4:6])
            local = calendar.timegm((spec["y"], spec["m"], spec["d"], spec["h"], spec["min"], 0))
            return (local - sign * (hours * 3600 + minutes * 60)) * 1000
        if "offset" in expr:
            return self.instant(expr["offset"]["from"]) + expr["offset"]["days"] * 86_400_000
        raise NotDenotable(f"{instant_id}: unknown instant")

    # -- contracts --------------------------------------------------------

    def continuation(self, items: Any) -> Any:
        if items in (None, "end"):
            return "close"
        items = [items] if isinstance(items, str) else list(items)
        if not items:
            return "close"
        head, rest = items[0], items[1:]
        if head in (self.draft_ids("steps")):
            return self.step(head)
        outcome = self.items[head]
        account = outcome["from_account"]
        amount, token = self.amount(outcome, account)
        return {"pay": amount, "from_account": _role(self.name(account)),
                "to": {"party": _role(self.name(outcome["to"]))}, "token": token,
                "then": self.continuation(rest)}

    def draft_ids(self, field: str) -> set[str]:
        return {item["id"] for item in self.draft.get(field) or []}

    def step(self, step_id: str) -> Any:
        step = self.items[step_id]
        kind = step["kind"]
        if kind == "wait_until":
            return {"when": [], "timeout": self.instant(step["at"]),
                    "timeout_continuation": self.continuation(step.get("then"))}
        if kind == "deposit":
            action = {"party": _role(self.name(step["by"])), "deposits": self.value(step["amount"]),
                      "of_token": self.token(step["amount"]),
                      "into_account": _role(self.name(step["into"]))}
            body = self.continuation(step.get("then"))
        elif kind == "notify":
            action, body = {"notify_if": True}, self.continuation(step.get("then"))
        elif kind == "choice":
            choice_id = {"choice_name": step_id, "choice_owner": _role(self.name(step["by"]))}
            action = {"for_choice": choice_id,
                      "choose_between": [{"from": step["bounds"]["from"],
                                          "to": step["bounds"]["to"]}]}
            body: Any = "close"
            for branch in reversed(step.get("branches") or []):
                guard = branch["guard"]
                observation = {"value": {"value_of_choice": choice_id},
                               GUARD_KEYS[guard["op"]]: guard["value"]}
                body = {"if": observation, "then": self.continuation(branch.get("then")),
                        "else": body}
        else:
            raise NotDenotable(f"{step_id}: step kind {kind!r}")
        return {"when": [{"case": action, "then": body}], "timeout": self.instant(step["deadline"]),
                "timeout_continuation": self.continuation(step.get("on_timeout"))}

    def root(self) -> str:
        referenced = set()
        for step in self.draft.get("steps") or []:
            for field in ("then", "on_timeout"):
                value = step.get(field)
                referenced.update([value] if isinstance(value, str) else value or [])
            for branch in step.get("branches") or []:
                value = branch.get("then")
                referenced.update([value] if isinstance(value, str) else value or [])
        roots = [step["id"] for step in self.draft.get("steps") or [] if step["id"] not in referenced]
        if len(roots) != 1:
            raise NotDenotable(f"expected one first step, found {roots}")
        return roots[0]


def denote(draft: dict[str, Any]) -> Any:
    """⟦D⟧: the Marlowe Core V1 contract a resolved FactDraft v5 means."""
    try:
        meaning = _Denotation(draft)
        return meaning.step(meaning.root())
    except (KeyError, TypeError, IndexError) as exc:
        raise NotDenotable(f"ill-formed draft: {type(exc).__name__} {exc}") from None


# -- a small interpreter over ⟦D⟧ ---------------------------------------------

@dataclass(frozen=True)
class Move:
    """One decision at a `When`: take its case, choose a number, or let it time out."""

    kind: str  # "case" | "choose" | "timeout"
    chosen: int | None = None


@dataclass
class PathRun:
    moves: tuple[Move, ...]
    payments: list[tuple[str, str, int]]  # (from account, payee, amount); Close refunds last
    deadlines: list[int]
    transactions: list[dict[str, Any]]
    partial_pays: int = 0  # Pays that asked for more than the account held


def _token_key(token: dict[str, str]) -> str:
    return f"{token['currency_symbol']}/{token['token_name']}"


def _eval(value: Any, accounts: dict[tuple[str, str], int], choices: dict[str, int]) -> int:
    """`evalValue` for the constructors ⟦D⟧ uses; DivValue truncates toward zero (quot)."""
    if type(value) is int:
        return value
    if "add" in value:
        return _eval(value["add"], accounts, choices) + _eval(value["and"], accounts, choices)
    if "minus" in value:
        return _eval(value["value"], accounts, choices) - _eval(value["minus"], accounts, choices)
    if "multiply" in value:
        return _eval(value["multiply"], accounts, choices) * _eval(value["times"], accounts, choices)
    if "divide" in value:
        num, den = _eval(value["divide"], accounts, choices), _eval(value["by"], accounts, choices)
        quotient = abs(num) // abs(den)
        return quotient if (num >= 0) == (den > 0) else -quotient
    if "in_account" in value:
        key = (value["in_account"]["role_token"], _token_key(value["amount_of_token"]))
        return accounts.get(key, 0)
    raise ValueError(f"value outside ⟦D⟧: {value}")


def _observe(observation: dict[str, Any], choices: dict[str, int]) -> bool:
    chosen = choices[observation["value"]["value_of_choice"]["choice_name"]]
    for op, key in GUARD_KEYS.items():
        if key in observation:
            bound = observation[key]
            return {"eq": chosen == bound, "ge": chosen >= bound, "gt": chosen > bound,
                    "le": chosen <= bound, "lt": chosen < bound}[op]
    raise ValueError(f"observation outside ⟦D⟧: {observation}")


def paths(contract: Any) -> list[PathRun]:
    """Every path through ⟦D⟧, one choice value per guard, run by the local interpreter.

    Each path also carries the transactions that drive the pinned reference
    semantics along it. Payments follow Marlowe: a `Pay` pays at most the
    account balance, and `Close` refunds every account to its owner.
    """
    runs: list[PathRun] = []

    def go(node: Any, now: int, accounts: dict[tuple[str, str], int], choices: dict[str, int],
           run: PathRun) -> None:
        while isinstance(node, dict) and ("pay" in node or "if" in node):
            if "if" in node:
                node = node["then"] if _observe(node["if"], choices) else node["else"]
                continue
            key = (node["from_account"]["role_token"], _token_key(node["token"]))
            requested = _eval(node["pay"], accounts, choices)
            if requested > 0:  # a non-positive Pay is a warning and pays nothing
                amount = min(requested, accounts.get(key, 0))
                run.partial_pays += amount < requested
                accounts[key] = accounts.get(key, 0) - amount
                run.payments.append((key[0], node["to"]["party"]["role_token"], amount))
            node = node["then"]
        if node == "close":
            for (owner, _token), amount in sorted(accounts.items()):
                if amount > 0:
                    run.payments.append((owner, owner, amount))
            runs.append(run)
            return
        timeout = node["timeout"]
        run.deadlines.append(timeout)
        options: list[tuple[Move, Any, dict[str, Any] | None]] = []
        for case in node["when"]:
            action = case["case"]
            if "deposits" in action:
                amount = _eval(action["deposits"], accounts, choices)
                options.append((Move("case"), case["then"], {
                    "type": "Deposit", "party": action["party"], "account": action["into_account"],
                    "token": action["of_token"], "amount": amount}))
            elif "notify_if" in action:
                options.append((Move("case"), case["then"], {"type": "Notify"}))
            else:
                bound = action["choose_between"][0]
                candidates = _guard_samples(case["then"], bound)
                for chosen in candidates:
                    options.append((Move("choose", chosen), case["then"], {
                        "type": "Choice", "choice_id": action["for_choice"], "chosen": chosen}))
        for move, body, transaction_input in options:
            if now >= timeout:
                continue  # already timed out: the case can never be taken on this path
            branch_accounts, branch_choices = dict(accounts), dict(choices)
            if transaction_input["type"] == "Deposit":
                key = (transaction_input["account"]["role_token"],
                       _token_key(transaction_input["token"]))
                branch_accounts[key] = branch_accounts.get(key, 0) + transaction_input["amount"]
            elif transaction_input["type"] == "Choice":
                branch_choices[transaction_input["choice_id"]["choice_name"]] = move.chosen
            step = PathRun(run.moves + (move,), list(run.payments), list(run.deadlines),
                           run.transactions + [{"interval": {"from": now, "to": now},
                                                "inputs": [transaction_input]}],
                           run.partial_pays)
            go(body, now, branch_accounts, branch_choices, step)
        later = max(now, timeout)
        step = PathRun(run.moves + (Move("timeout"),), list(run.payments), list(run.deadlines),
                       run.transactions + [{"interval": {"from": later, "to": later},
                                            "inputs": []}], run.partial_pays)
        go(node["timeout_continuation"], later, dict(accounts), dict(choices), step)

    go(contract, 0, {}, {}, PathRun((), [], [], []))
    return runs


def _guard_samples(body: Any, bound: dict[str, int]) -> list[int]:
    """One in-bounds choice per guarded branch, plus one matching no guard if possible."""
    guards = []
    while isinstance(body, dict) and "if" in body:
        guards.append(body["if"])
        body = body["else"]
    values = range(bound["from"], bound["to"] + 1)
    samples: list[int] = []
    for guard in guards:
        hit = next((value for value in values
                    if _observe(guard, {guard["value"]["value_of_choice"]["choice_name"]: value})
                    and value not in samples), None)
        if hit is not None:
            samples.append(hit)
    miss = next((value for value in values if not any(
        _observe(guard, {guard["value"]["value_of_choice"]["choice_name"]: value})
        for guard in guards)), None)
    if miss is not None:
        samples.append(miss)
    return samples
