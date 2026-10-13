"""Materialize a source-grounded internal draft into the existing semantic core."""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
import re
from typing import Any

from research.stage2b.intent_spec import (
    CORE_FIELDS, DEADLINE_KINDS, explicit_utc_instants, valid_supporting_evidence,
)


DRAFT_FIELDS = CORE_FIELDS - {"schema_version", "requirement_history"}
ADA_VALUE = re.compile(r"(?<![\w.])(?P<number>\d+(?:\.\d{1,6})?)\s*ADA\b", re.IGNORECASE)


def _messages(history: list[dict[str, Any]]) -> dict[tuple[int, int], str]:
    return {(revision["version"], index): message
            for revision in history for index, message in enumerate(revision["messages"])}


def _grounded_literal(claim: dict[str, Any], messages: dict[tuple[int, int], str]) -> bool:
    value = claim.get("value")
    if not isinstance(value, str) or not value.strip():
        return False
    if not valid_supporting_evidence(claim, messages):
        return False
    return any(isinstance(item, dict) and item.get("relation") == "supports"
               and value in item.get("span", "")
               for item in claim.get("evidence", []))


def materialize_core_draft(data: dict[str, Any], history: list[dict[str, Any]],
                           version: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Only compact drafts get normalized; legacy full cores remain model evidence."""
    if set(data) != DRAFT_FIELDS:
        return deepcopy(data), []
    core = {"schema_version": version, "requirement_history": deepcopy(history),
            **deepcopy(data)}
    messages = _messages(history)
    actions: list[dict[str, Any]] = []
    if not isinstance(core["claims"], list):
        return core, actions
    for claim in core["claims"]:
        if not isinstance(claim, dict) or not _grounded_literal(claim, messages):
            continue
        value = claim["value"]
        kind = claim.get("kind")
        normalized: int | None = None
        basis: str | None = None
        if kind == "amount_lovelace":
            match = ADA_VALUE.fullmatch(value.strip())
            if match is not None:
                try:
                    amount = Decimal(match.group("number")) * 1_000_000
                except InvalidOperation:
                    amount = None
                if amount is not None and amount == amount.to_integral_value():
                    normalized = int(amount)
                    basis = "1 ADA = 1000000 lovelace; source-grounded decimal conversion"
        elif kind in DEADLINE_KINDS:
            instants = {instant for _, _, instant in explicit_utc_instants(value)}
            if len(instants) == 1:
                normalized = next(iter(instants))
                basis = "source-grounded calendar instant to POSIX milliseconds"
        if normalized is None:
            continue
        claim["value"] = normalized
        if claim.get("status") in {"explicit", "derived"}:
            claim["status"] = "derived"
        claim["normalization_basis"] = basis
        actions.append({"claim_id": claim.get("claim_id"), "kind": kind,
                        "source_literal": value, "normalized_value": normalized})
    return core, actions
