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
SPLITS = ("development", "evaluation")
RESOLUTIONS = {
    "accepted_interpretation", "clarification_required",
    "conflict_requires_resolution", "unsupported_for_current_study",
}
CLAIM_STATUSES = {
    "explicit", "derived", "assumed", "user_confirmed",
    "conflicted", "unresolved", "superseded",
}
ANNOTATION_STATUSES = {"draft", "reviewed", "adjudicated", "user_confirmed"}
MUTATIONS = {
    "wrong_choice_owner", "wrong_depositing_party", "wrong_account_owner",
    "wrong_payment_recipient", "wrong_token", "wrong_unit_scaling",
    "wrong_amount", "swapped_deadline", "reversed_timeout_branch",
    "missing_refund", "double_payment", "missing_terminal_outcome",
    "unauthorized_choice",
}
REQUIRED = {
    "case_id", "split", "family", "group_id", "requirement_history",
    "expected_resolution", "claims", "required_clarifications",
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

        claims = record["claims"]
        _require(isinstance(claims, list), loc, "claims must be a list", errors)
        claim_ids: dict[str, dict[str, Any]] = {}
        current_by_kind: dict[str, set[str]] = {}
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
                _require(isinstance(kind, str) and bool(kind), loc,
                         f"claim {claim_id}: kind is required", errors)
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
                if isinstance(status, str) and status not in {"superseded", "conflicted", "unresolved"} and isinstance(kind, str):
                    current_by_kind.setdefault(kind, set()).add(json.dumps(
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
                             and successor.get("kind") == claim.get("kind"), loc,
                             f"superseded claim {claim.get('claim_id')} lacks current successor", errors)
                    if successor:
                        old_versions = [item.get("requirement_version") for item in claim.get("evidence", [])]
                        new_versions = [item.get("requirement_version") for item in successor.get("evidence", [])]
                        if old_versions and new_versions and all(isinstance(v, int) for v in old_versions + new_versions):
                            _require(max(old_versions) < max(new_versions), loc,
                                     "supersession must follow requirement chronology", errors)
            if record["expected_resolution"] != "conflict_requires_resolution":
                for kind, values in current_by_kind.items():
                    _require(len(values) <= 1, loc,
                             f"active claim values conflict for {kind}", errors)

        mutation = record["mutation"]
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
        inherited = by_id[parent_id]["claims"] if parent_id else []
        claims = [f"{c['kind']}={c.get('value')} [{c['status']}]"
                  for c in inherited + record["claims"] if c["criticality"] == "financial"]
        lines.append("- Critical claims: " + ("; ".join(claims) or "none proposed"))
        if parent_id:
            lines.append(f"- Inherits canonical interpretation from: `{parent_id}`")
        assumptions = [f"{c['kind']}={c.get('value')}" for c in record["claims"]
                       if c["status"] in {"assumed", "derived"}]
        lines.append("- Assumptions/derivations: " + ("; ".join(assumptions) or "none proposed"))
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
