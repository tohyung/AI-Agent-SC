"""One frozen case at a time through the supported pipeline, with labeled roleplay."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
import traceback
from typing import Any

from research.orchestration.cli_runner import SessionOptions, run_session
from research.experiments.online_tuning import DATASET, load_batch
from research.ledger.marlowe_cli import config_from_environment
from research.adapters.model_replay import (FactDraftReplayModel, FirstCoreReplayModel,
                                                JournaledModel, SavedContractReplayModel)
from research.adapters.model_transport import ModelTransport
from research.formalization.intent_spec import CORE_SCHEMA_VERSION_V3, CORE_SCHEMA_VERSION_V4
from research.formalization.repair_policy import REPAIR_POLICY_VERSION


ROOT = Path(__file__).resolve().parents[2]
RUN_DIR = ROOT / "runs" / "E3-Roleplay-Batch20"
REMAINING_RUN_DIR = ROOT / "runs" / "E3-Roleplay-Batch80"
E6_RUN_DIR = ROOT / "runs" / "E6-Pipeline"
DATASETS = ("v2", "v3", "v4")
# E7: dataset v4 runs into its own directory, set by --run-dir.
# Secondary providers are chosen only by explicit argument (see ModelTransport).
PROVIDERS = ("default", "gemini")
# Free-tier Gemini allows about 15 requests per minute; space requests so a
# per-minute 429 does not end a case attempt as provider_limit.
MIN_REQUEST_INTERVAL_SECONDS = {"default": 0.0, "gemini": 5.0}
_last_request_at: dict[str, float] = {}


def _pace(provider: str) -> None:
    interval = MIN_REQUEST_INTERVAL_SECONDS[provider]
    last = _last_request_at.get(provider)
    if interval and last is not None:
        wait = interval - (time.monotonic() - last)
        if wait > 0:
            time.sleep(wait)
    _last_request_at[provider] = time.monotonic()


def _case_at(index: int, dataset: str = "v2") -> dict[str, Any]:
    if dataset in {"v3", "v4"}:
        # E6/E7: the pipeline arm sees the same fields as the baseline arm (id, prompt, language).
        from research.experiments.baseline_llm import load_case

        return load_case(index, dataset)
    if dataset != "v2":
        raise ValueError(f"dataset must be one of {', '.join(DATASETS)}")
    _, first_cases = load_batch()
    if 1 <= index <= len(first_cases):
        return first_cases[index - 1]
    if not 21 <= index <= 100:
        raise ValueError("case index outside frozen 100-case dataset")
    with DATASET.open(encoding="utf-8") as source:
        cases = [json.loads(line) for line in source]
    if (len(cases) != 100 or cases[:len(first_cases)] != first_cases
            or len({case.get("id") for case in cases}) != 100):
        raise ValueError("frozen 100-case dataset identity is invalid")
    return cases[index - 1]


def _write_exclusive(path: Path, payload: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as writer:
        json.dump(payload, writer, ensure_ascii=False, indent=2)
        writer.write("\n")
        writer.flush()
        os.fsync(writer.fileno())


def _latest(case_dir: Path) -> dict[str, Any] | None:
    paths = sorted(case_dir.glob("attempt-*.json"))
    return json.loads(paths[-1].read_text(encoding="utf-8")) if paths else None


def _next_attempt(case_dir: Path) -> int:
    used = {int(path.stem.removeprefix("attempt-"))
            for path in case_dir.glob("attempt-*.json")}
    journal = case_dir / "outbound-attempts.jsonl"
    if journal.exists():
        for line in journal.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            attempt = record.get("attempt")
            if type(attempt) is not int or attempt < 1:
                raise ValueError("invalid outbound attempt journal")
            used.add(attempt)
    return max(used, default=0) + 1


def _repair_stalled(case_dir: Path, history: list[dict[str, Any]]) -> bool:
    comparable = []
    for path in sorted(case_dir.glob("attempt-*.json"), reverse=True):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("stop_reason") == "repair_stalled":
            continue
        if record.get("requirement_history") != history:
            break
        if record.get("stop_reason") != "invalid_candidate":
            break
        telemetry = (record.get("steps", {}).get("intent_extraction", {})
                     .get("telemetry"))
        if (not isinstance(telemetry, dict)
                or telemetry.get("repair_policy_version") != REPAIR_POLICY_VERSION):
            break
        comparable.append(telemetry)
        if len(comparable) == 2:
            break
    if len(comparable) < 2:
        return False
    recent, older = comparable
    return (bool(recent.get("final_error_codes"))
            and recent.get("final_error_codes") == older.get("final_error_codes")
            and type(recent.get("final_error_count")) is int
            and type(older.get("final_error_count")) is int
            and recent["final_error_count"] >= older["final_error_count"])


def _source_transcript(history: list[dict[str, Any]] | None,
                       transcript: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    messages = [message for revision in (history or [])[1:]
                for message in revision["messages"]]
    remaining = list(transcript or [])
    source: list[dict[str, Any]] = []
    for message in messages:
        match = next((index for index, item in enumerate(remaining)
                      if isinstance(item, dict) and item.get("answer") == message
                      and item.get("synthetic_assumption") is True), None)
        if match is None:
            raise ValueError("stored roleplay answer missing from source transcript")
        source.append(remaining.pop(match))
    return source


def _reusable_core(case_dir: Path, history: list[dict[str, Any]], *,
                   candidate_id: str | None = None,
                   require_policy_version: str | None = None) -> tuple[dict, str, list[str]] | None:
    for path in sorted(case_dir.glob("attempt-*.json"), reverse=True):
        record = json.loads(path.read_text(encoding="utf-8"))
        candidate = record.get("candidate")
        core = candidate.get("semantic_core") if isinstance(candidate, dict) else None
        if (not isinstance(core, dict)
                or core.get("schema_version") not in {CORE_SCHEMA_VERSION_V3,
                                                       CORE_SCHEMA_VERSION_V4}
                or core.get("requirement_history") != history):
            continue
        ids = (record.get("steps", {}).get("intent_extraction", {})
               .get("output_artifacts", []))
        if candidate_id is not None and ids != [candidate_id]:
            continue
        if (require_policy_version is not None and
                (record.get("steps", {}).get("intent_extraction", {}).get(
                    "telemetry", {}).get("repair_policy_version") != require_policy_version
                 or record.get("replayed_core_candidate_id") in ids)):
            continue
        if len(ids) != 1 or record.get("artifacts", {}).get(ids[0], {}).get("payload") != candidate:
            raise ValueError("stored candidate artifact differs from replay payload")
        initial_errors = candidate.get("initial_core_validation_errors")
        if (not isinstance(initial_errors, list)
                or any(not isinstance(item, str) for item in initial_errors)):
            raise ValueError("stored candidate has invalid initial errors")
        if candidate.get("formalization_method") == "AFF":
            drafts = candidate.get("fact_drafts")
            if (not isinstance(drafts, list) or not drafts
                    or drafts[-1].get("problems") != []
                    or any(not isinstance(item.get("draft"), dict) for item in drafts)):
                raise ValueError("stored AFF candidate has no accepted FactDraft to replay")
            return {"fact_drafts": [item["draft"] for item in drafts]}, ids[0], initial_errors
        return core, ids[0], initial_errors
    return None


def _reusable_contract(case_dir: Path, contract_id: str,
                       reviewed_candidate_id: str) -> tuple[dict, str]:
    for path in sorted(case_dir.glob("attempt-*.json"), reverse=True):
        record = json.loads(path.read_text(encoding="utf-8"))
        if (record.get("steps", {}).get("intent_extraction", {})
                .get("output_artifacts") != [reviewed_candidate_id]):
            continue
        successful = [item for item in record.get("execution_history", [])
                      if item.get("step") == "compile"
                      and item.get("run_status") == "SUCCEEDED"
                      and item.get("output_artifacts") == [contract_id]]
        artifact = record.get("artifacts", {}).get(contract_id)
        accepted_ids = (record.get("steps", {}).get("intent_acceptance", {})
                        .get("output_artifacts", []))
        if not successful or not isinstance(artifact, dict) or len(accepted_ids) != 1:
            continue
        payload = artifact.get("payload")
        if (artifact.get("artifact_type") != "contract-candidate"
                or not isinstance(payload, dict)
                or payload.get("source_intent_id") != accepted_ids[0]
                or not isinstance(payload.get("mapping_evidence"), list)):
            raise ValueError("stored contract artifact fails provenance check")
        return {"contract": payload["contract"],
                "mapping_evidence": payload["mapping_evidence"],
                "reasoning_narrative": payload.get("reasoning_narrative", "")}, accepted_ids[0]
    raise ValueError("contract artifact is not stored for this reviewed intent")


def run_case(index: int, *, answers: list[str] | None = None,
             reviewed_candidate_id: str | None = None,
             repair_candidate_id: str | None = None,
             replay_contract_id: str | None = None,
             expectation: dict[str, Any] | None = None,
             revision: str | None = None,
             revision_question: str | None = None,
             repair_attempts: int = 0,
             run_dir: Path | None = None,
             provider: str = "default",
             formalization: str = "DCF",
             dataset: str = "v2") -> dict[str, Any]:
    if provider not in PROVIDERS:
        raise ValueError(f"provider must be one of {', '.join(PROVIDERS)}")
    if dataset in {"v3", "v4"} and formalization != "AFF":
        raise ValueError("E6 runs dataset v3 on the AFF main path only")
    case = _case_at(index, dataset)
    if run_dir is None:
        run_dir = (E6_RUN_DIR if dataset in {"v3", "v4"}
                   else RUN_DIR if index <= 20 else REMAINING_RUN_DIR)
    if answers is not None and (not isinstance(answers, list)
                                or any(not isinstance(item, str) or not item.strip()
                                       for item in answers)):
        raise ValueError("roleplay answers must be nonempty natural-language strings")
    if type(repair_attempts) is not int or not 0 <= repair_attempts <= 3:
        raise ValueError("repair_attempts must be 0 through 3")
    if replay_contract_id is not None and reviewed_candidate_id is None:
        raise ValueError("contract replay requires an exact reviewed intent candidate")
    if repair_candidate_id is not None and reviewed_candidate_id is not None:
        raise ValueError("a candidate cannot be reviewed and repaired in the same run")
    if repair_candidate_id is not None and repair_attempts == 0:
        raise ValueError("candidate repair requires at least one validation repair")
    case_dir = run_dir / (f"case-{index:03d}" if dataset in {"v3", "v4"} else f"case-{index:02d}")
    case_dir.mkdir(parents=True, exist_ok=True)
    previous = _latest(case_dir)
    if previous is not None and previous.get("case_id") != case["id"]:
        raise ValueError("prior evidence belongs to another frozen case")
    history = previous.get("requirement_history") if previous else None
    transcript = (_source_transcript(history, previous.get("simulation_transcript"))
                  if previous else None)
    if revision is not None:
        if not revision.strip() or reviewed_candidate_id is not None:
            raise ValueError("roleplay revision must be nonempty and cannot review an old candidate")
        history = list(history or [{"version": 1, "messages": [case["prompt"]]}])
        transcript = list(transcript or [])
        if any(revision in item["messages"] for item in history):
            raise ValueError("roleplay revision already exists in requirement history")
        history.append({"version": len(history) + 1, "messages": [revision]})
        transcript.append({
            # E7: the question the user actually answered, when the driver gives it.
            "question": (revision_question.strip() if revision_question and revision_question.strip()
                         else "Xin bổ sung các dữ kiện nghiệp vụ còn thiếu cho hợp đồng này."),
            "answer": revision, "synthetic_assumption": True,
        })
    selected_candidate_id = reviewed_candidate_id or repair_candidate_id
    replay = _reusable_core(case_dir, history or [
        {"version": 1, "messages": [case["prompt"]]}],
        candidate_id=selected_candidate_id,
        require_policy_version=(REPAIR_POLICY_VERSION
                                if selected_candidate_id is None else None))
    if selected_candidate_id is not None and replay is None:
        raise ValueError("selected candidate is not stored for this requirement history")
    contract_replay = (_reusable_contract(case_dir, replay_contract_id,
                                          reviewed_candidate_id)
                       if replay_contract_id is not None and reviewed_candidate_id is not None
                       else None)
    attempt = _next_attempt(case_dir)
    evidence_path = case_dir / f"attempt-{attempt:03d}.json"
    physical_journal = case_dir / "outbound-attempts.jsonl"
    if (reviewed_candidate_id is None and revision is None
            and _repair_stalled(case_dir, history or [
                {"version": 1, "messages": [case["prompt"]]}])):
        payload = {
            "case_id": case["id"], "case_index": index, "attempt": attempt,
            "simulation_only": True, "status": "BLOCKED",
            "stop_reason": "repair_stalled", "provider_limit": False,
            "requirement_history": history,
            "simulation_transcript": transcript or [],
            "roleplay_answers_supplied": [], "roleplay_revision": None,
            "replayed_core_candidate_id": None,
            "replayed_contract_candidate_id": None,
            "repair_attempts": repair_attempts,
            "model_usage_this_attempt": {"api_calls": 0, "prompt_tokens": 0,
                                         "completion_tokens": 0, "total_tokens": 0},
            "model_call_log_this_attempt": [], "harness_error_type": None,
            "case_physical_calls_total": (
                len(physical_journal.read_text(encoding="utf-8").splitlines())
                if physical_journal.exists() else 0),
            "harness_error_locations": [], "iterations": 0,
            "questions": [], "steps": {}, "artifacts": {},
            "candidate": None, "contract_candidate": None,
            "blocking_step": "intent_extraction",
            "blocking_diagnostics": [
                "same Formalization error categories did not improve across two attempts; "
                "revise the repair strategy or clarify the requirement before another call"],
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        _write_exclusive(evidence_path, payload)
        print(f"case {index:02d}: BLOCKED repair_stalled; new physical calls=0; "
              f"evidence={evidence_path}", flush=True)
        return payload

    def before_request(phase: str) -> None:
        _pace(provider)
        with physical_journal.open("a", encoding="utf-8") as writer:
            writer.write(json.dumps({
                "case_id": case["id"], "attempt": attempt, "phase": phase,
                "provider": provider,
                "reserved_at_utc": datetime.now(timezone.utc).isoformat(),
            }, ensure_ascii=False) + "\n")
            writer.flush()
            os.fsync(writer.fileno())

    transport = ModelTransport(before_request=before_request, api_style="chat",
                               max_tokens=16000, disable_reasoning=True,
                               retry_empty=False, request_json_object=False,
                               provider=None if provider == "default" else provider)
    journaled = JournaledModel(transport, case_dir / "logical-model-outputs.jsonl")
    replayed_model = (SavedContractReplayModel(journaled, contract_replay[1],
                                               contract_replay[0])
                      if contract_replay else journaled)
    if replay is None:
        model = replayed_model
    elif "fact_drafts" in replay[0]:
        model = FactDraftReplayModel(replayed_model, replay[0]["fact_drafts"])
    else:
        model = FirstCoreReplayModel(replayed_model, replay[0], replay[2])
    queued = iter(answers or [])
    asked: list[dict[str, str]] = []

    def answer(question: str) -> str:
        response = next(queued, "")
        asked.append({"question": question.strip(), "answer": response})
        return response

    snapshot: dict[str, Any] | None = None
    error_type = None
    error_locations: list[str] = []
    try:
        snapshot = run_session(
            case["prompt"], model,
            options=SessionOptions(
                roleplay=True, max_llm_calls=99999,
                reference_binary=os.getenv("MARLOWE_REFERENCE_BINARY"),
                smt_binary=os.getenv("MARLOWE_SMT_BIN"),
                ledger_config=config_from_environment(),
                simulated_expectation=expectation,
                roleplay_reviewed_candidate_id=reviewed_candidate_id,
                max_core_validation_repairs=repair_attempts,
                property_dataset_path="runs/property-dataset.sqlite3",
                formalization_method=formalization,
            ),
            ask=answer,
            emit=lambda message: print(message, flush=True) if message.startswith(
                ("Lượt ", "Đang chạy:", "AST chưa", "Ratification/3:", "Synthesis-5:")) else None,
            initial_history=history,
            simulation_transcript=transcript,
        )
    except Exception as exc:
        error_type = type(exc).__name__
        error_locations = [f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}"
                           for frame in traceback.extract_tb(exc.__traceback__)]
    payload = {
        "case_id": case["id"], "case_index": index, "attempt": attempt,
        "simulation_only": True,
        "model_provider": provider,
        "model_name": getattr(transport, "model", None),
        "roleplay_answers_supplied": asked,
        "roleplay_revision": revision,
        "reviewed_candidate_id": reviewed_candidate_id,
        "simulated_expectation": expectation,
        "replayed_core_candidate_id": replay[1] if replay else None,
        "replayed_contract_candidate_id": replay_contract_id,
        "repair_attempts": repair_attempts,
        "model_usage_this_attempt": transport.usage_summary(),
        "model_call_log_this_attempt": transport.call_log,
        "case_physical_calls_total": (
            len(physical_journal.read_text(encoding="utf-8").splitlines())
            if physical_journal.exists() else 0),
        "harness_error_type": error_type,
        "harness_error_locations": error_locations,
        **(snapshot or {"status": "HARNESS_ERROR", "requirement_history": history or [
            {"version": 1, "messages": [case["prompt"]]}],
            "simulation_transcript": transcript or []}),
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    payload["provider_limit"] = any(
        (step.get("safe_error") or {}).get("code") == "provider_limit"
        for step in payload.get("steps", {}).values())
    _write_exclusive(evidence_path, payload)
    print(f"case {index:02d}: {payload['status']}; new physical calls="
          f"{transport.llm_calls}; evidence={evidence_path}", flush=True)
    if error_type:
        raise RuntimeError(f"harness error {error_type}; evidence={evidence_path}")
    return payload


def main() -> int:
    if os.name == "nt":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Run one frozen case through the main pipeline")
    parser.add_argument("--case-index", type=int, required=True)
    parser.add_argument("--answers-file", type=Path)
    parser.add_argument("--revision-file", type=Path)
    parser.add_argument("--revision-question-file", type=Path,
                        help="the question the revision answers (E7)")
    parser.add_argument("--review-candidate-id")
    parser.add_argument("--repair-candidate-id")
    parser.add_argument("--replay-contract-id")
    parser.add_argument("--expectation-file", type=Path)
    parser.add_argument("--repair-attempts", type=int, default=0)
    parser.add_argument("--provider", choices=PROVIDERS, default="default",
                        help="default = the LLM_* model; gemini = the GEMINI_* model")
    parser.add_argument("--formalization", choices=["DCF", "AFF"], default="DCF",
                        help="DCF reproduces the E3 runs; AFF is the main path since E4")
    parser.add_argument("--dataset", choices=DATASETS, default="v2",
                        help="v2 = the E3 dataset; v3 = the E6 dataset; v4 = the E7 dataset (AFF only)")
    parser.add_argument("--run-dir", type=Path,
                        help="evidence directory (default: the E3 batch directory)")
    args = parser.parse_args()
    answers = json.loads(args.answers_file.read_text(encoding="utf-8")) if args.answers_file else []
    expectation = (json.loads(args.expectation_file.read_text(encoding="utf-8"))
                   if args.expectation_file else None)
    revision = args.revision_file.read_text(encoding="utf-8").strip() if args.revision_file else None
    question = (args.revision_question_file.read_text(encoding="utf-8")
                if args.revision_question_file else None)
    result = run_case(args.case_index, answers=answers,
                      reviewed_candidate_id=args.review_candidate_id,
                      repair_candidate_id=args.repair_candidate_id,
                      replay_contract_id=args.replay_contract_id,
                      expectation=expectation,
                      revision=revision, revision_question=question,
                      repair_attempts=args.repair_attempts,
                      run_dir=args.run_dir, provider=args.provider,
                      formalization=args.formalization, dataset=args.dataset)
    return 3 if result["provider_limit"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
