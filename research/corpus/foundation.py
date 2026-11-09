#!/usr/bin/env python3
"""Validate and summarize draft Stage 2A research annotations."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parent
SPLITS = ("development", "validation")
RESOLUTIONS = {
    "accepted_interpretation", "clarification_required",
    "conflict_requires_resolution", "unsupported_for_current_study",
}
CLAIM_STATUSES = {
    "explicit", "derived", "assumed", "user_confirmed",
    "conflicted", "unresolved", "superseded",
}
ANNOTATION_STATUSES = {"draft", "reviewed", "adjudicated", "user_confirmed"}
SOURCE_BY_STATUS = {
    "draft": "candidate_research_annotation",
    "reviewed": "reviewed_research_annotation",
    "adjudicated": "expert_adjudicated",
    "user_confirmed": "user_confirmed",
}
SCOPE_TYPES = {"global", "transition", "branch", "timeout", "terminal_outcome"}
CLAIM_KINDS = {
    "amount_lovelace", "asset", "autonomous_execution", "choice_deadline_ms",
    "choice_owner", "deposit_deadline_ms", "depositing_party",
    "destination_account_owner", "payment_recipient", "payment_source_account_owner",
    "refund_deadline_ms", "refund_recipient", "release_recipient", "timeout_ms",
}
LOCAL_CLAIM_KINDS = {
    "amount_lovelace", "autonomous_execution", "choice_deadline_ms", "choice_owner",
    "deposit_deadline_ms", "depositing_party", "destination_account_owner",
    "payment_recipient", "payment_source_account_owner",
    "refund_deadline_ms", "refund_recipient", "release_recipient", "timeout_ms",
}
MUTATIONS = {
    "wrong_choice_owner", "wrong_depositing_party", "wrong_account_owner",
    "wrong_payment_recipient", "wrong_token", "wrong_unit_scaling",
    "wrong_amount", "swapped_deadline", "reversed_timeout_branch",
    "missing_refund", "double_payment", "missing_terminal_outcome",
    "unauthorized_choice",
}
REQUIRED = {
    "case_id", "split", "family", "group_id", "requirement_history",
    "expected_resolution", "behavior_scopes", "claims", "required_clarifications",
    "forbidden_assumptions", "behavior_expectations", "mutation", "annotation",
}


def load_corpus(directory: Path = ROOT / "corpus") -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for split in SPLITS:
        path = directory / f"{split}.jsonl"
        with path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
                if not isinstance(record, dict):
                    raise ValueError(f"{path}:{line_number}: record must be an object")
                record["_location"] = f"{path}:{line_number}"
                record["_file_split"] = split
                records.append(record)
    return records


def _require(condition: bool, location: str, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(f"{location}: {message}")


def effective_claims(record: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    mutation = record["mutation"]
    if mutation is None:
        return record["claims"]
    parent = by_id[mutation["parent_case_id"]]
    if parent["mutation"] is not None:
        raise ValueError("mutation parent must be canonical")
    return parent["claims"]


def effective_scopes(record: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    mutation = record["mutation"]
    if mutation is None:
        return record["behavior_scopes"]
    parent = by_id[mutation["parent_case_id"]]
    if parent["mutation"] is not None:
        raise ValueError("mutation parent must be canonical")
    return parent["behavior_scopes"]


def validate(records: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    by_id: dict[str, dict[str, Any]] = {}
    groups: dict[str, str] = {}
    requirements: dict[str, str] = {}

    for record in records:
        loc = record.get("_location", record.get("case_id", "record"))
        missing = REQUIRED - record.keys()
        if missing:
            errors.append(f"{loc}: missing fields {sorted(missing)}")
            continue
        case_id = record["case_id"]
        if not isinstance(case_id, str) or not case_id:
            errors.append(f"{loc}: invalid case_id")
            continue
        _require(case_id not in by_id, loc, f"duplicate case_id {case_id}", errors)
        by_id[case_id] = record
        split = record["split"]
        _require(split in SPLITS and split == record.get("_file_split", split),
                 loc, "invalid split or split/file mismatch", errors)
        for field in ("family", "group_id"):
            _require(isinstance(record[field], str) and bool(record[field].strip()),
                     loc, f"missing {field}", errors)
        group = record["group_id"]
        if isinstance(group, str):
            previous = groups.setdefault(group, split)
            _require(previous == split, loc, f"group {group} leaks across splits", errors)
        _require(isinstance(record["expected_resolution"], str) and
                 record["expected_resolution"] in RESOLUTIONS,
                 loc, "invalid expected_resolution", errors)

        history = record["requirement_history"]
        _require(isinstance(history, list) and bool(history), loc,
                 "requirement_history must be nonempty", errors)
        messages: dict[tuple[int, int], str] = {}
        if isinstance(history, list):
            for expected_version, version in enumerate(history, 1):
                if not isinstance(version, dict):
                    errors.append(f"{loc}: invalid requirement version")
                    continue
                _require(version.get("version") == expected_version, loc,
                         "requirement versions must be consecutive from 1", errors)
                entries = version.get("messages")
                _require(isinstance(entries, list) and bool(entries), loc,
                         "requirement messages must be nonempty", errors)
                if isinstance(entries, list):
                    for index, message in enumerate(entries):
                        _require(isinstance(message, str) and bool(message.strip()), loc,
                                 "requirement message must be nonempty text", errors)
                        if isinstance(message, str):
                            messages[(expected_version, index)] = message
        fingerprint = "\n".join(messages.values()).strip().casefold()
        if fingerprint:
            earlier = requirements.setdefault(fingerprint, split)
            _require(earlier == split, loc, "identical requirement leaks across splits", errors)

        mutation = record["mutation"]
        scopes = record["behavior_scopes"]
        _require(isinstance(scopes, list), loc, "behavior_scopes must be a list", errors)
        scope_ids: dict[str, dict[str, Any]] = {}
        branch_keys: set[tuple[str, str]] = set()
        timeout_ids: set[str] = set()
        if isinstance(scopes, list):
            for scope in scopes:
                if not isinstance(scope, dict):
                    errors.append(f"{loc}: invalid behavior scope")
                    continue
                scope_id = scope.get("scope_id")
                if not isinstance(scope_id, str) or not scope_id.strip():
                    errors.append(f"{loc}: scope_id is required")
                    continue
                _require(scope_id not in scope_ids, loc,
                         f"duplicate scope_id {scope_id}", errors)
                scope_ids[scope_id] = scope
                scope_type = scope.get("scope_type")
                _require(isinstance(scope_type, str) and scope_type in SCOPE_TYPES, loc,
                         f"scope {scope_id}: invalid scope_type", errors)
                if scope_type == "global":
                    _require(scope_id == "global", loc,
                             "global scope_id must be global", errors)
                if scope_type == "transition":
                    _require(isinstance(scope.get("transition_kind"), str) and
                             bool(scope["transition_kind"].strip()), loc,
                             f"scope {scope_id}: transition_kind is required", errors)
                if scope_type == "branch":
                    decision_id = scope.get("decision_id")
                    branch_id = scope.get("branch_id")
                    valid_branch = (isinstance(decision_id, str) and bool(decision_id.strip())
                                    and isinstance(branch_id, str) and bool(branch_id.strip()))
                    _require(valid_branch, loc,
                             f"scope {scope_id}: branch requires decision_id and branch_id", errors)
                    if valid_branch:
                        key = (decision_id, branch_id)
                        _require(key not in branch_keys, loc,
                                 f"duplicate branch identity {key}", errors)
                        branch_keys.add(key)
                if scope_type == "timeout":
                    timeout_id = scope.get("timeout_id")
                    valid_timeout = isinstance(timeout_id, str) and bool(timeout_id.strip())
                    _require(valid_timeout, loc,
                             f"scope {scope_id}: timeout_id is required", errors)
                    if valid_timeout:
                        _require(timeout_id not in timeout_ids, loc,
                                 f"duplicate timeout_id {timeout_id}", errors)
                        timeout_ids.add(timeout_id)
                if scope_type == "terminal_outcome":
                    _require(isinstance(scope.get("outcome_id"), str) and
                             bool(scope["outcome_id"].strip()), loc,
                             f"scope {scope_id}: outcome_id is required", errors)
            for scope_id, scope in scope_ids.items():
                decision_id = scope.get("decision_id")
                if scope.get("scope_type") == "branch" or decision_id is not None:
                    _require(isinstance(decision_id, str) and
                             decision_id in scope_ids and
                             scope_ids[decision_id].get("scope_type") == "transition", loc,
                             f"scope {scope_id}: decision_id does not reference a transition", errors)
                deadline_claim_id = scope.get("deadline_claim_id")
                if deadline_claim_id is not None:
                    deadline_claims = (record["claims"] if isinstance(record["claims"], list)
                                       else [])
                    _require(isinstance(deadline_claim_id, str) and
                             any(isinstance(c, dict) and c.get("claim_id") == deadline_claim_id
                                 and isinstance(c.get("kind"), str)
                                 and c["kind"].endswith("_ms") for c in deadline_claims), loc,
                             f"scope {scope_id}: deadline_claim_id does not reference a claim", errors)
        if isinstance(mutation, dict):
            _require(scopes == [], loc, "mutation must not define behavior_scopes", errors)
        else:
            _require(bool(scopes), loc, "canonical case requires behavior_scopes", errors)

        claims = record["claims"]
        _require(isinstance(claims, list), loc, "claims must be a list", errors)
        claim_ids: dict[str, dict[str, Any]] = {}
        current_by_scope: dict[tuple[str, str], set[str]] = {}
        if isinstance(claims, list):
            for claim in claims:
                if not isinstance(claim, dict):
                    errors.append(f"{loc}: invalid claim")
                    continue
                claim_id = claim.get("claim_id")
                if not isinstance(claim_id, str) or not claim_id:
                    errors.append(f"{loc}: claim_id is required")
                    continue
                _require(claim_id not in claim_ids, loc,
                         f"duplicate claim_id {claim_id}", errors)
                claim_ids[claim_id] = claim
                kind = claim.get("kind")
                _require(isinstance(kind, str) and kind in CLAIM_KINDS, loc,
                         f"claim {claim_id}: invalid/unknown claim kind {kind!r}", errors)
                scope_id = claim.get("scope_id")
                _require(isinstance(scope_id, str) and scope_id in scope_ids, loc,
                         f"claim {claim_id}: scope_id not found", errors)
                _require(not (scope_id == "global" and isinstance(kind, str) and
                              kind in LOCAL_CLAIM_KINDS), loc,
                         f"claim {claim_id}: branch/transition fact cannot be global", errors)
                status = claim.get("status")
                _require(isinstance(status, str) and status in CLAIM_STATUSES, loc,
                         f"claim {claim_id}: invalid status", errors)
                _require(isinstance(claim.get("criticality"), str) and
                         claim["criticality"] in {"financial", "nonfinancial"}, loc,
                         f"claim {claim_id}: invalid criticality", errors)
                if status == "derived" and claim.get("criticality") == "financial":
                    _require(isinstance(claim.get("normalization_basis"), str) and
                             bool(claim["normalization_basis"].strip()), loc,
                             f"claim {claim_id}: financial derivation lacks basis", errors)
                if record["expected_resolution"] == "accepted_interpretation":
                    _require(not (claim.get("criticality") == "financial" and
                                  isinstance(status, str) and
                                  status in {"unresolved", "conflicted", "assumed"}), loc,
                             f"accepted case has unresolved critical claim {claim_id}", errors)
                if (isinstance(status, str) and
                        status not in {"superseded", "conflicted", "unresolved"} and
                        isinstance(kind, str) and isinstance(scope_id, str)):
                    current_by_scope.setdefault((kind, scope_id), set()).add(json.dumps(
                        claim.get("value"), ensure_ascii=False, sort_keys=True))
                evidence = claim.get("evidence")
                _require(isinstance(evidence, list), loc,
                         f"claim {claim_id}: evidence must be a list", errors)
                if isinstance(status, str) and status in {"explicit", "user_confirmed", "superseded", "conflicted"}:
                    _require(bool(evidence), loc,
                             f"claim {claim_id}: status requires evidence", errors)
                if isinstance(evidence, list):
                    for item in evidence:
                        if not isinstance(item, dict):
                            errors.append(f"{loc}: claim {claim_id}: invalid evidence")
                            continue
                        version_number = item.get("requirement_version")
                        message_index = item.get("message_index")
                        key = (version_number, message_index)
                        source = (messages.get(key) if isinstance(version_number, int) and
                                  isinstance(message_index, int) else None)
                        _require(source is not None, loc,
                                 f"claim {claim_id}: evidence target does not exist", errors)
                        span = item.get("span")
                        _require(isinstance(span, str) and bool(span) and
                                 source is not None and span in source, loc,
                                 f"claim {claim_id}: evidence span not in message", errors)
                        _require(item.get("relation") in {"supports", "contradicts"}, loc,
                                 f"claim {claim_id}: invalid evidence relation", errors)
            for claim in claims:
                if isinstance(claim, dict) and claim.get("status") == "superseded":
                    successor_id = claim.get("superseded_by")
                    successor = claim_ids.get(successor_id) if isinstance(successor_id, str) else None
                    _require(successor is not None and successor.get("status") != "superseded"
                             and successor.get("kind") == claim.get("kind") and
                             successor.get("scope_id") == claim.get("scope_id"), loc,
                             f"superseded claim {claim.get('claim_id')} lacks current successor", errors)
                    if successor:
                        old_versions = [item.get("requirement_version") for item in claim.get("evidence", [])]
                        new_versions = [item.get("requirement_version") for item in successor.get("evidence", [])]
                        if old_versions and new_versions and all(isinstance(v, int) for v in old_versions + new_versions):
                            _require(max(old_versions) < max(new_versions), loc,
                                     "supersession must follow requirement chronology", errors)
            if record["expected_resolution"] != "conflict_requires_resolution":
                for (kind, scope_id), values in current_by_scope.items():
                    _require(len(values) <= 1, loc,
                             f"active claim values conflict for {kind} in {scope_id}", errors)

        clarifications = record["required_clarifications"]
        _require(isinstance(clarifications, list), loc,
                 "required_clarifications must be a list", errors)
        if record["expected_resolution"] == "clarification_required":
            _require(bool(clarifications), loc,
                     "clarification case has no required clarification", errors)
        if record["expected_resolution"] == "conflict_requires_resolution":
            _require(any(isinstance(c, dict) and c.get("status") == "conflicted"
                         for c in claims or []), loc,
                     "conflict case has no conflicted claim evidence", errors)
        if record["expected_resolution"] == "accepted_interpretation":
            _require(bool(claims) or isinstance(mutation, dict), loc,
                     "accepted canonical case has no claims", errors)
            _require(not clarifications, loc,
                     "accepted case still requests clarification", errors)
        _require(isinstance(record["forbidden_assumptions"], list), loc,
                 "forbidden_assumptions must be a list", errors)
        behavior = record["behavior_expectations"]
        _require(isinstance(behavior, dict) and
                 {"accepted_traces", "rejected_traces", "terminal_outcomes"} <= behavior.keys(),
                 loc, "behavior_expectations is incomplete", errors)
        _require(mutation is None or isinstance(mutation, dict), loc,
                 "mutation must be null or object", errors)
        if isinstance(mutation, dict):
            _require(claims == [], loc, "mutation must not define claims", errors)
            _require(isinstance(mutation.get("mutation_type"), str) and
                     mutation["mutation_type"] in MUTATIONS, loc,
                     "invalid mutation_type", errors)
            _require(isinstance(mutation.get("expected_semantic_difference"), str) and
                     bool(mutation.get("expected_semantic_difference")), loc,
                     "mutation lacks expected semantic difference", errors)
        annotation = record["annotation"]
        _require(isinstance(annotation, dict) and
                 isinstance(annotation.get("status"), str) and
                 annotation["status"] in ANNOTATION_STATUSES, loc,
                 "invalid annotation status", errors)
        if isinstance(annotation, dict):
            status = annotation.get("status")
            _require(isinstance(status, str) and
                     annotation.get("ground_truth_source") == SOURCE_BY_STATUS.get(status),
                     loc, "ground_truth_source does not match annotation status", errors)
            _require(isinstance(annotation.get("authored_by"), str) and
                     bool(annotation.get("authored_by")), loc,
                     "annotation author missing", errors)
            if annotation.get("status") != "draft":
                _require(bool(annotation.get("reviewed_by")), loc,
                         "non-draft annotation lacks reviewer", errors)
            else:
                _require(annotation.get("reviewed_by") is None and
                         annotation.get("adjudicated_by") is None, loc,
                         "draft annotation cannot claim human review", errors)
            if annotation.get("status") == "adjudicated":
                _require(bool(annotation.get("adjudicated_by")), loc,
                         "adjudicated annotation lacks adjudicator", errors)

    for record in records:
        mutation = record.get("mutation")
        if not isinstance(mutation, dict):
            continue
        loc = record.get("_location", record["case_id"])
        parent_id = mutation.get("parent_case_id")
        parent = by_id.get(parent_id) if isinstance(parent_id, str) else None
        _require(parent is not None, loc, "mutation parent missing", errors)
        if parent:
            _require(parent.get("mutation") is None, loc,
                     "mutation parent must be canonical", errors)
            _require(parent["split"] == record["split"] and
                     parent["group_id"] == record["group_id"], loc,
                     "mutation parent leaks across split/group", errors)
            _require(parent["expected_resolution"] == record["expected_resolution"], loc,
                     "mutation changes resolution instead of testing a behavioral deviation", errors)
            _require(parent["requirement_history"] == record["requirement_history"], loc,
                     "mutation requirement_history differs from parent", errors)
            _require(parent["family"] == record["family"], loc,
                     "mutation family differs from parent", errors)
            _require(parent["required_clarifications"] == record["required_clarifications"], loc,
                     "mutation required_clarifications differ from parent", errors)
    return errors


def statistics(records: list[dict[str, Any]]) -> dict[str, Any]:
    count = lambda field: dict(sorted(Counter(record[field] for record in records).items()))
    claim_kinds = Counter(
        claim["kind"] for record in records for claim in record["claims"]
        if claim.get("criticality") == "financial"
    )
    mutations = Counter(
        record["mutation"]["mutation_type"] for record in records
        if isinstance(record["mutation"], dict)
    )
    resolutions = Counter(record["expected_resolution"] for record in records)
    return {
        "total_candidate_cases": len(records),
        "by_split": count("split"),
        "by_family": count("family"),
        "by_resolution": dict(sorted(resolutions.items())),
        "by_annotation_status": dict(sorted(Counter(
            record["annotation"]["status"] for record in records).items())),
        "by_critical_claim_kind": dict(sorted(claim_kinds.items())),
        "by_mutation_type": dict(sorted(mutations.items())),
        "clarification_cases": resolutions["clarification_required"],
        "conflict_cases": resolutions["conflict_requires_resolution"],
        "supported_explicit_cases": sum(
            record["mutation"] is None and
            record["expected_resolution"] == "accepted_interpretation" and
            any(claim["criticality"] == "financial" for claim in record["claims"]) and
            all(
                claim["status"] in {"explicit", "derived", "user_confirmed", "superseded"}
                for claim in record["claims"] if claim["criticality"] == "financial"
            ) for record in records
        ),
    }


def review_queue(records: list[dict[str, Any]]) -> str:
    by_id = {record["case_id"]: record for record in records}
    lines = ["# Stage 2A candidate review queue", "",
             "All annotations below are drafts. A human must approve, edit, or reject each case.", ""]
    for record in sorted(records, key=lambda item: (item["split"], item["case_id"])):
        lines.extend([f"## {record['case_id']} ({record['split']}; {record['family']})", ""])
        for version in record["requirement_history"]:
            lines.append(f"- Requirement v{version['version']}: " + " | ".join(version["messages"]))
        lines.append(f"- Proposed resolution: `{record['expected_resolution']}`")
        parent_id = (record["mutation"] or {}).get("parent_case_id")
        claims = effective_claims(record, by_id)
        scopes = effective_scopes(record, by_id)
        label = f" (inherited from {parent_id})" if parent_id else ""
        critical = [f"{c['kind']}={c.get('value')} [{c['status']}; scope={c['scope_id']}]"
                    for c in claims if c["criticality"] == "financial"]
        lines.append(f"- Critical claims{label}: " + ("; ".join(critical) or "none proposed"))
        lines.append("- Behavior scopes" + label + ": " + json.dumps(
            scopes, ensure_ascii=False, sort_keys=True))
        if parent_id:
            lines.append(f"- Inherits canonical interpretation from: `{parent_id}`")
        assumptions = [f"{c['kind']}={c.get('value')} [scope={c['scope_id']}]" for c in claims
                       if c["status"] in {"assumed", "derived"}]
        lines.append(f"- Assumptions/derivations{label}: " +
                     ("; ".join(assumptions) or "none proposed"))
        lines.append("- Required clarifications: " +
                     ("; ".join(str(item) for item in record["required_clarifications"]) or "none"))
        lines.append("- Forbidden assumptions: " +
                     ("; ".join(record["forbidden_assumptions"]) or "none"))
        lines.append("- Expected behavior: " + json.dumps(
            record["behavior_expectations"], ensure_ascii=False, sort_keys=True))
        lines.append("- Mutation: " + json.dumps(record["mutation"], ensure_ascii=False, sort_keys=True))
        if record["annotation"].get("notes"):
            lines.append("- Annotation notes: " + "; ".join(record["annotation"]["notes"]))
        lines.extend(["- Decision: [ ] Approve  [ ] Edit  [ ] Reject", "- Reviewer note:", ""])
    return "\n".join(lines).rstrip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("validate", "stats", "review"))
    parser.add_argument("--corpus-dir", type=Path, default=ROOT / "corpus")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        records = load_corpus(args.corpus_dir)
        errors = validate(records)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 2
    if args.command == "validate":
        result = f"VALID: {len(records)} draft candidate cases"
    elif args.command == "stats":
        result = json.dumps(statistics(records), ensure_ascii=False, indent=2, sort_keys=True)
    else:
        result = review_queue(records)
    if args.output:
        args.output.write_text(result + "\n", encoding="utf-8")
    else:
        print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
