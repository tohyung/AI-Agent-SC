"""Conservative claim-to-AST checks for accepted intent."""

from __future__ import annotations

import re
from typing import Any


_PATH = re.compile(r"(?:root|\$)(?:\.[A-Za-z_][A-Za-z_0-9]*|\[[0-9]+\])*")
_PARTY_FIELDS = {
    "depositing_party": (".party",),
    "destination_account_owner": (".into_account",),
    "payment_source_account_owner": (".from_account",),
    "choice_owner": (".choice_owner",),
    "payment_recipient": (".to.party", ".to.account"),
    "refund_recipient": (".to.party", ".to.account"),
    "release_recipient": (".to.party", ".to.account"),
}
_DEADLINE_KINDS = {
    "choice_deadline_ms", "deposit_deadline_ms", "refund_deadline_ms", "timeout_ms",
}


def _lookup(contract: Any, path: str) -> Any:
    if not _PATH.fullmatch(path):
        raise ValueError("invalid AST path")
    current = contract
    prefix_length = 4 if path.startswith("root") else 1
    for part in re.findall(r"\.([A-Za-z_][A-Za-z_0-9]*)|\[([0-9]+)\]",
                           path[prefix_length:]):
        key = part[0] if part[0] else int(part[1])
        if isinstance(key, int):
            if not isinstance(current, list):
                raise ValueError("AST path does not address a list")
            current = current[key]
        else:
            if not isinstance(current, dict):
                raise ValueError("AST path does not address an object")
            current = current[key]
    return current


def _party(value: Any) -> Any:
    return value.get("role_token") if isinstance(value, dict) else value


def _claim_matches(claim: dict[str, Any], path: str, observed: Any) -> bool | None:
    kind, expected = claim["kind"], claim.get("value")
    if kind in _PARTY_FIELDS:
        suffixes = _PARTY_FIELDS[kind]
        if not any(path.endswith(suffix) or path.endswith(suffix + ".role_token")
                   for suffix in suffixes):
            return None
        return _party(observed) == expected
    if kind == "amount_lovelace":
        if not (path.endswith(".deposits") or path.endswith(".pay")):
            return None
        return type(observed) is int and observed == expected
    if kind in _DEADLINE_KINDS:
        if not path.endswith(".timeout"):
            return None
        return type(observed) is int and observed == expected
    if kind == "asset":
        if not (path.endswith(".of_token") or path.endswith(".token")):
            return None
        if expected == "ADA":
            return observed == {"currency_symbol": "", "token_name": ""}
        return None
    return None


def check_intent_alignment(spec: dict[str, Any], contract: Any,
                           evidence: list[dict[str, Any]]) -> dict[str, Any]:
    """Unknown is not success; path existence alone is never claim equivalence."""
    mapped: dict[tuple[str, str], list[str]] = {}
    for item in evidence:
        if not isinstance(item, dict):
            continue
        key = (item.get("source_kind"), item.get("source_id"))
        mapped.setdefault(key, []).append(item.get("ast_path", ""))
    results: list[dict[str, str]] = []
    for claim in spec.get("claims", []):
        if claim.get("status") == "superseded":
            continue
        claim_id = claim["claim_id"]
        paths = mapped.get(("claim", claim_id), [])
        if len(paths) != 1:
            state, reason, path = "INCONCLUSIVE", "missing_or_ambiguous_mapping", ""
        else:
            path = paths[0]
            try:
                observed = _lookup(contract, path)
            except (KeyError, IndexError, TypeError, ValueError):
                state, reason = "VIOLATED", "ast_path_missing"
            else:
                matched = _claim_matches(claim, path, observed)
                if matched is True:
                    state, reason = "SATISFIED", "exact_ast_field_match"
                elif matched is False:
                    state, reason = "VIOLATED", "ast_value_mismatch"
                else:
                    state, reason = "INCONCLUSIVE", "claim_mapping_not_proven"
        results.append({"source_kind": "claim", "source_id": claim_id,
                        "status": state, "reason": reason, "ast_path": path})
    for scope in spec.get("behavior_scopes", []):
        scope_id = scope["scope_id"]
        paths = mapped.get(("scope", scope_id), [])
        if len(paths) != 1:
            state, reason, path = "INCONCLUSIVE", "missing_or_ambiguous_mapping", ""
        else:
            path = paths[0]
            try:
                _lookup(contract, path)
            except (KeyError, IndexError, TypeError, ValueError):
                state, reason = "VIOLATED", "ast_path_missing"
            else:
                state, reason = "INCONCLUSIVE", "ast_path_exists_only"
        results.append({"source_kind": "scope", "source_id": scope_id,
                        "status": state, "reason": reason, "ast_path": path})
    statuses = {item["status"] for item in results}
    verdict = ("VIOLATED" if "VIOLATED" in statuses else
               "INCONCLUSIVE" if "INCONCLUSIVE" in statuses or not results else "SATISFIED")
    return {"verdict": verdict, "checks": results,
            "limitations": ["scope path existence is not behavioral equivalence",
                            "symbolic expressions and unsupported claim kinds require independent review"]}
