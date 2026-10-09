"""Select user-declared transactions enabled by the current contract state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from research.stage3.scenario_binding import ScenarioBindingError, bind_choice_input


@dataclass(frozen=True)
class DeclaredActionDomain:
    """Match AST-enabled actions without deriving transactions from the AST."""

    domain_id: str
    declared: tuple[dict[str, Any], ...]
    finite: bool = True

    def transactions(self, state: dict[str, Any], contract: Any) -> list[dict[str, Any]]:
        if contract == "close":
            return []
        if isinstance(contract, dict) and "pay" in contract:
            return [tx for tx in self.declared if tx.get("inputs") == []]
        if not isinstance(contract, dict) or not isinstance(contract.get("when"), list):
            return []
        timeout = contract.get("timeout")
        timeout_actions = [tx for tx in self.declared
                           if tx.get("inputs") == []
                           and isinstance(tx.get("interval"), dict)
                           and type(timeout) is int
                           and type(tx["interval"].get("from")) is int
                           and type(tx["interval"].get("to")) is int
                           and timeout <= tx["interval"]["from"] <= tx["interval"]["to"]]
        if not contract["when"]:
            return timeout_actions
        enabled = [item["case"] for item in contract["when"]
                   if isinstance(item, dict) and isinstance(item.get("case"), dict)]
        matches = list(timeout_actions)
        for tx in self.declared:
            inputs = tx.get("inputs")
            if not isinstance(inputs, list) or len(inputs) != 1:
                continue
            item = inputs[0]
            if item.get("type") == "Choice" and "choice_id" not in item:
                try:
                    bound = bind_choice_input(item, enabled)
                except ScenarioBindingError:
                    continue
                tx = {**tx, "inputs": [bound]}
                item = bound
            if item.get("type") == "Choice" and any(
                    action.get("for_choice") == item.get("choice_id")
                    and any(bound.get("from") <= item.get("chosen") <= bound.get("to")
                            for bound in action.get("choose_between", []))
                    for action in enabled if "for_choice" in action):
                matches.append(tx)
            elif item.get("type") == "Deposit" and any(
                    action.get("party") == item.get("party")
                    and action.get("into_account") == item.get("account")
                    and action.get("of_token") == item.get("token")
                    and action.get("deposits") == item.get("amount")
                    for action in enabled if "deposits" in action):
                matches.append(tx)
            elif item.get("type") == "Notify" and any(
                    "notify_if" in action for action in enabled):
                matches.append(tx)
        return matches
