"""E5: print each E3 contract next to the requirement history that produced it, for adjudication.

    python -m research.experiments.gate_adjudication --cases 1-56 > review.txt
Rubric: docs/E5-Adjudication-Rubric.md.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from typing import Any

from research.experiments.gate_eval import _candidates_in, e3_case_files, parse_range

VN = timezone(timedelta(hours=7))


def _when(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, VN).strftime("%Y-%m-%d %H:%M VN")


def _party(value: Any) -> str:
    if isinstance(value, dict):
        if "party" in value:
            return _party(value["party"])
        if "account" in value:
            return "acct:" + _party(value["account"])
        return str(value.get("role_token", value))
    return str(value)


def _token(value: dict[str, str]) -> str:
    return "ADA" if value == {"currency_symbol": "", "token_name": ""} else f"[{value.get('token_name')}]"


def _value(value: Any) -> str:
    if type(value) is int:
        return f"{value / 1_000_000:g}" if value >= 100_000 else str(value)
    return json.dumps(value, ensure_ascii=False)


def render(node: Any, depth: int = 0) -> list[str]:
    pad = "  " * depth
    if node == "close":
        return [pad + "Close"]
    if not isinstance(node, dict):
        return [pad + repr(node)]
    if "when" in node:
        lines = [pad + f"When (timeout {_when(node['timeout'])}):"]
        for branch in node["when"]:
            case = branch["case"]
            if "deposits" in case:
                head = (f"Deposit {_party(case['party'])} -> acct {_party(case['into_account'])} "
                        f"{_value(case['deposits'])} {_token(case['of_token'])}")
            elif "for_choice" in case:
                choice = case["for_choice"]
                bounds = ",".join(f"{b['from']}..{b['to']}" for b in case["choose_between"])
                head = f"Choice {choice['choice_name']} by {_party(choice['choice_owner'])} in [{bounds}]"
            else:
                head = f"Notify if {json.dumps(case.get('notify_if'))}"
            lines.append(pad + "  case " + head)
            lines += render(branch["then"], depth + 2)
        lines.append(pad + "  timeout ->")
        return lines + render(node["timeout_continuation"], depth + 2)
    if "pay" in node:
        return [pad + f"Pay {_value(node['pay'])} {_token(node['token'])} from acct "
                f"{_party(node['from_account'])} to {_party(node['to'])}"] + render(node["then"], depth)
    if "if" in node:
        return ([pad + f"If {json.dumps(node['if'], ensure_ascii=False)}"] + render(node["then"], depth + 1)
                + [pad + "Else"] + render(node["else"], depth + 1))
    if "let" in node:
        return [pad + f"Let {node['let']} = {json.dumps(node['be'], ensure_ascii=False)}"] + render(node["then"], depth)
    if "assert" in node:
        return [pad + f"Assert {json.dumps(node['assert'])}"] + render(node["then"], depth)
    return [pad + json.dumps(node, ensure_ascii=False)[:200]]


def history_of(files: dict[str, str], content_hash: str) -> list[str]:
    """Requirement history of the latest attempt that produced this contract."""
    found = None
    for name in sorted(files):
        if not name.startswith("attempt-") and "attempt" not in name:
            continue
        try:
            attempt = json.loads(files[name])
        except json.JSONDecodeError:
            continue
        artifacts: list[dict[str, Any]] = []
        _candidates_in(attempt, artifacts)
        if any(a.get("content_hash") == content_hash for a in artifacts):
            found = attempt
    if not found:
        return ["(no attempt found)"]
    lines = []
    for revision in found.get("requirement_history", []):
        for message in revision.get("messages", []):
            lines.append("  > " + " ".join(str(message).split()))
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cases", default="1-56")
    args = parser.parse_args()
    for index in parse_range(args.cases):
        files = e3_case_files(index)
        ordered: dict[str, Any] = {}
        for name in sorted(files):
            if "contract-candidate" not in files[name]:
                continue
            try:
                found: list[dict[str, Any]] = []
                _candidates_in(json.loads(files[name]), found)
            except json.JSONDecodeError:
                continue
            for artifact in found:
                if artifact["payload"].get("generation_mode"):
                    ordered.pop(artifact["content_hash"], None)
                    ordered[artifact["content_hash"]] = artifact["payload"]["contract"]
        for position, (digest, contract) in enumerate(ordered.items()):
            final = position == len(ordered) - 1
            print(f"=== case-{index:02d}-E3-{digest[:12]}{' (final)' if final else ''}")
            print("\n".join(history_of(files, digest)))
            print("\n".join(render(contract)))
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
