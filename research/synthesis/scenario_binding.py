"""Bind declared Choice actions to unique AST ChoiceIds without changing outcomes."""

from __future__ import annotations

import json
from typing import Any

from .reference import ReferenceExecutor, ReferenceRequest


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


def _enabled_choice_actions(contract: Any) -> list[dict[str, Any]]:
    if not isinstance(contract, dict) or not isinstance(contract.get("when"), list):
        return []
    return [item["case"] for item in contract["when"]
            if isinstance(item, dict) and isinstance(item.get("case"), dict)
            and "for_choice" in item["case"]]


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
    # A Choice input is identified only by its ChoiceId: several actions with the same id (one per
    # period, say) take the very same input, so they bind it alike.
    unique = {json.dumps(_materialize(choice), sort_keys=True, ensure_ascii=False): choice
              for choice in matches}
    if len(unique) != 1:
        raise ScenarioBindingError("abstract Choice does not bind uniquely")
    return {"type": "Choice", "choice_id": _materialize(matches[0]), "chosen": chosen}


def _role_tokens(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        if isinstance(value.get("role_token"), str):
            found.add(value["role_token"])
        for item in value.values():
            found |= _role_tokens(item)
    elif isinstance(value, list):
        for item in value:
            found |= _role_tokens(item)
    return found


def _rename(value: Any, mapping: dict[str, str]) -> Any:
    if isinstance(value, dict):
        if isinstance(value.get("role_token"), str) and set(value) == {"role_token"}:
            return {"role_token": mapping.get(value["role_token"], value["role_token"])}
        return {key: _rename(item, mapping) for key, item in value.items()}
    if isinstance(value, list):
        return [_rename(item, mapping) for item in value]
    return value


def party_name_mapping(contract: Any, expectation: Any) -> dict[str, str]:
    """Scenario role token -> the contract role token for the same party (E7 conventions, Q-TÊN 3).

    "CongTy" in a scenario and "Công ty" in a contract are one party. A name that matches no
    contract token is left as written (the comparison then reports it). Two contract tokens with
    one folded form, or two scenario names landing on one token, are ambiguous.
    """
    from research.formalization.party_names import fold_name

    by_fold: dict[str, set[str]] = {}
    for token in _role_tokens(contract):
        by_fold.setdefault(fold_name(token), set()).add(token)
    mapping: dict[str, str] = {}
    for name in sorted(_role_tokens(expectation)):
        candidates = by_fold.get(fold_name(name), set())
        if len(candidates) > 1:
            raise ScenarioBindingError(f"party {name!r} matches several contract roles")
        if candidates:
            mapping[name] = next(iter(candidates))
    targets = list(mapping.values())
    if len(targets) != len(set(targets)):
        raise ScenarioBindingError("two scenario parties name one contract role")
    return {name: token for name, token in mapping.items() if name != token}


def bind_party_names(contract: Any, transactions: tuple[dict[str, Any], ...],
                     payments: tuple[dict[str, Any], ...] | None
                     ) -> tuple[tuple[dict[str, Any], ...], tuple[dict[str, Any], ...] | None,
                                dict[str, str]]:
    """The scenario's transactions and expected payments written with the contract's role tokens."""
    mapping = party_name_mapping(contract, [list(transactions), list(payments or [])])
    if not mapping:
        return transactions, payments, {}
    return (tuple(_rename(item, mapping) for item in transactions),
            None if payments is None else tuple(_rename(item, mapping) for item in payments),
            mapping)


def bind_choice_transactions(contract: Any, transactions: tuple[dict[str, Any], ...],
                             *, reference: ReferenceExecutor | None = None,
                             initial_state: dict[str, Any] | None = None
                             ) -> tuple[tuple[dict[str, Any], ...], list[dict[str, Any]]]:
    if reference is not None and initial_state is None:
        raise ValueError("path-aware binding requires an initial state")
    actions = _choice_actions(contract)
    bound: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    for tx_index, transaction in enumerate(transactions):
        copy = _materialize(transaction)
        abstract = [index for index, item in enumerate(copy.get("inputs", []))
                    if item.get("type") == "Choice" and "choice_id" not in item]
        if reference is not None and abstract:
            if len(copy["inputs"]) != 1:
                raise ScenarioBindingError("path-aware Choice binding needs one input per transaction")
            current = contract
            if bound:
                try:
                    prefix = reference.execute(ReferenceRequest(
                        contract, initial_state, tuple(bound)))
                except (OSError, RuntimeError, ValueError) as exc:
                    raise ScenarioBindingError("reference prefix could not be evaluated") from exc
                if prefix.get("status") != "Success" or prefix.get("final_contract") is None:
                    raise ScenarioBindingError("reference prefix has no reliable continuation")
                current = prefix["final_contract"]
            actions = _enabled_choice_actions(current)
        for input_index, item in enumerate(copy.get("inputs", [])):
            if item.get("type") != "Choice" or "choice_id" in item:
                continue
            resolved = bind_choice_input(item, actions)
            copy["inputs"][input_index] = resolved
            evidence.append({"transaction_index": tx_index, "input_index": input_index,
                             "binding_kind": ("enabled_choice_owner_and_bound" if reference is not None
                                              else "unique_choice_owner_and_bound"),
                             "choice_id": resolved["choice_id"]})
        bound.append(copy)
    return tuple(bound), evidence
