from __future__ import annotations

from decimal import Decimal
from typing import Any


def role(name: str) -> dict[str, str]:
    return {"role_token": name}


def ada() -> dict[str, str]:
    return {"currency_symbol": "", "token_name": ""}


def constant(value: int) -> int:
    return value


def close() -> str:
    return "close"


def is_close(node: Any) -> bool:
    return node == "close" if isinstance(node, str) else False


def ada_to_lovelace(ada_amount: int | Decimal) -> int:
    value = Decimal(ada_amount) * 1_000_000
    if value != value.to_integral_value():
        raise ValueError("ADA amount must be representable in lovelace")
    return int(value)


def seconds_to_posix_ms(seconds: int | Decimal) -> int:
    value = Decimal(seconds) * 1_000
    if value != value.to_integral_value():
        raise ValueError("Seconds must be representable in milliseconds")
    return int(value)


def choice_id(name: str, party_name: str) -> dict[str, Any]:
    return {"choice_name": name, "choice_owner": role(party_name)}


def choice_action(name: str, party_name: str, low: int, high: int) -> dict[str, Any]:
    return {"for_choice": choice_id(name, party_name), "choose_between": [{"from": low, "to": high}]}


def deposit(account: str, party: str, amount: int) -> dict[str, Any]:
    return {"deposits": constant(amount), "into_account": role(account), "of_token": ada(), "party": role(party)}


def notify(observation: Any) -> dict[str, Any]:
    return {"notify_if": observation}


def if_(observation: Any, then: Any, else_: Any) -> dict[str, Any]:
    return {"if": observation, "then": then, "else": else_}


def let(name: str, value: Any, then: Any) -> dict[str, Any]:
    return {"let": name, "be": value, "then": then}


def assert_(observation: Any, then: Any) -> dict[str, Any]:
    return {"assert": observation, "then": then}


def pay(from_account: str, to_party: str, amount: int, then: Any = None) -> dict[str, Any]:
    return {
        "pay": constant(amount), "from_account": role(from_account), "to": {"party": role(to_party)},
        "token": ada(), "then": close() if then is None else then,
    }


def case(action: dict[str, Any], then: Any) -> dict[str, Any]:
    return {"case": action, "then": then}


def when(cases: list[dict[str, Any]], timeout: int, timeout_continuation: Any = None) -> dict[str, Any]:
    return {"when": cases, "timeout": timeout,
            "timeout_continuation": close() if timeout_continuation is None else timeout_continuation}


def escrow_contract(buyer: str, seller: str, amount: int, deposit_timeout: int, decision_timeout: int) -> dict[str, Any]:
    return when(
        [case(deposit(buyer, buyer, amount), when(
            [case(choice_action("approve", buyer, 1, 1), pay(buyer, seller, amount)),
             case(choice_action("reject", buyer, 0, 0), pay(buyer, buyer, amount))],
            decision_timeout, pay(buyer, buyer, amount),
        ))],
        deposit_timeout,
    )


def prompt_contract_examples() -> list[dict[str, Any]]:
    return [
        escrow_contract("Alice", "Bob", 250000000, 1893456000000, 1893542400000),
        when([case(notify(True), if_(
            {"value": 1, "ge_than": 0},
            let("count", 1, assert_(True, close())), close(),
        ))], 1893456000000),
    ]


def normalize_marlowe_ast(contract: Any) -> tuple[Any, list[str]]:
    notes: list[str] = []

    def convert(node: Any, path: str) -> Any:
        if isinstance(node, list):
            return [convert(item, f"{path}[{index}]") for index, item in enumerate(node)]
        if not isinstance(node, dict):
            return node
        if node == {"close": "close"}:
            notes.append(f"{path}: chuyển Close object thành chuỗi.")
            return "close"
        if set(node) == {"constant"} and type(node["constant"]) is int:
            notes.append(f"{path}: chuyển Constant object thành số nguyên.")
            return node["constant"]
        converted = {key: convert(value, f"{path}.{key}") for key, value in node.items()}
        if set(converted) == {"choice", "bounds"}:
            converted = {"for_choice": converted["choice"], "choose_between": converted["bounds"]}
            notes.append(f"{path}: đổi choice/bounds thành for_choice/choose_between.")
        return converted

    return convert(contract, "root"), notes


def walk_contract(contract: Any, path: str = "root") -> list[tuple[str, Any]]:
    nodes = [(path, contract)]
    if is_close(contract) or not isinstance(contract, dict):
        return nodes
    if "when" in contract and isinstance(contract["when"], list):
        for index, item in enumerate(contract["when"]):
            if isinstance(item, dict) and "then" in item:
                nodes.extend(walk_contract(item["then"], f"{path}.when[{index}].then"))
        nodes.extend(walk_contract(contract.get("timeout_continuation"), f"{path}.timeout_continuation"))
    elif "if" in contract:
        nodes.extend(walk_contract(contract.get("then"), f"{path}.then"))
        nodes.extend(walk_contract(contract.get("else"), f"{path}.else"))
    elif "then" in contract:
        nodes.extend(walk_contract(contract["then"], f"{path}.then"))
    return nodes
