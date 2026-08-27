from __future__ import annotations

from typing import Any


def role(name: str) -> dict[str, str]:
    return {"role_token": name}


def ada() -> dict[str, str]:
    return {"currency_symbol": "", "token_name": ""}


def constant(value: int) -> dict[str, int]:
    return {"constant": value}


def close() -> dict[str, str]:
    return {"close": "close"}


def choice_id(name: str, party_name: str) -> dict[str, Any]:
    return {"choice_name": name, "choice_owner": role(party_name)}


def choice_action(name: str, party_name: str, low: int, high: int) -> dict[str, Any]:
    return {"choice": choice_id(name, party_name), "bounds": [{"from": low, "to": high}]}


def deposit(account: str, party: str, amount: int) -> dict[str, Any]:
    return {
        "deposits": constant(amount),
        "into_account": role(account),
        "of_token": ada(),
        "party": role(party),
    }


def pay(from_account: str, to_party: str, amount: int, then: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "pay": constant(amount),
        "from_account": role(from_account),
        "to": {"party": role(to_party)},
        "token": ada(),
        "then": then or close(),
    }


def case(action: dict[str, Any], then: dict[str, Any]) -> dict[str, Any]:
    return {"case": action, "then": then}


def when(cases: list[dict[str, Any]], timeout: int, timeout_continuation: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"when": cases, "timeout": timeout, "timeout_continuation": timeout_continuation or close()}


def escrow_contract(buyer: str, seller: str, amount: int, deposit_timeout: int, decision_timeout: int) -> dict[str, Any]:
    return when(
        [
            case(
                deposit(account=buyer, party=buyer, amount=amount),
                when(
                    [
                        case(choice_action("approve", buyer, 1, 1), pay(from_account=buyer, to_party=seller, amount=amount)),
                        case(choice_action("reject", buyer, 0, 0), pay(from_account=buyer, to_party=buyer, amount=amount)),
                    ],
                    timeout=decision_timeout,
                    timeout_continuation=pay(from_account=buyer, to_party=buyer, amount=amount),
                ),
            )
        ],
        timeout=deposit_timeout,
        timeout_continuation=close(),
    )


def walk_contract(contract: dict[str, Any], path: str = "root") -> list[tuple[str, dict[str, Any]]]:
    nodes = [(path, contract)]
    if "when" in contract:
        for index, item in enumerate(contract["when"]):
            nodes.extend(walk_contract(item["then"], f"{path}.case[{index}]"))
        nodes.extend(walk_contract(contract["timeout_continuation"], f"{path}.timeout"))
    elif "if" in contract:
        nodes.extend(walk_contract(contract["then"], f"{path}.then"))
        nodes.extend(walk_contract(contract["else"], f"{path}.else"))
    elif "then" in contract:
        nodes.extend(walk_contract(contract["then"], f"{path}.then"))
    return nodes
