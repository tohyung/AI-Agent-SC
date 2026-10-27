"""Materialize a source-grounded internal draft into the existing semantic core."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import re
from typing import Any

from research.stage2b.intent_spec import (
    BACKING_STATUSES, CLAIM_KINDS_V4, CORE_FIELDS, CORE_SCHEMA_VERSION_V4,
    DEADLINE_KINDS, DERIVED_SOURCE_STATUSES, PAYMENT_RELEASE_TIME_KINDS,
    TRANSITION_ACTOR_KINDS, TRANSITION_DEADLINE_KINDS, explicit_utc_instants,
    parse_native_asset_id, valid_derived_source, valid_supporting_evidence,
)


DRAFT_FIELDS = CORE_FIELDS - {"schema_version", "requirement_history"}
ADA_VALUE = re.compile(r"(?<![\w.])(?P<number>\d+(?:\.\d{1,6})?)\s*ADA\b", re.IGNORECASE)
VI_NOON_DATE = re.compile(
    r"(?<!\d)(?:12\s+giờ|12:00(?::00)?)\s+trưa\s+ngày\s+"
    r"(?P<day>\d{1,2})/"
    r"(?P<month>\d{1,2})/(?P<year>\d{4})(?!\d)", re.IGNORECASE)
UTC_OFFSET = re.compile(r"\bUTC(?P<sign>[+-])(?P<hour>\d{1,2})"
                        r"(?::(?P<minute>\d{2}))?\b", re.IGNORECASE)
DOT_NATIVE_ASSET_ID = re.compile(
    r"(?P<policy>[0-9a-fA-F]{56})\.(?P<token>[0-9a-fA-F]{2,64})\Z")


def _messages(history: list[dict[str, Any]]) -> dict[tuple[int, int], str]:
    return {(revision["version"], index): message
            for revision in history for index, message in enumerate(revision["messages"])}


def normalize_dot_native_asset_ids(core: dict[str, Any]) -> list[dict[str, Any]]:
    """Canonicalize a complete policy.token hex pair without inferring either part."""
    claims = core.get("claims")
    if not isinstance(claims, list):
        return []
    actions: list[dict[str, Any]] = []
    for claim in claims:
        if not isinstance(claim, dict) or claim.get("kind") != "asset":
            continue
        value = claim.get("value")
        if not isinstance(value, str):
            continue
        match = DOT_NATIVE_ASSET_ID.fullmatch(value)
        if match is None or len(match.group("token")) % 2:
            continue
        normalized = f"native:{match.group('policy').lower()}/{match.group('token').lower()}"
        claim["value"] = normalized
        actions.append({"kind": "native_asset_id_format", "claim_id": claim.get("claim_id"),
                        "source_value": value, "normalized_value": normalized})
    return actions


def derive_unambiguous_token_assets(core: dict[str, Any]) -> list[dict[str, Any]]:
    """Bind token quantities only to one source-backed native asset identity."""
    scopes = core.get("behavior_scopes")
    claims = core.get("claims")
    if not isinstance(scopes, list) or not isinstance(claims, list):
        return []
    scopes_by_id = {scope["scope_id"]: scope for scope in scopes
                    if isinstance(scope, dict) and isinstance(scope.get("scope_id"), str)}
    assets_by_scope: dict[str, list[dict[str, Any]]] = {}
    for claim in claims:
        if (isinstance(claim, dict) and claim.get("kind") == "asset"
                and isinstance(claim.get("scope_id"), str)):
            assets_by_scope.setdefault(claim["scope_id"], []).append(claim)

    all_active_native_values = {
        claim.get("value") for claim in claims if isinstance(claim, dict)
        and claim.get("kind") == "asset"
        and claim.get("status") in {"explicit", "derived", "assumed", "user_confirmed", "conflicted"}
        and isinstance(claim.get("value"), str)
        and (claim["value"].startswith("native:")
             or parse_native_asset_id(claim["value"]) is not None)
    }
    additions: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    derived_scopes: set[str] = set()
    for quantity in claims:
        if (not isinstance(quantity, dict)
                or quantity.get("kind") != "amount_token_units"
                or quantity.get("status") not in BACKING_STATUSES):
            continue
        scope_id = quantity.get("scope_id")
        if (not isinstance(scope_id, str) or scope_id not in scopes_by_id
                or scope_id in derived_scopes or assets_by_scope.get(scope_id)):
            continue

        ancestors: list[str] = []
        seen = {scope_id}
        current = scopes_by_id[scope_id]
        while isinstance(current.get("parent_scope_id"), str):
            parent_id = current["parent_scope_id"]
            if parent_id in seen or parent_id not in scopes_by_id:
                break
            seen.add(parent_id)
            ancestors.append(parent_id)
            current = scopes_by_id[parent_id]

        candidates = [claim for ancestor in ancestors
                      for claim in assets_by_scope.get(ancestor, [])
                      if claim.get("status") in DERIVED_SOURCE_STATUSES
                      and isinstance(claim.get("claim_id"), str)
                      and isinstance(claim.get("criticality"), str)
                      and isinstance(claim.get("evidence"), list)
                      and isinstance(claim.get("value"), str)
                      and parse_native_asset_id(claim["value"]) is not None]
        asset_values = {claim["value"] for claim in candidates}
        binding_basis = (
            "unique source-backed asset carried through parent_scope_id lineage"
            if candidates else None)
        if not candidates and len(all_active_native_values) == 1:
            only_asset = next(iter(all_active_native_values))
            candidates = [claim for claim in claims if isinstance(claim, dict)
                          and claim.get("kind") == "asset"
                          and claim.get("value") == only_asset
                          and claim.get("status") in DERIVED_SOURCE_STATUSES
                          and isinstance(claim.get("claim_id"), str)
                          and isinstance(claim.get("criticality"), str)
                          and isinstance(claim.get("evidence"), list)
                          and parse_native_asset_id(only_asset) is not None]
            asset_values = {claim["value"] for claim in candidates}
            if candidates:
                binding_basis = "unique source-backed native asset identity in semantic core"
        if len(asset_values) != 1:
            continue
        source = min(candidates, key=lambda claim: (
            ancestors.index(claim["scope_id"])
            if claim["scope_id"] in ancestors else len(ancestors),
            claim["claim_id"]))
        inherited = {
            "claim_id": f"derived-asset:{source['claim_id']}:{scope_id}",
            "kind": "asset", "value": source["value"],
            "criticality": source["criticality"], "status": "derived",
            "scope_id": scope_id, "evidence": deepcopy(source["evidence"]),
            "normalization_basis": binding_basis,
            "derived_from": source["claim_id"],
        }
        additions.append(inherited)
        derived_scopes.add(scope_id)
        actions.append({"kind": "unique_token_asset_binding",
                        "claim_id": inherited["claim_id"], "scope_id": scope_id,
                        "derived_from": source["claim_id"]})
    if additions:
        core["claims"].extend(additions)
    return actions


def retarget_unique_evidence_spans(
        core: dict[str, Any], messages: dict[tuple[int, int], str]) -> list[dict[str, Any]]:
    """Retarget exact citations or canonicalize a unique case-only source span."""
    actions: list[dict[str, Any]] = []
    claims = core.get("claims")
    scopes = core.get("behavior_scopes")
    lists = [claim.get("evidence") for claim in claims if isinstance(claim, dict)] \
        if isinstance(claims, list) else []
    for scope in scopes if isinstance(scopes, list) else []:
        if not isinstance(scope, dict):
            continue
        for field in ("choice_bounds", "choice_guard"):
            metadata = scope.get(field)
            if isinstance(metadata, dict):
                lists.append(metadata.get("source_evidence"))
    for evidence in lists:
        if not isinstance(evidence, list):
            continue
        for item in evidence:
            if not isinstance(item, dict) or not isinstance(item.get("span"), str):
                continue
            span = item["span"]
            if not span.strip():
                continue
            old = (item.get("requirement_version"), item.get("message_index"))
            current = messages.get(old, "") if all(type(value) is int for value in old) else ""
            if span in current:
                continue
            matches = [target for target, source in messages.items() if span in source]
            if len(matches) == 1:
                item["requirement_version"], item["message_index"] = matches[0]
                actions.append({"kind": "unique_evidence_retarget", "span": span,
                                "from": list(old), "to": list(matches[0])})
                continue
            if matches:
                continue
            folded_span = span.casefold()
            folded_matches = [
                (target, offset, source[offset:offset + len(span)])
                for target, source in messages.items()
                for offset in range(max(0, len(source) - len(span) + 1))
                if source[offset:offset + len(span)].casefold() == folded_span
            ]
            if len(folded_matches) != 1:
                continue
            target, _, exact_span = folded_matches[0]
            item["requirement_version"], item["message_index"] = target
            item["span"] = exact_span
            actions.append({"kind": "unique_casefold_evidence_canonicalization",
                            "span": exact_span, "from_span": span,
                            "from": list(old), "to": list(target)})
    return actions


def normalize_choice_metadata(core: dict[str, Any],
                              messages: dict[tuple[int, int], str]) -> list[dict[str, Any]]:
    """Keep source-backed Choice metadata in scopes, never as duplicate claim kinds."""
    scopes = core.get("behavior_scopes")
    claims = core.get("claims")
    if not isinstance(scopes, list) or not isinstance(claims, list):
        return []
    by_id = {item["scope_id"]: item for item in scopes if isinstance(item, dict)
             and isinstance(item.get("scope_id"), str)}
    actions: list[dict[str, Any]] = []
    for scope in scopes:
        if not isinstance(scope, dict):
            continue
        for field in ("choice_bounds", "choice_guard"):
            metadata = scope.get(field)
            if not isinstance(metadata, dict) or not isinstance(metadata.get("source_evidence"), list):
                continue
            for evidence in metadata["source_evidence"]:
                if (core.get("schema_version") == CORE_SCHEMA_VERSION_V4
                        and field == "choice_guard" and isinstance(evidence, dict)
                        and type(metadata.get("value")) is int
                        and isinstance(evidence.get("span"), str)):
                    key = (evidence.get("requirement_version"), evidence.get("message_index"))
                    source = messages.get(key) if all(type(item) is int for item in key) else None
                    span = evidence["span"]
                    if isinstance(source, str) and span not in source:
                        words = span.split()
                        value = str(metadata["value"])
                        for start in range(1, len(words) - 2):
                            suffix = " ".join(words[start:])
                            if (source.count(suffix) == 1
                                    and re.search(r"(?<!\d)" + re.escape(value) + r"(?!\d)",
                                                  suffix)):
                                evidence["span"] = suffix
                                actions.append({"kind": "choice_guard_exact_suffix",
                                                "scope_id": scope.get("scope_id")})
                                break
                if not isinstance(evidence, dict) or evidence.get("relation") != "explicit":
                    continue
                target = (evidence.get("requirement_version"), evidence.get("message_index"))
                source = messages.get(target, "") if all(type(value) is int for value in target) else ""
                span = evidence.get("span")
                if isinstance(span, str) and span.strip() and span in source:
                    evidence["relation"] = "supports"
                    actions.append({"kind": "choice_evidence_relation", "scope_id": scope.get("scope_id")})
    retained: list[Any] = []
    for claim in claims:
        if not isinstance(claim, dict):
            retained.append(claim)
            continue
        scope = by_id.get(claim.get("scope_id"))
        value = claim.get("value")
        kind = claim.get("kind")
        if kind in {"choice_bounds", "choice_guard"}:
            field = kind
        elif (core.get("schema_version") == CORE_SCHEMA_VERSION_V4
              and kind not in CLAIM_KINDS_V4 and isinstance(value, dict)
              and set(value) in ({"from", "to"}, {"operator", "value"})):
            field = "choice_bounds" if set(value) == {"from", "to"} else "choice_guard"
        else:
            retained.append(claim)
            continue
        metadata = scope.get(field) if isinstance(scope, dict) else None
        fields = ("from", "to") if field == "choice_bounds" else ("operator", "value")
        claim_id = claim.get("claim_id")
        if (not isinstance(metadata, dict) or not isinstance(value, dict)
                or set(value) != set(fields) or any(value[key] != metadata.get(key) for key in fields)
                or not isinstance(claim_id, str)
                or any(other is not claim and isinstance(other, dict)
                       and other.get("derived_from") == claim_id for other in claims)):
            retained.append(claim)
            continue
        actions.append({"kind": "redundant_choice_metadata_claim", "claim_id": claim_id})
    if len(retained) != len(claims):
        core["claims"] = retained
    return actions


def _grounded_literal(claim: dict[str, Any], messages: dict[tuple[int, int], str]) -> bool:
    value = claim.get("value")
    if not isinstance(value, str) or not value.strip():
        return False
    if not valid_supporting_evidence(claim, messages):
        return False
    return any(isinstance(item, dict) and item.get("relation") == "supports"
               and value in item.get("span", "")
               for item in claim.get("evidence", []))


def _matching_iso_deadline(claim: dict[str, Any],
                           messages: dict[tuple[int, int], str]) -> tuple[int, str] | None:
    value = claim.get("value")
    if not isinstance(value, str) or not valid_supporting_evidence(claim, messages):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.utcoffset() is None:
        return None
    instant = int(parsed.timestamp() * 1000)
    spans = [item["span"] for item in claim.get("evidence", [])
             if isinstance(item, dict) and item.get("relation") == "supports"
             and isinstance(item.get("span"), str)]
    cited = {candidate for span in spans
             for _, _, candidate in explicit_utc_instants(span)}
    if cited != {instant}:
        return None
    return instant, next(span for span in spans if explicit_utc_instants(span))


def _matching_named_deadline(claim: dict[str, Any],
                             messages: dict[tuple[int, int], str]) -> tuple[int, str] | None:
    if not valid_supporting_evidence(claim, messages):
        return None
    named = re.compile(
        r"(?<!\w)(?P<day>\d{1,2})\s+"
        r"(?P<month>January|February|March|April|May|June|July|August|"
        r"September|October|November|December)\s+(?P<year>\d{4})\s+"
        r"at\s+(?P<hour>\d{1,2}):(?P<minute>\d{2})"
        r"(?:\s+(?P<meridiem>noon|midnight|am|pm))?\b", re.IGNORECASE)
    offset_pattern = re.compile(r"\bUTC(?P<sign>[+-])(?P<hour>\d{1,2})"
                                r"(?::(?P<minute>\d{2}))?\b", re.IGNORECASE)
    months = {name: index for index, name in enumerate((
        "january", "february", "march", "april", "may", "june", "july",
        "august", "september", "october", "november", "december"), 1)}
    candidates: set[int] = set()
    cited_span = ""
    for item in claim["evidence"]:
        if item.get("relation") != "supports":
            continue
        span = item["span"]
        matches = list(named.finditer(span))
        if len(matches) != 1:
            continue
        message = messages[(item["requirement_version"], item["message_index"])]
        offsets = list(offset_pattern.finditer(span))
        if not offsets:
            if "same timezone" not in message.lower():
                continue
            offsets = list(offset_pattern.finditer(message))
        if len(offsets) != 1:
            continue
        match, offset = matches[0], offsets[0]
        hour = int(match.group("hour"))
        meridiem = (match.group("meridiem") or "").lower()
        if meridiem in {"noon", "midnight"}:
            if hour != 12 or int(match.group("minute")) != 0:
                continue
            hour = 12 if meridiem == "noon" else 0
        elif meridiem in {"am", "pm"}:
            if not 1 <= hour <= 12:
                continue
            hour = hour % 12 + (12 if meridiem == "pm" else 0)
        sign = 1 if offset.group("sign") == "+" else -1
        try:
            zone = timezone(sign * timedelta(hours=int(offset.group("hour")),
                                             minutes=int(offset.group("minute") or 0)))
            instant = datetime(int(match.group("year")),
                               months[match.group("month").lower()],
                               int(match.group("day")), hour, int(match.group("minute")),
                               tzinfo=zone)
        except ValueError:
            continue
        candidates.add(int(instant.timestamp() * 1000))
        cited_span = span
    return (next(iter(candidates)), cited_span) if len(candidates) == 1 else None


def _matching_vietnamese_noon_deadline(
        claim: dict[str, Any], messages: dict[tuple[int, int], str]
) -> tuple[int, str] | None:
    if not valid_supporting_evidence(claim, messages):
        return None
    candidates: set[int] = set()
    cited_span = ""
    for item in claim["evidence"]:
        if item.get("relation") != "supports":
            continue
        span = item["span"]
        dates = list(VI_NOON_DATE.finditer(span))
        if len(dates) != 1:
            continue
        offsets = list(UTC_OFFSET.finditer(span))
        if not offsets and "cùng múi giờ" in span.lower():
            offsets = list(UTC_OFFSET.finditer(
                messages[(item["requirement_version"], item["message_index"])]))
        if len(offsets) != 1:
            continue
        date, offset = dates[0], offsets[0]
        sign = 1 if offset.group("sign") == "+" else -1
        try:
            zone = timezone(sign * timedelta(hours=int(offset.group("hour")),
                                             minutes=int(offset.group("minute") or 0)))
            instant = datetime(int(date.group("year")), int(date.group("month")),
                               int(date.group("day")), 12, tzinfo=zone)
        except ValueError:
            continue
        candidates.add(int(instant.timestamp() * 1000))
        cited_span = span
    return (next(iter(candidates)), cited_span) if len(candidates) == 1 else None


def normalize_vietnamese_noon_deadlines(
        core: dict[str, Any], messages: dict[tuple[int, int], str]
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    claims = core.get("claims")
    if not isinstance(claims, list):
        return actions
    for claim in claims:
        if (not isinstance(claim, dict)
                or claim.get("kind") not in DEADLINE_KINDS | PAYMENT_RELEASE_TIME_KINDS
                or type(claim.get("value")) is int):
            continue
        matching = _matching_vietnamese_noon_deadline(claim, messages)
        if matching is None:
            continue
        normalized, source_literal = matching
        claim["value"] = normalized
        claim["status"] = "derived"
        claim["normalization_basis"] = (
            "source-grounded Vietnamese noon instant to POSIX milliseconds")
        actions.append({"claim_id": claim.get("claim_id"), "kind": claim.get("kind"),
                        "source_literal": source_literal, "normalized_value": normalized})
    return actions


def normalize_explicit_deadline_instants(
        core: dict[str, Any], messages: dict[tuple[int, int], str]
) -> list[dict[str, Any]]:
    """Resolve null deadlines only when cited text yields one explicit UTC instant."""
    claims = core.get("claims")
    if not isinstance(claims, list):
        return []
    actions: list[dict[str, Any]] = []
    for claim in claims:
        if (not isinstance(claim, dict)
                or claim.get("kind") not in DEADLINE_KINDS | PAYMENT_RELEASE_TIME_KINDS
                or claim.get("status") != "unresolved" or claim.get("value") is not None
                or not valid_supporting_evidence(claim, messages)):
            continue
        candidates: dict[int, str] = {}
        for item in claim["evidence"]:
            if item.get("relation") != "supports":
                continue
            for _, _, instant in explicit_utc_instants(item["span"]):
                candidates[instant] = item["span"]
        if len(candidates) != 1:
            continue
        normalized, source_literal = next(iter(candidates.items()))
        claim["value"] = normalized
        claim["status"] = "derived"
        claim["normalization_basis"] = (
            "source-grounded explicit timezone instant to POSIX milliseconds")
        actions.append({"claim_id": claim.get("claim_id"), "kind": claim.get("kind"),
                        "source_literal": source_literal, "normalized_value": normalized})
    return actions


def normalize_actor_scoped_deadlines(core: dict[str, Any],
                                     history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Resolve an uncited deadline only from its actor's uniquely grounded clause."""
    scopes = core.get("behavior_scopes")
    claims = core.get("claims")
    if not isinstance(scopes, list) or not isinstance(claims, list):
        return []
    scopes_by_id = {scope["scope_id"]: scope for scope in scopes
                    if isinstance(scope, dict) and isinstance(scope.get("scope_id"), str)}
    actors_by_scope: dict[str, set[str]] = {}
    actors: set[str] = set()
    for claim in claims:
        if (not isinstance(claim, dict) or claim.get("kind") not in {
                kind for values in TRANSITION_ACTOR_KINDS.values() for kind in values}
                or claim.get("status") not in DERIVED_SOURCE_STATUSES
                or not isinstance(claim.get("scope_id"), str)
                or not isinstance(claim.get("value"), str)
                or not claim["value"].strip()):
            continue
        actors_by_scope.setdefault(claim["scope_id"], set()).add(claim["value"].strip())
        actors.add(claim["value"].strip())

    actions: list[dict[str, Any]] = []
    for claim in claims:
        if (not isinstance(claim, dict) or claim.get("kind") not in DEADLINE_KINDS
                or claim.get("status") != "unresolved" or claim.get("value") is not None
                or claim.get("evidence") not in (None, [])):
            continue
        scope = scopes_by_id.get(claim.get("scope_id"))
        if not isinstance(scope, dict) or scope.get("scope_type") != "transition":
            continue
        transition_kind = scope.get("transition_kind")
        actor_kinds = TRANSITION_ACTOR_KINDS.get(transition_kind, set())
        if (claim.get("kind") not in TRANSITION_DEADLINE_KINDS.get(transition_kind, set())
                or not actor_kinds):
            continue
        scope_actors = actors_by_scope.get(scope["scope_id"], set())
        if len(scope_actors) != 1:
            continue
        actor = next(iter(scope_actors))
        candidates: list[tuple[int, int, int, str]] = []
        relative_days = re.compile(
            r"\b(?:đúng|exactly)\s+(?P<count>\d+|một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười)"
            r"\s+(?:ngày|days)\s+(?:sau|later)\b", re.IGNORECASE)
        day_words = {"một": 1, "hai": 2, "ba": 3, "bốn": 4, "năm": 5,
                     "sáu": 6, "bảy": 7, "tám": 8, "chín": 9, "mười": 10}
        calendar_date = re.compile(r"(?<!\d)(?P<day>\d{1,2})/(?P<month>\d{1,2})/"
                                   r"(?P<year>\d{4})(?!\d)")
        for revision in history:
            version = revision.get("version")
            if type(version) is not int or not isinstance(revision.get("messages"), list):
                continue
            for message_index, message in enumerate(revision["messages"]):
                if not isinstance(message, str):
                    continue
                instants = explicit_utc_instants(message)
                for start, end, instant in instants:
                    left = max((message.rfind(delimiter, 0, start) + 1
                                for delimiter in ";.!?\n"), default=0)
                    right_options = [position for delimiter in ";.!?\n"
                                     if (position := message.find(delimiter, end)) >= 0]
                    right = min(right_options) if right_options else len(message)
                    clause = message[left:right]
                    mentioned_actors = {
                        name for name in actors
                        if re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)",
                                     clause, re.IGNORECASE)
                    }
                    if mentioned_actors == {actor}:
                        candidates.append((version, message_index, instant,
                                           message[start:end]))
                for clause_match in re.finditer(r"[^;.!?\n]+", message):
                    clause = clause_match.group()
                    mentioned_actors = {
                        name for name in actors
                        if re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)",
                                     clause, re.IGNORECASE)
                    }
                    if mentioned_actors != {actor} or any(
                            clause_match.start() <= start and end <= clause_match.end()
                            for start, end, _ in instants):
                        continue
                    relative = list(relative_days.finditer(clause))
                    dates = list(calendar_date.finditer(clause))
                    if len(relative) != 1 or len(dates) != 1:
                        continue
                    before = [item for item in instants if item[1] <= clause_match.start()]
                    if len({item[2] for item in before}) != 1:
                        continue
                    base = max(before, key=lambda item: item[1])
                    base_left = max((message.rfind(delimiter, 0, base[0]) + 1
                                     for delimiter in ";.!?\n"), default=0)
                    base_clause = message[base_left:base[1]]
                    offsets = list(UTC_OFFSET.finditer(base_clause))
                    if len(offsets) != 1:
                        continue
                    offset = offsets[0]
                    sign = 1 if offset.group("sign") == "+" else -1
                    offset_hour = int(offset.group("hour"))
                    offset_minute = int(offset.group("minute") or 0)
                    if offset_hour > 23 or offset_minute > 59:
                        continue
                    zone = timezone(sign * timedelta(hours=offset_hour,
                                                     minutes=offset_minute))
                    count_text = relative[0].group("count").lower()
                    count = int(count_text) if count_text.isdigit() else day_words[count_text]
                    if not 1 <= count <= 36_500:
                        continue
                    try:
                        local_base = datetime.fromtimestamp(
                            base[2] / 1000, timezone.utc).astimezone(zone)
                        expected = local_base + timedelta(days=count)
                        cited_date = date(int(dates[0].group("year")),
                                          int(dates[0].group("month")),
                                          int(dates[0].group("day")))
                    except (OverflowError, ValueError):
                        continue
                    if expected.date() != cited_date:
                        continue
                    candidates.append((version, message_index,
                                       int(expected.timestamp() * 1000), clause.strip()))
        if not candidates:
            continue
        latest_version = max(item[0] for item in candidates)
        latest = [item for item in candidates if item[0] == latest_version]
        instants = {item[2] for item in latest}
        if len(instants) != 1:
            continue
        version, message_index, normalized, source_literal = min(
            latest, key=lambda item: item[1])
        claim["value"] = normalized
        claim["status"] = "derived"
        claim["evidence"] = [{"requirement_version": version,
                              "message_index": message_index,
                              "span": source_literal, "relation": "supports"}]
        claim["normalization_basis"] = (
            "unique actor-scoped source deadline to POSIX milliseconds")
        actions.append({"claim_id": claim.get("claim_id"), "kind": claim.get("kind"),
                        "source_literal": source_literal, "normalized_value": normalized,
                        "requirement_version": version})
    return actions


def normalize_grounded_numeric_amounts(
        core: dict[str, Any], messages: dict[tuple[int, int], str]
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    claims = core.get("claims")
    if not isinstance(claims, list):
        return actions
    for claim in claims:
        if (not isinstance(claim, dict) or claim.get("kind") != "amount_lovelace"
                or not isinstance(claim.get("value"), str)
                or not re.fullmatch(r"\d+", claim["value"])
                or not valid_supporting_evidence(claim, messages)):
            continue
        source_amounts: set[int] = set()
        ambiguous = False
        for item in claim["evidence"]:
            if item.get("relation") != "supports":
                continue
            matches = list(ADA_VALUE.finditer(item["span"]))
            if len(matches) > 1 and not re.search(
                    r"\b(?:gồm|bao gồm|including)\b", item["span"], re.IGNORECASE):
                ambiguous = True
                break
            if matches:
                amount = Decimal(matches[0].group("number")) * 1_000_000
                if amount == amount.to_integral_value():
                    source_amounts.add(int(amount))
        value = int(claim["value"])
        if ambiguous or source_amounts != {value}:
            continue
        claim["value"] = value
        claim["status"] = "derived"
        claim["normalization_basis"] = "source-grounded ADA-to-lovelace conversion"
        actions.append({"claim_id": claim.get("claim_id"), "kind": "numeric_amount_string",
                        "normalized_value": value})
    return actions


def drop_dangling_amount_derivations(
        core: dict[str, Any], messages: dict[tuple[int, int], str]
) -> list[dict[str, Any]]:
    claims = core.get("claims")
    if not isinstance(claims, list):
        return []
    by_id = {item["claim_id"]: item for item in claims if isinstance(item, dict)
             and isinstance(item.get("claim_id"), str)}
    removed: list[dict[str, Any]] = []
    for claim in claims:
        if (not isinstance(claim, dict) or claim.get("kind") != "amount_lovelace"
                or type(claim.get("value")) is not int
                or not isinstance(claim.get("derived_from"), str)
                or not valid_supporting_evidence(claim, messages)):
            continue
        if valid_derived_source(claim, by_id.get(claim["derived_from"])):
            continue
        supported = any(item.get("relation") == "supports"
                        and any(int(Decimal(match.group("number")) * 1_000_000)
                                == claim["value"]
                                for match in ADA_VALUE.finditer(item["span"]))
                        for item in claim["evidence"])
        if not supported:
            continue
        old = claim.pop("derived_from")
        removed.append({"claim_id": claim.get("claim_id"),
                        "kind": "dangling_amount_derivation", "removed_link": old})
    return removed


def prune_unverifiable_evidence(
        core: dict[str, Any], messages: dict[tuple[int, int], str]
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    claims = core.get("claims")
    if not isinstance(claims, list):
        return actions
    for claim in claims:
        if not isinstance(claim, dict) or not isinstance(claim.get("evidence"), list):
            continue
        evidence = claim["evidence"]
        retained = [item for item in evidence if isinstance(item, dict)
                    and type(item.get("requirement_version")) is int
                    and type(item.get("message_index")) is int
                    and isinstance(item.get("span"), str)
                    and item["span"] in messages.get((item.get("requirement_version"),
                                                      item.get("message_index")), "")]
        if len(retained) == len(evidence):
            continue
        proposed = dict(claim, evidence=retained)
        if not valid_supporting_evidence(proposed, messages):
            continue
        claim["evidence"] = retained
        actions.append({"claim_id": claim.get("claim_id"), "kind": "unverifiable_evidence",
                        "removed_count": len(evidence) - len(retained)})
    return actions


def _contains_value(value: Any, target: str) -> bool:
    if isinstance(value, dict):
        return any(_contains_value(item, target) for item in value.values())
    if isinstance(value, list):
        return any(_contains_value(item, target) for item in value)
    return value == target if isinstance(value, str) else False


def connect_skipped_terminal_outcomes(core: dict[str, Any]) -> list[str]:
    scopes = core.get("behavior_scopes")
    claims = core.get("claims")
    if (not isinstance(scopes, list) or not isinstance(claims, list)
            or not all(isinstance(item, dict) for item in scopes)):
        return []
    ids = [item.get("scope_id") for item in scopes]
    if any(not isinstance(item, str) for item in ids) or len(set(ids)) != len(ids):
        return []
    by_id = {item["scope_id"]: item for item in scopes}
    connected: list[str] = []
    for outcome in scopes:
        if outcome.get("scope_type") != "terminal_outcome":
            continue
        outcome_id = outcome["scope_id"]
        parent = by_id.get(outcome.get("parent_scope_id"))
        successor_id = outcome.get("continuation_scope_id")
        if (isinstance(parent, dict) and parent.get("scope_type") == "terminal_outcome"
                and parent.get("continuation_scope_id") is None):
            children = [item for item in scopes
                        if item.get("scope_type") == "terminal_outcome"
                        and item.get("parent_scope_id") == parent.get("scope_id")]
            if (len(children) == 1 and children[0].get("scope_id") == outcome_id
                    and any(claim.get("scope_id") == outcome_id for claim in claims
                            if isinstance(claim, dict))):
                parent["continuation_scope_id"] = outcome_id
                connected.append(outcome_id)
            continue
        if (not isinstance(parent, dict)
                or parent.get("scope_type") != "transition"
                or parent.get("transition_kind") != "payment"
                or not isinstance(successor_id, str)
                or successor_id not in by_id
                or parent.get("continuation_scope_id") != successor_id
                or not any(claim.get("scope_id") == outcome_id for claim in claims
                           if isinstance(claim, dict))):
            continue
        parent["continuation_scope_id"] = outcome_id
        connected.append(outcome_id)
    return connected


def prune_unreachable_duplicate_outcomes(core: dict[str, Any]) -> list[str]:
    scopes = core.get("behavior_scopes")
    if not isinstance(scopes, list) or not all(isinstance(item, dict) for item in scopes):
        return []
    ids = [item.get("scope_id") for item in scopes]
    if any(not isinstance(item, str) for item in ids) or len(set(ids)) != len(ids):
        return []
    by_id = {item["scope_id"]: item for item in scopes}
    removed: list[str] = []
    for scope in scopes:
        scope_id = scope["scope_id"]
        if scope.get("scope_type") != "terminal_outcome":
            continue
        parent = by_id.get(scope.get("parent_scope_id"))
        successor = scope.get("continuation_scope_id")
        if (parent is None or not isinstance(successor, str)
                or successor not in by_id
                or parent.get("continuation_scope_id") != successor):
            continue
        other_scopes = [item for item in scopes if item is not scope]
        other_fields = {key: value for key, value in core.items()
                        if key != "behavior_scopes"}
        if (_contains_value(other_scopes, scope_id)
                or _contains_value(other_fields, scope_id)):
            continue
        removed.append(scope_id)
    if removed:
        core["behavior_scopes"] = [item for item in scopes
                                   if item["scope_id"] not in removed]
    return removed


def drop_decision_to_own_branch_or_timeout(core: dict[str, Any]) -> list[str]:
    scopes = core.get("behavior_scopes")
    if not isinstance(scopes, list):
        return []
    by_id = {item["scope_id"]: item for item in scopes if isinstance(item, dict)
             and isinstance(item.get("scope_id"), str)}
    removed: list[str] = []
    for scope in scopes:
        if not isinstance(scope, dict) or scope.get("scope_type") != "transition":
            continue
        source_id = scope.get("scope_id")
        successor = scope.get("continuation_scope_id")
        if not isinstance(source_id, str) or not isinstance(successor, str):
            continue
        target = by_id.get(successor)
        own_branch = (isinstance(target, dict) and target.get("scope_type") == "branch"
                      and target.get("decision_id") == source_id)
        own_choice_timeout = (isinstance(target, dict)
                              and core.get("schema_version") == CORE_SCHEMA_VERSION_V4
                              and scope.get("transition_kind") == "choice"
                              and target.get("scope_type") == "timeout"
                              and target.get("decision_id") == source_id
                              and any(item.get("scope_type") == "branch"
                                      and item.get("decision_id") == source_id
                                      for item in by_id.values()))
        if own_branch or own_choice_timeout:
            scope.pop("continuation_scope_id")
            removed.append(source_id)
    return removed


def collapse_automatic_success_branches(core: dict[str, Any]) -> list[str]:
    scopes = core.get("behavior_scopes")
    if not isinstance(scopes, list):
        return []
    by_id = {item["scope_id"]: item for item in scopes if isinstance(item, dict)
             and isinstance(item.get("scope_id"), str)}
    removed: list[str] = []
    for branch in scopes:
        if (not isinstance(branch, dict) or branch.get("scope_type") != "branch"
                or not isinstance(branch.get("branch_id"), str)
                or branch.get("choice_guard") is not None):
            continue
        branch_id, parent_id = branch.get("scope_id"), branch.get("decision_id")
        successor_id = branch.get("continuation_scope_id")
        if not all(isinstance(value, str) for value in (branch_id, parent_id)):
            continue
        if not isinstance(successor_id, str):
            children = [item for item in scopes if isinstance(item, dict)
                        and item.get("scope_type") == "terminal_outcome"
                        and item.get("parent_scope_id") == branch_id]
            if len(children) == 1:
                successor_id = children[0].get("scope_id")
        if not isinstance(successor_id, str):
            continue
        parent, successor = by_id.get(parent_id), by_id.get(successor_id)
        if (not isinstance(parent, dict) or parent.get("scope_type") != "transition"
                or parent.get("transition_kind") not in {"deposit", "payment"}
                or parent.get("continuation_scope_id") not in {None, branch_id}
                or not isinstance(successor, dict)
                or successor.get("scope_type") not in {"transition", "terminal_outcome"}
                or any(item is not branch and isinstance(item, dict)
                       and item.get("scope_type") == "branch"
                       and item.get("decision_id") == parent_id for item in scopes)):
            continue
        other_scopes = [item for item in scopes if item is not branch
                        and item is not parent and item is not successor]
        other_fields = {key: value for key, value in core.items()
                        if key != "behavior_scopes"}
        if (_contains_value(other_scopes, branch_id)
                or _contains_value(other_fields, branch_id)
                or (successor.get("scope_type") == "terminal_outcome"
                    and successor.get("parent_scope_id") != branch_id)):
            continue
        parent["continuation_scope_id"] = successor_id
        if successor.get("parent_scope_id") == branch_id:
            successor["parent_scope_id"] = parent_id
        removed.append(branch_id)
    if removed:
        core["behavior_scopes"] = [item for item in scopes
                                   if not isinstance(item, dict)
                                   or item.get("scope_id") not in removed]
    return removed


def drop_resolved_time_format_questions(core: dict[str, Any]) -> int:
    claims = core.get("claims")
    questions = core.get("required_clarifications")
    if not isinstance(claims, list) or not isinstance(questions, list):
        return 0
    temporal = [claim for claim in claims if isinstance(claim, dict)
                and claim.get("kind") in DEADLINE_KINDS | PAYMENT_RELEASE_TIME_KINDS]
    if (not temporal or any(type(claim.get("value")) is not int
                            or claim.get("status") not in BACKING_STATUSES
                            or (claim.get("status") == "derived"
                                and not isinstance(claim.get("normalization_basis"), str))
                            for claim in temporal)):
        return 0
    temporal_ids = {claim.get("claim_id") for claim in temporal}
    resolved_temporal_ids = {
        claim.get("claim_id") for claim in temporal
        if isinstance(claim.get("claim_id"), str)
        and type(claim.get("value")) is int
        and claim.get("status") != "unresolved"
        and isinstance(claim.get("normalization_basis"), str)
    }
    def resolved_format_question(item: Any) -> bool:
        if not isinstance(item, dict) or not isinstance(item.get("question"), str):
            return False
        question = item["question"].strip().lower()
        if question.startswith(("what is the exact posix millisecond",
                                "please confirm the exact posix millisecond")):
            return True
        if ("posix" in question and ("millisecond" in question
                                     or "mili-giây" in question)):
            return True
        linked_ids = item.get("unresolved_claim_ids", item.get("linked_claim_ids"))
        linked_deadline = (isinstance(linked_ids, list) and bool(linked_ids)
                           and all(claim_id in resolved_temporal_ids
                                   for claim_id in linked_ids))
        asks_time = bool(re.search(
            r"\b(?:deadline|time|date|timezone|timestamp)\b|"
            r"hạn|giờ|ngày|múi\s*giờ|mốc\s*chót", question))
        return (linked_deadline and asks_time) or (
            item.get("claim_id") in temporal_ids and "chính xác" in question
            and ("giờ nào" in question or "lúc nào" in question))
    retained = [item for item in questions if not resolved_format_question(item)]
    removed = len(questions) - len(retained)
    if not removed:
        return 0
    core["required_clarifications"] = retained
    observations = core.get("unscored_observations")
    if (not retained and core.get("predicted_resolution") == "clarification_required"
            and isinstance(observations, list)
            and all(isinstance(item, dict)
                    and item.get("reason") == "irrelevant_context"
                    for item in observations)
            and not any(isinstance(claim, dict) and claim.get("status") == "unresolved"
                        for claim in claims)):
        core["predicted_resolution"] = "accepted_interpretation"
    return removed


def normalize_clarification_question_aliases(core: dict[str, Any]) -> int:
    questions = core.get("required_clarifications")
    if not isinstance(questions, list):
        return 0
    normalized = 0
    for item in questions:
        if (isinstance(item, dict) and "question" not in item
                and isinstance(item.get("question_text"), str)
                and item["question_text"].strip()):
            item["question"] = item.pop("question_text")
            normalized += 1
    return normalized


def drop_explicitly_absent_refund_recipient(
        core: dict[str, Any], messages: dict[tuple[int, int], str]) -> list[str]:
    claims = core.get("claims")
    if not isinstance(claims, list):
        return []
    removed: list[str] = []
    retained: list[Any] = []
    negated_refund = re.compile(r"\b(?:no|without|do not|don't)\b[^.]{0,80}\brefund\b",
                                re.IGNORECASE)
    for claim in claims:
        if (isinstance(claim, dict) and claim.get("kind") == "refund_recipient"
                and claim.get("status") == "explicit"
                and claim.get("value") == "none"
                and isinstance(claim.get("claim_id"), str)
                and valid_supporting_evidence(claim, messages)
                and any(isinstance(item, dict) and item.get("relation") == "supports"
                        and negated_refund.search(item["span"])
                        for item in claim["evidence"])):
            removed.append(claim["claim_id"])
        else:
            retained.append(claim)
    if removed:
        core["claims"] = retained
    return removed


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
        if not isinstance(claim, dict):
            continue
        grounded = _grounded_literal(claim, messages)
        value = claim.get("value")
        kind = claim.get("kind")
        normalized: int | None = None
        basis: str | None = None
        source_literal = value
        if kind == "amount_lovelace" and grounded:
            match = ADA_VALUE.fullmatch(value.strip())
            if match is not None:
                try:
                    amount = Decimal(match.group("number")) * 1_000_000
                except InvalidOperation:
                    amount = None
                if amount is not None and amount == amount.to_integral_value():
                    normalized = int(amount)
                    basis = "1 ADA = 1000000 lovelace; source-grounded decimal conversion"
        elif kind in DEADLINE_KINDS | PAYMENT_RELEASE_TIME_KINDS and grounded:
            instants = {instant for _, _, instant in explicit_utc_instants(value)}
            if len(instants) == 1:
                normalized = next(iter(instants))
                basis = "source-grounded calendar instant to POSIX milliseconds"
        elif kind in DEADLINE_KINDS | PAYMENT_RELEASE_TIME_KINDS:
            matching = _matching_iso_deadline(claim, messages)
            if matching is not None:
                normalized, source_literal = matching
                basis = "cited timezone instant equals model ISO instant; POSIX milliseconds"
        if kind in DEADLINE_KINDS | PAYMENT_RELEASE_TIME_KINDS and normalized is None:
            matching = _matching_named_deadline(claim, messages)
            if matching is not None:
                normalized, source_literal = matching
                basis = "source-grounded named calendar instant to POSIX milliseconds"
        if kind in DEADLINE_KINDS | PAYMENT_RELEASE_TIME_KINDS and normalized is None:
            matching = _matching_vietnamese_noon_deadline(claim, messages)
            if matching is not None:
                normalized, source_literal = matching
                basis = "source-grounded Vietnamese noon instant to POSIX milliseconds"
        if normalized is None:
            continue
        claim["value"] = normalized
        if claim.get("status") in {"explicit", "derived", "unresolved"}:
            claim["status"] = "derived"
        claim["normalization_basis"] = basis
        actions.append({"claim_id": claim.get("claim_id"), "kind": kind,
                        "source_literal": source_literal, "model_literal": value,
                        "normalized_value": normalized})
    for scope_id in prune_unreachable_duplicate_outcomes(core):
        actions.append({"scope_id": scope_id, "kind": "unreachable_duplicate_outcome",
                        "reason": "no references; parent already continues to same successor"})
    for claim_id in drop_explicitly_absent_refund_recipient(core, messages):
        actions.append({"claim_id": claim_id, "kind": "absent_refund_recipient",
                        "reason": "source explicitly negates refund; none is not a party"})
    removed_questions = drop_resolved_time_format_questions(core)
    if removed_questions:
        actions.append({"kind": "resolved_time_format_questions",
                        "removed_count": removed_questions})
    return core, actions
