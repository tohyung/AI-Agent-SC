"""Local, auditable property observations with explicit review and replay gates."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
from typing import Any, Iterator

from research.architecture.artifacts import (ArtifactEnvelope, canonical_json_v1,
                                             stable_artifact_id)
from research.architecture.ports import latest_artifact
from research.architecture.status import AuthorityLevel, ImplementationStatus
from research.stage3.reference import PinnedMarloweReference, ReferenceRequest
from research.stage4.oracles import NoWarningsOracle


SCHEMA_VERSION = "property-observation-v1"
DATABASE_VERSION = 1
GENESIS_HASH = "0" * 64
REVIEW_LABELS = {"SATISFIED", "VIOLATED", "INCONCLUSIVE"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(payload: Any) -> str:
    return hashlib.sha256(canonical_json_v1(payload)).hexdigest()


def _artifact_from_record(record: dict[str, Any]) -> ArtifactEnvelope:
    artifact = ArtifactEnvelope(
        record["artifact_type"], record["schema_version"], record["producer_stage"],
        ImplementationStatus(record["implementation_status"]),
        AuthorityLevel(record["authority_level"]), record["payload"],
        record.get("metadata", {}))
    if (artifact.artifact_id != record.get("artifact_id")
            or artifact.content_hash != record.get("content_hash")):
        raise ValueError("snapshot artifact content hash mismatch")
    return artifact


def _observations(artifacts: list[ArtifactEnvelope]) -> list[dict[str, Any]]:
    requirement = latest_artifact(artifacts, "requirement-history")
    contract = latest_artifact(artifacts, "contract-candidate")
    graph = latest_artifact(artifacts, "exploration-graph")
    oracle = latest_artifact(artifacts, "oracle-findings")
    comparison = latest_artifact(artifacts, "reference-comparison")
    if any(item is None for item in (contract, graph, oracle, comparison)):
        return []
    if (oracle.payload.get("graph_id") != graph.artifact_id
            or comparison.payload.get("contract_artifact_id") != contract.artifact_id
            or comparison.payload.get("verdict") != "SATISFIED"):
        raise ValueError("property source artifact lineage is inconsistent")
    traces = {item["trace_id"]: item for item in graph.payload["traces"]}
    if len(traces) != len(graph.payload["traces"]):
        raise ValueError("duplicate trace identity in exploration graph")
    request = comparison.payload.get("expectation", {}).get("request", {})
    state = request.get("state") if isinstance(request, dict) else None
    result = []
    for finding in oracle.payload["findings"]:
        trace = traces.get(finding.get("trace_id"))
        if trace is None:
            raise ValueError("oracle finding references an absent trace")
        if (trace["trace_id"] != stable_artifact_id(
                "reference-trace", "v1", {key: value for key, value in trace.items()
                                          if key != "trace_id"})):
            raise ValueError("reference trace content hash mismatch")
        if finding.get("verdict") not in {
                "SATISFIED", "VIOLATED", "INCONCLUSIVE", "NOT_EVALUATED", "UNSUPPORTED"}:
            raise ValueError("unsupported oracle verdict")
        result.append({
            "schema_version": SCHEMA_VERSION,
            "contract": contract.payload["contract"],
            "initial_state": state,
            "trace": trace,
            "finding": finding,
            "property_candidate_id": (stable_artifact_id("property-candidate", "v1", {
                "finding": finding, "contract_artifact_id": contract.artifact_id})
                                      if finding["verdict"] == "VIOLATED" else None),
            "source_artifact_ids": {
                "requirement": requirement.artifact_id if requirement is not None else None,
                "contract": contract.artifact_id,
                "comparison": comparison.artifact_id,
                "exploration": graph.artifact_id,
                "oracle": oracle.artifact_id,
            },
            "reference_identity": comparison.payload.get("reference_identity"),
            "coverage": graph.payload.get("coverage"),
            "domain_id": graph.payload.get("domain_id"),
            "simulation_only": (contract.payload.get("simulation_only") is True
                                or comparison.payload.get("simulation_only") is True),
            "expectation_source_kind": comparison.payload.get("expectation", {}).get(
                "source_kind"),
            "source_reviewer_id": comparison.payload.get("expectation", {}).get(
                "reviewer_id"),
            "leakage_group_ids": [identifier for identifier in (
                requirement.artifact_id if requirement is not None else None,
                contract.artifact_id) if identifier is not None],
        })
    return result


def _trace_projection(responses: list[dict[str, Any]]) -> dict[str, Any]:
    last = responses[-1]
    steps = [step for response in responses for step in response.get("steps", [])]
    return {
        "status": last.get("status"),
        "final_contract": last.get("final_contract"),
        "final_state": last.get("final_state"),
        "warnings": [warning for step in steps for warning in step.get("warnings", [])],
        "payments": [payment for step in steps for payment in step.get("payments", [])],
    }


class PropertyDataset:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in {0, DATABASE_VERSION}:
                raise ValueError("unsupported property dataset database version")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS examples (
                    example_id TEXT PRIMARY KEY,
                    content_hash TEXT NOT NULL,
                    payload BLOB NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS observed_runs (
                    example_id TEXT NOT NULL REFERENCES examples(example_id),
                    run_id TEXT NOT NULL,
                    PRIMARY KEY (example_id, run_id)
                );
                CREATE TABLE IF NOT EXISTS property_links (
                    property_id TEXT NOT NULL,
                    example_id TEXT NOT NULL REFERENCES examples(example_id),
                    PRIMARY KEY (property_id, example_id)
                );
                CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    example_id TEXT NOT NULL REFERENCES examples(example_id),
                    payload BLOB NOT NULL,
                    previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS events_example_kind
                    ON events(example_id, kind);
            """)
            connection.execute(f"PRAGMA user_version={DATABASE_VERSION}")

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _event(connection: sqlite3.Connection, kind: str, example_id: str,
               payload: dict[str, Any]) -> None:
        last = connection.execute(
            "SELECT event_hash FROM events ORDER BY sequence DESC LIMIT 1").fetchone()
        previous = last[0] if last else GENESIS_HASH
        created_at = _now()
        encoded = canonical_json_v1(payload)
        cursor = connection.execute(
            "INSERT INTO events(kind,example_id,payload,previous_hash,event_hash,created_at) "
            "VALUES(?,?,?,?,?,?)", (kind, example_id, encoded, previous, "", created_at))
        digest = _hash({"sequence": cursor.lastrowid, "kind": kind,
                        "example_id": example_id, "payload": payload,
                        "previous_hash": previous, "created_at": created_at})
        connection.execute("UPDATE events SET event_hash=? WHERE sequence=?",
                           (digest, cursor.lastrowid))

    def ingest_artifacts(self, artifacts: list[ArtifactEnvelope], run_id: str) -> list[str]:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("dataset observation needs a run ID")
        observations = _observations(artifacts)
        ids = []
        with self._connection() as connection:
            for payload in observations:
                example_id = stable_artifact_id("property-observation", "v1", payload)
                encoded = canonical_json_v1(payload)
                existing = connection.execute(
                    "SELECT payload FROM examples WHERE example_id=?", (example_id,)).fetchone()
                if existing is not None and existing[0] != encoded:
                    raise ValueError("property observation identity collision")
                if existing is None:
                    connection.execute(
                        "INSERT INTO examples VALUES(?,?,?,?)",
                        (example_id, _hash(payload), encoded, _now()))
                property_id = payload.get("property_candidate_id")
                if property_id is not None:
                    connection.execute(
                        "INSERT OR IGNORE INTO property_links VALUES(?,?)",
                        (property_id, example_id))
                seen = connection.execute(
                    "SELECT 1 FROM observed_runs WHERE example_id=? AND run_id=?",
                    (example_id, run_id)).fetchone()
                if seen is None:
                    connection.execute("INSERT INTO observed_runs VALUES(?,?)",
                                       (example_id, run_id))
                    self._event(connection, "OBSERVED", example_id, {"run_id": run_id})
                ids.append(example_id)
        return ids

    def ingest_snapshot(self, snapshot: dict[str, Any]) -> list[str]:
        stages = snapshot.get("stages", {})
        records = snapshot.get("artifacts", {})
        stage_names = ("compile", "semantic_comparison", "exploration", "oracle_evaluation")
        if (any(stages.get(stage, {}).get("run_status") != "SUCCEEDED"
                for stage in stage_names[:-1])
                or stages.get("oracle_evaluation", {}).get("run_status") not in {
                    "SUCCEEDED", "INCONCLUSIVE"}):
            return []
        artifacts = []
        for stage in stage_names:
            ids = stages[stage].get("output_artifacts", [])
            if len(ids) != 1 or ids[0] not in records:
                raise ValueError(f"snapshot lacks {stage} artifact")
            artifacts.append(_artifact_from_record(records[ids[0]]))
        if isinstance(snapshot.get("requirement_history"), list):
            artifacts.insert(0, ArtifactEnvelope(
                "requirement-history", "v1", "user_input",
                ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                AuthorityLevel.NO_AUTHORITY, snapshot["requirement_history"]))
        return self.ingest_artifacts(artifacts, snapshot["run_id"])

    def get(self, example_id: str) -> dict[str, Any]:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT payload FROM examples WHERE example_id=?", (example_id,)).fetchone()
        if row is None:
            raise KeyError(example_id)
        return json.loads(row[0])

    def verify_reference(self, example_id: str, reference: PinnedMarloweReference) -> str:
        if not isinstance(reference, PinnedMarloweReference):
            raise TypeError("dataset replay requires the pinned Marlowe reference adapter")
        example = self.get(example_id)
        trace = example["trace"]
        if (not isinstance(example["initial_state"], dict)
                or not trace.get("transactions")
                or example["finding"].get("oracle_id") != NoWarningsOracle.oracle_id):
            outcome = "UNAVAILABLE"
        else:
            outcome = "MISMATCH"
            try:
                current_contract = example["contract"]
                current_state = example["initial_state"]
                responses = []
                matched = len(trace["transactions"]) == len(trace["steps"])
                for transaction, stored in zip(trace["transactions"], trace["steps"]):
                    replay = reference.execute(ReferenceRequest(
                        current_contract, current_state, (transaction,)))
                    if not isinstance(replay, dict):
                        raise ValueError("reference result is not an object")
                    if replay.get("status") in {"Unavailable", "Timeout", "InternalError"}:
                        matched = False
                        outcome = "UNAVAILABLE"
                        break
                    meta = replay.get("meta", {})
                    identity = (f"{meta.get('upstream_commit')}:{meta.get('reference_driver_version')}"
                                if isinstance(meta, dict) else None)
                    responses.append(replay)
                    if (identity != example["reference_identity"]
                            or _trace_projection([replay]) != _trace_projection([stored])):
                        matched = False
                        break
                    current_contract = replay.get("final_contract")
                    current_state = replay.get("final_state")
                if matched and responses and responses[-1].get("status") == trace["status"]:
                    actual_verdict = NoWarningsOracle().evaluate({
                        "trace_id": trace["trace_id"], "status": trace["status"],
                        "steps": responses})["verdict"]
                    if actual_verdict == example["finding"]["verdict"]:
                        outcome = "MATCH"
            except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
                outcome = "UNAVAILABLE"
        with self._connection() as connection:
            self._event(connection, "REPLAY_CHECK", example_id, {"outcome": outcome,
                                                                "reference_identity": example[
                                                                    "reference_identity"]})
        return outcome

    def review(self, example_id: str, *, reviewer_id: str, label: str,
               rationale: str, consent_for_training: bool) -> None:
        self.get(example_id)
        if (not isinstance(reviewer_id, str) or not reviewer_id.strip()
                or not isinstance(rationale, str) or not rationale.strip()
                or label not in REVIEW_LABELS or type(consent_for_training) is not bool):
            raise ValueError("review needs reviewer, label, rationale and explicit consent flag")
        with self._connection() as connection:
            self._event(connection, "REVIEW", example_id, {
                "reviewer_id": reviewer_id.strip(), "label": label,
                "rationale": rationale.strip(), "consent_for_training": consent_for_training})

    def authorize_use(self, example_id: str, *, grantor_id: str,
                      rationale: str, granted: bool) -> None:
        example = self.get(example_id)
        if (not isinstance(grantor_id, str) or not grantor_id.strip()
                or grantor_id.strip() != example.get("source_reviewer_id")
                or not isinstance(rationale, str) or not rationale.strip()
                or type(granted) is not bool):
            raise ValueError("data-use authorization requires the recorded source reviewer")
        with self._connection() as connection:
            self._event(connection, "DATA_USE_AUTHORIZATION", example_id, {
                "grantor_id": grantor_id.strip(), "scope": "validator_training",
                "granted": granted, "rationale": rationale.strip(),
                "identity_assurance": "self_asserted"})

    def record_checker_outcome(self, property_id: str, *, status: str,
                               evidence_ids: list[str], reviewer_id: str | None,
                               run_id: str) -> None:
        if (not isinstance(property_id, str) or not property_id
                or status not in {"VALIDATED_FOR_SCOPE", "REFUTED", "INCONCLUSIVE"}
                or not isinstance(run_id, str) or not run_id.strip()
                or not isinstance(evidence_ids, list)
                or any(not isinstance(item, str) or not item.strip()
                       for item in evidence_ids)
                or (status != "INCONCLUSIVE" and
                    (not evidence_ids or not isinstance(reviewer_id, str)
                     or not reviewer_id.strip()))):
            raise ValueError("checker outcome needs a valid status and evidence provenance")
        with self._connection() as connection:
            matching = [row[0] for row in connection.execute(
                "SELECT example_id FROM property_links WHERE property_id=?", (property_id,))]
            if not matching:
                raise ValueError("checker outcome has no recorded property candidate")
            for example_id in matching:
                if connection.execute(
                    "SELECT 1 FROM events WHERE example_id=? AND kind='PROPERTY_CANDIDATE' "
                    "LIMIT 1", (example_id,)).fetchone() is None:
                    raise ValueError("checker outcome precedes property candidate")
                self._event(connection, "CHECKER_OUTCOME", example_id, {
                    "property_id": property_id, "status": status,
                    "evidence_ids": evidence_ids, "reviewer_id": reviewer_id,
                    "run_id": run_id, "adjudicated_label": None})

    def record_property_candidate(self, candidate: dict[str, Any], run_id: str) -> None:
        if (not isinstance(candidate, dict) or not isinstance(candidate.get("scope"), dict)
                or not isinstance(run_id, str) or not run_id.strip()):
            raise ValueError("property candidate needs content and run provenance")
        property_id = candidate.get("property_id")
        if not isinstance(property_id, str) or not property_id:
            raise ValueError("property candidate needs an ID")
        with self._connection() as connection:
            matching = [row for row in connection.execute(
                "SELECT example_id FROM property_links WHERE property_id=?", (property_id,))]
            if not matching:
                raise ValueError("property candidate has no recorded oracle observation")
            for (example_id,) in matching:
                example = json.loads(connection.execute(
                    "SELECT payload FROM examples WHERE example_id=?", (example_id,)
                ).fetchone()[0])
                if (candidate.get("contract_artifact_id") != example["source_artifact_ids"][
                        "contract"]
                        or candidate.get("source_finding_id") != example["trace"]["trace_id"]
                        or candidate.get("scope", {}).get("oracle_id") != example["finding"][
                            "oracle_id"]
                        or candidate.get("scope", {}).get("trace_id") != example["trace"][
                            "trace_id"]):
                    raise ValueError("property candidate conflicts with oracle observation")
                previous = connection.execute(
                    "SELECT payload FROM events WHERE example_id=? AND kind='PROPERTY_CANDIDATE'",
                    (example_id,)).fetchall()
                existing = [json.loads(row[0]) for row in previous]
                if any(item["candidate"] != candidate for item in existing):
                    raise ValueError("property candidate ID has conflicting content")
                event = {"run_id": run_id, "candidate": candidate,
                         "adjudicated_label": None}
                if event not in existing:
                    self._event(connection, "PROPERTY_CANDIDATE", example_id, event)

    def _events_for(self, connection: sqlite3.Connection, example_id: str
                    ) -> list[tuple[str, dict[str, Any]]]:
        rows = connection.execute(
            "SELECT kind,payload FROM events WHERE example_id=? ORDER BY sequence",
            (example_id,)).fetchall()
        return [(kind, json.loads(payload)) for kind, payload in rows]

    def _eligible(self, example: dict[str, Any], events: list[tuple[str, dict[str, Any]]]
                  ) -> tuple[str, int] | None:
        if example["simulation_only"] or example["finding"]["verdict"] not in {
                "SATISFIED", "VIOLATED"}:
            return None
        replays = [payload for kind, payload in events if kind == "REPLAY_CHECK"]
        if not replays or replays[-1]["outcome"] != "MATCH":
            return None
        grants = [payload for kind, payload in events if kind == "DATA_USE_AUTHORIZATION"]
        if (not grants or grants[-1]["granted"] is not True
                or grants[-1]["grantor_id"] != example.get("source_reviewer_id")):
            return None
        reviewers = {payload["reviewer_id"]: payload for kind, payload in events
                     if kind == "REVIEW"}
        if (len(reviewers) < 2 or not all(item["consent_for_training"]
                                         for item in reviewers.values())):
            return None
        labels = {item["label"] for item in reviewers.values()}
        if len(labels) != 1 or example["finding"]["verdict"] not in labels:
            return None
        return labels.pop(), len(reviewers)

    def audit(self, expected_anchor: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._connection() as connection:
            if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise ValueError("property dataset foreign-key integrity failure")
            examples = connection.execute(
                "SELECT example_id,content_hash,payload FROM examples ORDER BY example_id").fetchall()
            for example_id, digest, encoded in examples:
                payload = json.loads(encoded)
                if (canonical_json_v1(payload) != encoded or _hash(payload) != digest
                        or stable_artifact_id("property-observation", "v1", payload)
                        != example_id):
                    raise ValueError("property observation content integrity failure")
            links = set(connection.execute(
                "SELECT property_id,example_id FROM property_links").fetchall())
            expected_links = {(payload["property_candidate_id"], example_id)
                              for example_id, _, encoded in examples
                              for payload in (json.loads(encoded),)
                              if payload.get("property_candidate_id") is not None}
            if links != expected_links:
                raise ValueError("property candidate index integrity failure")
            rows = connection.execute(
                "SELECT sequence,kind,example_id,payload,previous_hash,event_hash,created_at "
                "FROM events ORDER BY sequence").fetchall()
            previous = GENESIS_HASH
            for expected_sequence, row in enumerate(rows, 1):
                sequence, kind, example_id, encoded, prior, digest, created_at = row
                payload = json.loads(encoded)
                if kind not in {"OBSERVED", "REPLAY_CHECK", "REVIEW",
                                "DATA_USE_AUTHORIZATION", "PROPERTY_CANDIDATE",
                                "CHECKER_OUTCOME"}:
                    raise ValueError("unknown property dataset event kind")
                if (sequence != expected_sequence or prior != previous
                        or canonical_json_v1(payload) != encoded
                        or _hash({"sequence": sequence, "kind": kind,
                                  "example_id": example_id, "payload": payload,
                                  "previous_hash": prior, "created_at": created_at}) != digest):
                    raise ValueError("property dataset event chain integrity failure")
                previous = digest
            observed = connection.execute(
                "SELECT example_id,run_id FROM observed_runs").fetchall()
            recorded = {(example_id, payload["run_id"])
                        for _, kind, example_id, encoded, _, _, _ in rows
                        if kind == "OBSERVED" for payload in (json.loads(encoded),)}
            if set(observed) != recorded:
                raise ValueError("property dataset run provenance integrity failure")
        anchor = {"schema_version": SCHEMA_VERSION, "example_count": len(examples),
                  "event_count": len(rows), "head_hash": previous}
        if expected_anchor is not None and anchor != expected_anchor:
            raise ValueError("property dataset differs from external anchor")
        return anchor

    def export_approved(self, path: str | Path) -> dict[str, Any]:
        anchor = self.audit()
        records = []
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT example_id,payload FROM examples ORDER BY example_id").fetchall()
            for example_id, encoded in rows:
                example = json.loads(encoded)
                eligible = self._eligible(example, self._events_for(connection, example_id))
                if eligible is not None:
                    label, reviewer_count = eligible
                    records.append({"example_id": example_id, "observation": example,
                                    "adjudicated_label": label,
                                    "reviewer_count": reviewer_count,
                                    "leakage_group_ids": example.get(
                                        "leakage_group_ids", [example["source_artifact_ids"]["contract"]]),
                                    "trust_tier": "PINNED_REPLAY_TWO_REVIEWS_ASSERTED_USE_RIGHTS"})
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        content = b"".join(canonical_json_v1(record) + b"\n" for record in records)
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_bytes(content)
        os.replace(temporary, target)
        manifest = {"schema_version": SCHEMA_VERSION, "count": len(records),
                    "sha256": hashlib.sha256(content).hexdigest(), "source_anchor": anchor,
                    "reviewer_identity": "self_asserted_not_authenticated",
                    "data_use_rights": "source_reviewer_asserted_not_authenticated",
                    "split_status": "UNASSIGNED_GROUP_BY_REQUIREMENT_AND_CONTRACT",
                    "scope": "observed traces, not universal property proof"}
        manifest_path = target.with_suffix(target.suffix + ".manifest.json")
        manifest_path.write_bytes(canonical_json_v1(manifest) + b"\n")
        return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Local property dataset audit and review")
    parser.add_argument("--db", default="runs/property-dataset.sqlite3")
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("ingest-run")
    ingest.add_argument("snapshot", type=Path)
    audit = commands.add_parser("audit")
    audit.add_argument("--anchor", type=Path)
    replay = commands.add_parser("replay")
    replay.add_argument("example_id")
    replay.add_argument("--binary")
    review = commands.add_parser("review")
    review.add_argument("example_id")
    review.add_argument("--reviewer", required=True)
    review.add_argument("--label", choices=sorted(REVIEW_LABELS), required=True)
    review.add_argument("--rationale", required=True)
    review.add_argument("--consent-for-training", action="store_true")
    authorization = commands.add_parser("authorize-use")
    authorization.add_argument("example_id")
    authorization.add_argument("--grantor", required=True)
    authorization.add_argument("--rationale", required=True)
    authorization.add_argument("--revoke", action="store_true")
    export = commands.add_parser("export")
    export.add_argument("path", type=Path)
    args = parser.parse_args()
    dataset = PropertyDataset(args.db)
    if args.command == "ingest-run":
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        result: Any = {"example_ids": dataset.ingest_snapshot(snapshot)}
    elif args.command == "audit":
        expected = json.loads(args.anchor.read_text(encoding="utf-8")) if args.anchor else None
        if isinstance(expected, dict) and "source_anchor" in expected:
            expected = expected["source_anchor"]
        result = dataset.audit(expected)
    elif args.command == "replay":
        result = {"outcome": dataset.verify_reference(
            args.example_id, PinnedMarloweReference(binary=args.binary))}
    elif args.command == "review":
        dataset.review(args.example_id, reviewer_id=args.reviewer,
                       label=args.label, rationale=args.rationale,
                       consent_for_training=args.consent_for_training)
        result = {"review_recorded": True, "example_id": args.example_id}
    elif args.command == "authorize-use":
        dataset.authorize_use(args.example_id, grantor_id=args.grantor,
                              rationale=args.rationale, granted=not args.revoke)
        result = {"authorization_recorded": True, "granted": not args.revoke,
                  "example_id": args.example_id}
    else:
        result = dataset.export_approved(args.path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
