"""Static lint and pinned SMT warning analysis for generated candidates."""

from __future__ import annotations

from collections.abc import Callable
import subprocess
from threading import BoundedSemaphore
from typing import Any

from research.marlowe_core.logic_graph import LogicGraphVerifier
from research.marlowe_core.node3_mapper import map_counterexample, unmapped_findings
from research.marlowe_core.node3_policy import StructuredWarning
from research.architecture.artifacts import ArtifactEnvelope
from research.architecture.models import StageResult
from research.architecture.ports import StageContext, StageExecution, latest_artifact
from research.architecture.status import AuthorityLevel, ImplementationStatus, StageRunStatus
from research.integrations.smt_driver import DRIVER_VERSION, UPSTREAM_COMMIT, analyze


_SLOTS = BoundedSemaphore(2)


class SMTVerificationPort:
    def __init__(self, analyzer: Callable[[Any], dict[str, Any]] | None = None,
                 binary: str | None = None) -> None:
        self.analyzer = analyzer
        self.binary = binary

    def execute(self, artifacts: list[ArtifactEnvelope], context: StageContext) -> StageExecution:
        candidate = latest_artifact(artifacts, "contract-candidate")
        if candidate is None:
            return StageExecution(StageResult(
                "smt_verification", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                StageRunStatus.NOT_EVALUATED,
                diagnostics=["contract candidate unavailable"],
            ))
        contract = candidate.payload["contract"]
        lint = LogicGraphVerifier().lint(contract)
        if lint.errors:
            return self._outcome(candidate, StageRunStatus.FAILED, "LINT_FAILED",
                                 {"lint_errors": lint.errors, "lint_warnings": lint.warnings,
                                  "smt_status": "not_run", "structured_findings": []}, lint.errors)
        try:
            with _SLOTS:
                raw = (self.analyzer(contract) if self.analyzer is not None else
                       analyze(contract, binary=self.binary))
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
            return self._outcome(candidate, StageRunStatus.UNAVAILABLE, "SMT_UNAVAILABLE",
                                 {"lint_errors": [], "lint_warnings": lint.warnings,
                                  "smt_status": "Unavailable", "structured_findings": []},
                                 [f"SMT driver unavailable: {type(exc).__name__}"])
        if not isinstance(raw, dict):
            return self._outcome(candidate, StageRunStatus.INCONCLUSIVE, "SMT_INVALID_OUTPUT",
                                 {"lint_errors": [], "lint_warnings": lint.warnings,
                                  "smt_status": "InvalidOutput", "structured_findings": []},
                                 ["SMT driver returned a non-object result"])
        meta = raw.get("meta")
        if (not isinstance(meta, dict) or meta.get("upstream_commit") != UPSTREAM_COMMIT
                or meta.get("driver_version") != DRIVER_VERSION):
            return self._outcome(candidate, StageRunStatus.INCONCLUSIVE, "SMT_IDENTITY_MISMATCH",
                                 {"lint_errors": [], "lint_warnings": lint.warnings,
                                  "smt_status": raw.get("status"), "structured_findings": [],
                                  "meta": meta if isinstance(meta, dict) else None},
                                 ["SMT source or driver identity mismatch"])
        status = raw.get("status")
        notes = raw.get("analysis_notes", [])
        warning_data = raw.get("warnings", [])
        if (not isinstance(notes, list) or any(not isinstance(note, str) for note in notes)
                or not isinstance(warning_data, list) or any(
                not isinstance(item, dict) or not isinstance(item.get("type"), str)
                or not item["type"] for item in warning_data)):
            return self._outcome(candidate, StageRunStatus.INCONCLUSIVE, "SMT_INVALID_OUTPUT",
                                 {"lint_errors": [], "lint_warnings": lint.warnings,
                                  "smt_status": status, "structured_findings": []},
                                 ["SMT warnings or notes have invalid shape"])
        warnings = [StructuredWarning(item["type"],
                                      {key: value for key, value in item.items() if key != "type"})
                    for item in warning_data]
        findings = []
        if status == "Counterexample":
            try:
                findings = map_counterexample(contract, warnings, raw.get("counterexample"))
            except Exception:  # noqa: BLE001 - diagnostic mapping cannot alter the SMT verdict
                findings = unmapped_findings(contract, warnings, "mapper_internal_error")
        payload = {"lint_errors": [], "lint_warnings": lint.warnings,
                   "smt_status": status, "warnings": warning_data,
                   "counterexample": raw.get("counterexample"),
                   "structured_findings": [item.to_dict() for item in findings],
                   "analysis_notes": notes, "meta": meta,
                   "elapsed_seconds": (str(raw["elapsed_seconds"])
                                       if raw.get("elapsed_seconds") is not None else None)}
        process_exit = raw.get("process_exit")
        if (status == "Valid" and not notes and not warnings
                and (process_exit is None or type(process_exit) is int and process_exit == 0)):
            return self._outcome(candidate, StageRunStatus.SUCCEEDED, "NO_MODELED_WARNINGS",
                                 payload, [])
        if status == "Counterexample":
            diagnostics = ([item.message for item in findings] or
                           ["SMT found a warning trace without a mapped warning"])
            return self._outcome(candidate, StageRunStatus.FAILED, "SMT_COUNTEREXAMPLE",
                                 payload, diagnostics)
        run_status = (StageRunStatus.UNAVAILABLE if status in {"Timeout", "Unavailable"}
                      else StageRunStatus.INCONCLUSIVE)
        return self._outcome(candidate, run_status, "SMT_INCONCLUSIVE", payload,
                             ["SMT did not establish warning freedom", *notes])

    @staticmethod
    def _outcome(candidate: ArtifactEnvelope, run_status: StageRunStatus,
                 semantic_status: str, payload: dict[str, Any],
                 diagnostics: list[str]) -> StageExecution:
        report = ArtifactEnvelope(
            "smt-report", "v1", "smt_verification",
            ImplementationStatus.IMPLEMENTED_UNVALIDATED,
            AuthorityLevel.NO_AUTHORITY,
            {"contract_artifact_id": candidate.artifact_id, **payload},
        )
        return StageExecution(StageResult(
            "smt_verification", ImplementationStatus.IMPLEMENTED_UNVALIDATED,
            run_status, semantic_status=semantic_status,
            input_artifacts=[candidate.artifact_id], diagnostics=diagnostics,
            limitations=["SMT checks modeled Marlowe warnings, not business intent or ledger limits"],
        ), [report])
