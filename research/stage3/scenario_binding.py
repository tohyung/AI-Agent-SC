"""Bind declared Choice actions to unique AST ChoiceIds without changing outcomes."""

from __future__ import annotations

from typing import Any


class ScenarioBindingError(ValueError):
    pass


def _materialize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _materialize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_materialize(item) for item in value]
    return value


def _choice_actions(contract: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    def visit(node: Any) -> None:
        if not isinstance(node, dict):
            return
        for item in node.get("when", []):
            if not isinstance(item, dict):
                continue
            action = item.get("case")
            if isinstance(action, dict) and "for_choice" in action:
                found.append(action)
            visit(item.get("then"))
        for key in ("timeout_continuation", "then", "else"):
            visit(node.get(key))

    visit(contract)
    return found


def bind_choice_input(item: dict[str, Any],
                      actions: list[dict[str, Any]]) -> dict[str, Any]:
    if item.get("type") != "Choice" or "choice_id" in item:
        return _materialize(item)
    if set(item) != {"type", "choice_owner", "chosen"}:
        raise ScenarioBindingError("abstract Choice requires owner and chosen value")
    owner, chosen = item["choice_owner"], item["chosen"]
    if not isinstance(owner, dict) or type(chosen) is not int:
        raise ScenarioBindingError("abstract Choice has invalid owner or chosen value")
    matches = [action["for_choice"] for action in actions
               if isinstance(action.get("for_choice"), dict)
               and action["for_choice"].get("choice_owner") == owner
               and any(isinstance(bound, dict)
                       and type(bound.get("from")) is int
                       and type(bound.get("to")) is int
                       and bound["from"] <= chosen <= bound["to"]
                       for bound in action.get("choose_between", []))]
    unique = {str(choice.get("choice_name")): choice for choice in matches}
    if len(matches) != 1 or len(unique) != 1:
        raise ScenarioBindingError("abstract Choice does not bind uniquely")
    return {"type": "Choice", "choice_id": _materialize(matches[0]), "chosen": chosen}


def bind_choice_transactions(contract: Any, transactions: tuple[dict[str, Any], ...]
                             ) -> tuple[tuple[dict[str, Any], ...], list[dict[str, Any]]]:
    actions = _choice_actions(contract)
    bound: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    for tx_index, transaction in enumerate(transactions):
        copy = _materialize(transaction)
        for input_index, item in enumerate(copy.get("inputs", [])):
            if item.get("type") != "Choice" or "choice_id" in item:
                continue
            resolved = bind_choice_input(item, actions)
            copy["inputs"][input_index] = resolved
            evidence.append({"transaction_index": tx_index, "input_index": input_index,
                             "binding_kind": "unique_choice_owner_and_bound",
                             "choice_id": resolved["choice_id"]})
        bound.append(copy)
    return tuple(bound), evidence
