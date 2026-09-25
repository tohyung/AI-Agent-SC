"""Deterministic enumeration of contract continuations for secondary review."""

from __future__ import annotations

from typing import Any

from .marlowe_sim import identity, token_id


def narrate(contract: Any) -> str:
    lines: list[str] = []

    def paths(node: Any, prefix: list[str]) -> None:
        if node == "close":
            lines.append("; ".join(prefix + ["Close: remaining balances return to account owners."]))
        elif "pay" in node:
            recipient = node["to"].get("party", node["to"].get("account"))
            action = (f"Pay {node['pay']} {token_id(node['token']) or 'ADA base units'} "
                      f"from {identity(node['from_account'])} to {identity(recipient)}")
            paths(node["then"], prefix + [action])
        elif "when" in node:
            for branch in node["when"]:
                action = branch["case"]
                if "deposits" in action:
                    label = (f"Before {node['timeout']}: {identity(action['party'])} sends "
                             f"{action['deposits']} {token_id(action['of_token']) or 'ADA base units'} "
                             f"to {identity(action['into_account'])}")
                elif "for_choice" in action:
                    choice = action["for_choice"]
                    label = (f"Before {node['timeout']}: {identity(choice['choice_owner'])} "
                             f"chooses {choice['choice_name']} in {action['choose_between']}")
                else:
                    label = f"Before {node['timeout']}: notification condition {action['notify_if']}"
                paths(branch["then"], prefix + [label])
            paths(node["timeout_continuation"], prefix + [f"At/after {node['timeout']}: timeout path"])
        elif "if" in node:
            paths(node["then"], prefix + [f"If {node['if']} is true"])
            paths(node["else"], prefix + [f"If {node['if']} is false"])
        elif "let" in node:
            paths(node["then"], prefix + [f"Let {node['let']}={node['be']}"])
        elif "assert" in node:
            paths(node["then"], prefix + [f"Assert {node['assert']}"])
        else:
            lines.append("; ".join(prefix + ["Unknown contract node"]))

    paths(contract, [])
    return "\n".join(f"{index + 1}. {line}" for index, line in enumerate(lines))
