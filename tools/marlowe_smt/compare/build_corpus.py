#!/usr/bin/env python3
"""Build the deterministic Logic Graph versus SMT comparison corpus."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
from typing import Any


COMPARE = Path(__file__).resolve().parent
CORPUS = COMPARE / "corpus"
REPO = COMPARE.parents[2]
AUDIT_SOURCE = REPO / "marlowe_ai_agent" / "bench" / "audit"
VALID_SOURCE = REPO / "tools" / "marlowe_smt" / "bench" / "valid-corpus"
TIMEOUT = 1_893_456_000_000
ADA = {"currency_symbol": "", "token_name": ""}
ALICE = {"role_token": "Alice"}
BOB = {"role_token": "Bob"}
CHOICE = {"choice_name": "amount", "choice_owner": ALICE}
EMPTY_STATE = {"accounts": [], "choices": [], "boundValues": [], "minTime": 0}


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def deposit(amount: Any, then: Any = "close") -> dict[str, Any]:
    return {
        "when": [{
            "case": {"party": ALICE, "deposits": amount, "of_token": ADA, "into_account": ALICE},
            "then": then,
        }],
        "timeout": TIMEOUT,
        "timeout_continuation": "close",
    }


def choice(low: int, high: int, then: Any, choice_id: dict[str, Any] = CHOICE) -> dict[str, Any]:
    return {
        "when": [{
            "case": {"for_choice": choice_id, "choose_between": [{"from": low, "to": high}]},
            "then": then,
        }],
        "timeout": TIMEOUT,
        "timeout_continuation": "close",
    }


def pay(amount: Any) -> dict[str, Any]:
    return {"pay": amount, "from_account": ALICE, "to": {"party": BOB}, "token": ADA, "then": "close"}


def hand_written() -> list[dict[str, Any]]:
    choice_value = {"value_of_choice": CHOICE}
    choice_at_least_six = choice(6, 10, pay(choice_value))
    duplicate = {"notify_if": True}
    overlapping_choice = {"choice_name": "overlap", "choice_owner": ALICE}
    draft_contract = deposit(1)
    impossible_partial = choice(0, 10, {
        "if": {"value": choice_value, "gt": 10},
        "then": pay(1),
        "else": "close",
    })
    return [
        {"name": "01-nonpositive-deposit", "intentional_error": "nonpositive_deposit", "contract": deposit(0)},
        {"name": "02-nonpositive-pay", "intentional_error": "nonpositive_pay", "contract": pay(0)},
        {"name": "03-literal-partial-pay", "intentional_error": "literal_partial_pay", "contract": deposit(10, pay(20))},
        {"name": "04-symbolic-partial-pay", "intentional_error": "symbolic_partial_pay", "contract": deposit(5, choice_at_least_six)},
        {"name": "05-let-shadowing", "intentional_error": "let_shadowing", "contract": {"let": "x", "be": 1, "then": {"let": "x", "be": 2, "then": "close"}}},
        {"name": "06-symbolic-assertion", "intentional_error": "symbolic_assertion", "contract": choice(0, 1, {"assert": {"value": choice_value, "gt": 0}, "then": "close"})},
        {"name": "07-duplicate-action", "intentional_error": "duplicate_action", "contract": {"when": [{"case": duplicate, "then": "close"}, {"case": duplicate, "then": "close"}], "timeout": TIMEOUT, "timeout_continuation": "close"}},
        {"name": "08-overlapping-choice-bounds", "intentional_error": "overlapping_choice_bounds", "contract": {"when": [{"case": {"for_choice": overlapping_choice, "choose_between": [{"from": 0, "to": 5}]}, "then": "close"}, {"case": {"for_choice": overlapping_choice, "choose_between": [{"from": 5, "to": 10}]}, "then": "close"}], "timeout": TIMEOUT, "timeout_continuation": "close"}},
        {"name": "09-undefined-use-value", "intentional_error": "undefined_use_value", "contract": pay({"use_value": "missing"})},
        {"name": "10-draft-mismatch", "intentional_error": "draft_consistency", "contract": draft_contract, "draft": {"parties": [{"role": "seller", "name": "Bob"}], "amount": 2, "deposit_timeout": TIMEOUT + 1, "decision_timeout": TIMEOUT + 2}},
        {"name": "11-infeasible-if-partial-pay", "intentional_error": "infeasible_branch_false_positive", "contract": impossible_partial},
        {"name": "12-merkleized-case", "intentional_error": "merkleized_case", "contract": {"when": [{"case": {"notify_if": True}, "merkleized_then": "deadbeef"}], "timeout": TIMEOUT, "timeout_continuation": "close"}},
    ]


def write_case(directory: Path, name: str, contract: Any) -> dict[str, Any]:
    payload = canonical(contract)
    filename = f"{name}.json"
    (directory / filename).write_bytes(payload)
    return {"file": str((directory / filename).relative_to(CORPUS)).replace("\\", "/"), "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}


def main() -> None:
    if CORPUS.exists():
        shutil.rmtree(CORPUS)
    for source in ("audit", "valid-corpus", "hand-written"):
        (CORPUS / source).mkdir(parents=True)
    manifest: list[dict[str, Any]] = []

    for path in sorted(AUDIT_SOURCE.glob("*-full.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        contract = record.get("contract")
        if record.get("status") != "done" or contract in (None, {}):
            continue
        item = {"name": path.stem, "source": "audit", "intentional_error": ""}
        item.update(write_case(CORPUS / "audit", path.stem, contract))
        manifest.append(item)

    for path in sorted(VALID_SOURCE.glob("*.json")):
        contract = json.loads(path.read_text(encoding="utf-8"))
        item = {"name": path.stem, "source": "valid-corpus", "intentional_error": ""}
        item.update(write_case(CORPUS / "valid-corpus", path.stem, contract))
        manifest.append(item)

    for case in hand_written():
        item = {
            "name": case["name"], "source": "hand-written",
            "intentional_error": case["intentional_error"], "state": EMPTY_STATE,
        }
        if "draft" in case:
            item["draft"] = case["draft"]
        item.update(write_case(CORPUS / "hand-written", case["name"], case["contract"]))
        manifest.append(item)

    (CORPUS / "MANIFEST.json").write_bytes(canonical(manifest))
    total = sum(path.stat().st_size for path in CORPUS.rglob("*") if path.is_file())
    print(f"wrote {len(manifest)} cases ({total} bytes)")


if __name__ == "__main__":
    main()
