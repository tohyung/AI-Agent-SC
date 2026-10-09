"""Dataset labels are gated by immutable evidence, replay, and independent review."""

from copy import deepcopy
import json
import sqlite3

import pytest

from research.architecture.artifacts import ArtifactEnvelope, stable_artifact_id
from research.architecture.ports import StageContext
from research.architecture.status import AuthorityLevel, ImplementationStatus
from research.stage3.reference import PinnedMarloweReference
from research.stage4.oracles import NoWarningsOracle
from research.stage5.dataset import PropertyDataset
from research.stage5.registry import (PropertyCheckResult, PropertyStatus,
                                      PropertyValidationPort)


STATE = {"accounts": [], "choices": [], "boundValues": [], "minTime": 0}
META = {"upstream_commit": "7b5b1e900ec53a8eb18747992bec73470704dfcb",
        "reference_driver_version": "0.1.0"}
REFERENCE_IDENTITY = f"{META['upstream_commit']}:{META['reference_driver_version']}"
TRANSACTION = {"interval": {"from": 0, "to": 0}, "inputs": []}
REFERENCE_RESULT = {"status": "Success", "final_contract": "close",
                    "final_state": STATE, "meta": META,
                    "steps": [{"status": "Success", "warnings": [], "payments": []}]}


def _artifact(kind, version, producer, payload):
    return ArtifactEnvelope(kind, version, producer,
                            ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                            AuthorityLevel.NO_AUTHORITY, payload)


def _sources(*, simulated=False, verdict="SATISFIED", contract_ast="close"):
    contract = _artifact("contract-candidate", "core-v1", "compile",
                         {"contract": contract_ast, "simulation_only": simulated})
    response = deepcopy(REFERENCE_RESULT)
    if verdict == "VIOLATED":
        response["steps"][0]["warnings"] = [{"kind": "PartialPay"}]
    elif verdict == "INCONCLUSIVE":
        del response["steps"][0]["warnings"]
    trace = {"transactions": [TRANSACTION], "steps": [response],
             "status": "Success"}
    trace["trace_id"] = stable_artifact_id("reference-trace", "v1", trace)
    graph = _artifact("exploration-graph", "v1", "exploration",
                      {"domain_id": "reviewed", "coverage": "BOUNDED", "traces": [trace]})
    finding = NoWarningsOracle().evaluate(trace)
    assert finding["verdict"] == verdict
    oracle = _artifact("oracle-findings", "v1", "oracle_evaluation",
                       {"graph_id": graph.artifact_id, "findings": [finding]})
    comparison = _artifact("reference-comparison", "v1", "semantic_comparison",
                           {"contract_artifact_id": contract.artifact_id,
                            "verdict": "SATISFIED", "reference_identity": REFERENCE_IDENTITY,
                            "simulation_only": simulated,
                            "expectation": {"source_kind": "reviewed",
                                            "reviewer_id": "source-owner",
                                            "request": {"state": STATE}}})
    adversarial = _artifact("adversarial-candidates", "v1", "adversarial_search",
                            {"candidates": ([{"finding": finding}]
                                            if verdict == "VIOLATED" else [])})
    return [contract, comparison, graph, oracle, adversarial]


def _reference(monkeypatch, response=None):
    reference = PinnedMarloweReference(binary="pinned-test")
    monkeypatch.setattr(reference, "execute", lambda request: deepcopy(
        REFERENCE_RESULT if response is None else response))
    return reference


def test_stage5_collects_satisfied_observation_without_promoting_property(tmp_path):
    dataset = PropertyDataset(tmp_path / "property.sqlite3")
    port = PropertyValidationPort(dataset=dataset)
    outcome = port.execute(_sources(), StageContext("run-1"))
    assert outcome.result.semantic_status == "NO_CANDIDATES"
    ids = outcome.artifacts[0].payload["dataset_observation_ids"]
    assert len(ids) == 1
    assert dataset.get(ids[0])["finding"]["verdict"] == "SATISFIED"
    assert dataset.audit()["example_count"] == 1
    assert dataset.export_approved(tmp_path / "train.jsonl")["count"] == 0


def test_checker_result_is_evidence_not_an_adjudicated_training_label(tmp_path):
    dataset = PropertyDataset(tmp_path / "property.sqlite3")

    class Checker:
        def check(self, candidate):
            return PropertyCheckResult(PropertyStatus.REFUTED, ("checker-evidence",),
                                       "checker-reviewer")

    outcome = PropertyValidationPort(checker=Checker(), dataset=dataset).execute(
        _sources(verdict="VIOLATED"), StageContext("run-violation"))
    assert outcome.result.semantic_status == "REFUTED"
    example_id = outcome.artifacts[0].payload["dataset_observation_ids"][0]
    example = dataset.get(example_id)
    assert example["property_candidate_id"] == outcome.artifacts[0].payload["candidates"][0][
        "property_id"]
    assert dataset.audit()["event_count"] == 3
    assert dataset.export_approved(tmp_path / "train.jsonl")["count"] == 0


def test_property_identity_includes_contract_not_only_observed_trace(tmp_path):
    dataset = PropertyDataset(tmp_path / "property.sqlite3")
    port = PropertyValidationPort(dataset=dataset)
    first = port.execute(_sources(verdict="VIOLATED"), StageContext("run-1"))
    second = port.execute(_sources(
        verdict="VIOLATED", contract_ast={"when": [], "timeout": 100,
                                            "timeout_continuation": "close"}),
        StageContext("run-2"))
    assert (first.artifacts[0].payload["candidates"][0]["property_id"]
            != second.artifacts[0].payload["candidates"][0]["property_id"])
    assert dataset.audit()["example_count"] == 2


def test_property_candidate_event_is_idempotent_for_same_run(tmp_path):
    dataset = PropertyDataset(tmp_path / "property.sqlite3")
    port = PropertyValidationPort(dataset=dataset)
    sources = _sources(verdict="VIOLATED")
    port.execute(sources, StageContext("run-1"))
    anchor = dataset.audit()
    port.execute(sources, StageContext("run-1"))
    assert dataset.audit() == anchor


def test_candidate_and_checker_events_require_matching_provenance(tmp_path):
    dataset = PropertyDataset(tmp_path / "property.sqlite3")
    outcome = PropertyValidationPort(dataset=dataset).execute(
        _sources(verdict="VIOLATED"), StageContext("run-1"))
    candidate = outcome.artifacts[0].payload["candidates"][0]
    forged = json.loads(json.dumps(candidate))
    forged["contract_artifact_id"] = "another-contract"
    with pytest.raises(ValueError, match="conflicts with oracle observation"):
        dataset.record_property_candidate(forged, "run-1")
    with pytest.raises(ValueError, match="valid status"):
        dataset.record_checker_outcome(candidate["property_id"], status="PROVEN",
                                       evidence_ids=["evidence"], reviewer_id="reviewer",
                                       run_id="run-1")
    with pytest.raises(ValueError, match="valid status"):
        dataset.record_checker_outcome(candidate["property_id"], status="REFUTED",
                                       evidence_ids=[], reviewer_id="reviewer", run_id="run-1")
    assert dataset.audit()["event_count"] == 2


def test_dedupe_preserves_distinct_run_provenance_and_external_anchor(tmp_path):
    dataset = PropertyDataset(tmp_path / "property.sqlite3")
    sources = _sources()
    first = dataset.ingest_artifacts(sources, "run-1")
    assert dataset.ingest_artifacts(sources, "run-1") == first
    assert dataset.audit()["event_count"] == 1
    assert dataset.ingest_artifacts(sources, "run-2") == first
    anchor = dataset.audit()
    assert anchor["example_count"] == 1
    assert anchor["event_count"] == 2
    dataset.review(first[0], reviewer_id="reviewer-a", label="SATISFIED",
                   rationale="Trace output checked", consent_for_training=False)
    with pytest.raises(ValueError, match="external anchor"):
        dataset.audit(anchor)


def test_snapshot_ingest_rejects_tampered_artifact(tmp_path):
    dataset = PropertyDataset(tmp_path / "property.sqlite3")
    sources = _sources()
    stages = {stage: {"run_status": "SUCCEEDED", "output_artifacts": [artifact.artifact_id]}
              for stage, artifact in zip(("compile", "semantic_comparison", "exploration",
                                           "oracle_evaluation"), sources[:4])}
    snapshot = {"run_id": "old-run", "stages": stages,
                "artifacts": {item.artifact_id: item.to_dict() for item in sources[:4]}}
    assert len(dataset.ingest_snapshot(snapshot)) == 1
    snapshot["artifacts"][sources[0].artifact_id]["payload"]["contract"] = "tampered"
    with pytest.raises(ValueError, match="content hash"):
        dataset.ingest_snapshot(snapshot)


def test_snapshot_ingests_inconclusive_oracle_artifact(tmp_path):
    dataset = PropertyDataset(tmp_path / "property.sqlite3")
    sources = _sources(verdict="INCONCLUSIVE")
    stages = {stage: {"run_status": "SUCCEEDED", "output_artifacts": [artifact.artifact_id]}
              for stage, artifact in zip(("compile", "semantic_comparison", "exploration",
                                          "oracle_evaluation"), sources[:4])}
    stages["oracle_evaluation"]["run_status"] = "INCONCLUSIVE"
    snapshot = {"run_id": "old-inconclusive", "stages": stages,
                "artifacts": {item.artifact_id: item.to_dict() for item in sources[:4]}}
    example_ids = dataset.ingest_snapshot(snapshot)
    assert len(example_ids) == 1
    assert dataset.get(example_ids[0])["finding"]["verdict"] == "INCONCLUSIVE"


def test_replay_and_two_concordant_reviews_are_required_for_export(tmp_path, monkeypatch):
    dataset = PropertyDataset(tmp_path / "property.sqlite3")
    example_id = dataset.ingest_artifacts(_sources(), "run-1")[0]
    target = tmp_path / "train.jsonl"
    assert dataset.export_approved(target)["count"] == 0
    dataset.review(example_id, reviewer_id="alice", label="SATISFIED",
                   rationale="No warning in reference trace", consent_for_training=True)
    dataset.review(example_id, reviewer_id="bob", label="SATISFIED",
                   rationale="Independently checked outcome", consent_for_training=True)
    assert dataset.export_approved(target)["count"] == 0
    assert dataset.verify_reference(example_id, _reference(monkeypatch)) == "MATCH"
    assert dataset.export_approved(target)["count"] == 0
    dataset.authorize_use(example_id, grantor_id="source-owner",
                          rationale="I own this requirement and approve validator training",
                          granted=True)
    manifest = dataset.export_approved(target)
    assert manifest["count"] == 1
    exported = json.loads(target.read_text(encoding="utf-8"))
    assert exported["adjudicated_label"] == "SATISFIED"
    assert exported["trust_tier"] == "PINNED_REPLAY_TWO_REVIEWS_ASSERTED_USE_RIGHTS"
    assert exported["leakage_group_ids"] == [exported["observation"]["source_artifact_ids"][
        "contract"]]
    assert manifest["reviewer_identity"] == "self_asserted_not_authenticated"
    assert manifest["split_status"] == "UNASSIGNED_GROUP_BY_REQUIREMENT_AND_CONTRACT"
    dataset.authorize_use(example_id, grantor_id="source-owner",
                          rationale="Withdraw my previous grant", granted=False)
    assert dataset.export_approved(target)["count"] == 0


def test_replay_mismatch_or_conflicting_review_blocks_export(tmp_path, monkeypatch):
    dataset = PropertyDataset(tmp_path / "property.sqlite3")
    example_id = dataset.ingest_artifacts(_sources(), "run-1")[0]
    bad = deepcopy(REFERENCE_RESULT)
    bad["steps"][0]["warnings"] = [{"kind": "warning"}]
    assert dataset.verify_reference(example_id, _reference(monkeypatch, bad)) == "MISMATCH"
    for reviewer, label in (("alice", "SATISFIED"), ("bob", "VIOLATED")):
        dataset.review(example_id, reviewer_id=reviewer, label=label,
                       rationale="Independent review", consent_for_training=True)
    assert dataset.export_approved(tmp_path / "train.jsonl")["count"] == 0
    assert dataset.verify_reference(example_id, _reference(monkeypatch)) == "MATCH"
    assert dataset.export_approved(tmp_path / "train.jsonl")["count"] == 0


def test_concordant_reviews_opposing_oracle_are_not_exported(tmp_path, monkeypatch):
    dataset = PropertyDataset(tmp_path / "property.sqlite3")
    example_id = dataset.ingest_artifacts(_sources(), "run-1")[0]
    assert dataset.verify_reference(example_id, _reference(monkeypatch)) == "MATCH"
    for reviewer in ("alice", "bob"):
        dataset.review(example_id, reviewer_id=reviewer, label="VIOLATED",
                       rationale="Disputing the oracle", consent_for_training=True)
    dataset.authorize_use(example_id, grantor_id="source-owner",
                          rationale="Approved for validator training", granted=True)
    assert dataset.export_approved(tmp_path / "train.jsonl")["count"] == 0


def test_replay_checks_each_transaction_and_intermediate_state(tmp_path, monkeypatch):
    dataset = PropertyDataset(tmp_path / "property.sqlite3")
    contract, comparison, _, _, _ = _sources()
    first = deepcopy(REFERENCE_RESULT)
    first["final_contract"] = {"when": [], "timeout": 100,
                               "timeout_continuation": "close"}
    second = deepcopy(REFERENCE_RESULT)
    trace = {"transactions": [TRANSACTION, TRANSACTION],
             "steps": [first, second], "status": "Success"}
    trace["trace_id"] = stable_artifact_id("reference-trace", "v1", trace)
    graph = _artifact("exploration-graph", "v1", "exploration",
                      {"domain_id": "reviewed", "coverage": "BOUNDED", "traces": [trace]})
    finding = NoWarningsOracle().evaluate(trace)
    oracle = _artifact("oracle-findings", "v1", "oracle_evaluation",
                       {"graph_id": graph.artifact_id, "findings": [finding]})
    example_id = dataset.ingest_artifacts([contract, comparison, graph, oracle], "run-1")[0]
    reference = PinnedMarloweReference(binary="pinned-test")
    requests = []

    def replay(request):
        requests.append(request)
        return deepcopy((first, second)[len(requests) - 1])

    monkeypatch.setattr(reference, "execute", replay)
    assert dataset.verify_reference(example_id, reference) == "MATCH"
    assert len(requests) == 2
    assert requests[1].contract == first["final_contract"]
    assert requests[1].state == first["final_state"]
    altered = deepcopy(first)
    altered["final_contract"] = "close"
    monkeypatch.setattr(reference, "execute", lambda request: altered)
    assert dataset.verify_reference(example_id, reference) == "MISMATCH"


def test_simulation_and_inconclusive_never_enter_training_export(tmp_path, monkeypatch):
    dataset = PropertyDataset(tmp_path / "property.sqlite3")
    ids = [dataset.ingest_artifacts(_sources(simulated=True), "simulated")[0],
           dataset.ingest_artifacts(_sources(verdict="INCONCLUSIVE"), "uncertain")[0]]
    for example_id in ids:
        assert dataset.verify_reference(example_id, _reference(monkeypatch)) in {
            "MATCH", "MISMATCH"}
        for reviewer in ("alice", "bob"):
            dataset.review(example_id, reviewer_id=reviewer, label="SATISFIED",
                           rationale="Reviewed but not training eligible",
                           consent_for_training=True)
    assert dataset.export_approved(tmp_path / "train.jsonl")["count"] == 0


def test_tampered_database_payload_or_event_chain_is_detected(tmp_path):
    path = tmp_path / "property.sqlite3"
    dataset = PropertyDataset(path)
    example_id = dataset.ingest_artifacts(_sources(), "run-1")[0]
    with sqlite3.connect(path) as connection:
        original = connection.execute(
            "SELECT payload FROM examples WHERE example_id=?", (example_id,)).fetchone()[0]
        connection.execute("UPDATE examples SET payload=? WHERE example_id=?",
                           (b"{}", example_id))
    with pytest.raises(ValueError, match="content integrity"):
        dataset.audit()
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE examples SET payload=? WHERE example_id=?",
                           (original, example_id))
        connection.execute("UPDATE events SET event_hash=? WHERE sequence=1", ("0" * 64,))
    with pytest.raises(ValueError, match="event chain"):
        dataset.audit()


def test_review_requires_explicit_consent_and_replay_adapter_type(tmp_path):
    dataset = PropertyDataset(tmp_path / "property.sqlite3")
    example_id = dataset.ingest_artifacts(_sources(), "run-1")[0]
    with pytest.raises(TypeError, match="pinned"):
        dataset.verify_reference(example_id, object())
    with pytest.raises(ValueError, match="explicit consent"):
        dataset.review(example_id, reviewer_id="alice", label="SATISFIED",
                       rationale="checked", consent_for_training=None)
    with pytest.raises(ValueError, match="source reviewer"):
        dataset.authorize_use(example_id, grantor_id="unrelated",
                              rationale="Not the source owner", granted=True)
