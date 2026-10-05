"""Sequential Batch 01 extraction with a durable outbound-call journal."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import threading
from typing import Any
from contextlib import contextmanager

from marlowe_ai_agent.marlowe_agent.models import LLMBudgetError, LLMError, LLMTransientError
from marlowe_ai_agent.marlowe_agent.openai_reasoner import parse_json_text
from research.architecture.bootstrap import ResearchPipelineWiring, build_research_pipeline
from research.architecture.status import StageRunStatus
from research.experiments.batch_scenarios import (SyntheticExpectationPolicy,
                                                 scenario_from_intent)
from research.experiments.simulated_acceptance import SimulatedIntentAcceptancePort
from research.final_validation.marlowe_cli import (MarloweCliSizeAnalysisPort,
                                                   MarloweCliSizeConfig)
from research.stage2b.intent_spec import (CORE_SCHEMA_VERSION, CORE_SCHEMA_VERSION_V2,
                                          CORE_SCHEMA_VERSION_V3)
from research.stage2b.shadow_extractor import LegacyReasonerTransport
from research.stage3.comparison import SemanticComparisonPort
from research.stage3.profile_compilers.direct_payment_v1 import (
    DIRECT_PAYMENT_PROFILE, compile_direct_payment_v1,
)
from research.stage3.profile_compilers.funded_choice_v1 import (
    FUNDED_CHOICE_PROFILE, compile_funded_choice_v1,
)
from research.stage3.profile_compilers.funded_swap_v1 import (
    FUNDED_SWAP_PROFILE, compile_funded_swap_v1,
)
from research.stage3.profile_compilers.linear_time_release_v1 import (
    LINEAR_TIME_RELEASE_PROFILE, compile_linear_time_release_v1,
)
from research.stage3.profile_compilers.sequential_approval_v1 import (
    SEQUENTIAL_APPROVAL_PROFILE, compile_sequential_approval_v1,
)
from research.stage3.profiles import ProfileRegistry
from research.stage3.reference import PinnedMarloweReference
from research.stage4.explorer import ExplorationBounds, ExplorationPort
from research.stage4.oracles import NoWarningsOracle, OraclePort


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs/research/online-tuning-batch01.manifest.json"
BUDGET_EXTENSION = ROOT / "docs/research/online-tuning-batch01-budget-extension.json"
DATASET = ROOT / "marlowe_ai_agent/bench/dataset/cases.jsonl"
RUN_DIR = ROOT / "runs/online-tuning-batch01"
MODEL_REQUEST_WALL_SECONDS = 300
EXTRACTION_SOURCES = (ROOT / "research/stage2b/shadow_extractor.py",
                      ROOT / "research/stage2b/intent_spec.py",
                      ROOT / "research/stage2b/projector.py",
                      ROOT / "research/integrations/stage2b.py")


def extraction_source_sha256() -> str:
    digest = hashlib.sha256()
    for path in EXTRACTION_SOURCES:
        digest.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def write_json_exclusive(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as writer:
        json.dump(value, writer, ensure_ascii=False, indent=2)
        writer.write("\n")
        writer.flush()
        os.fsync(writer.fileno())


class CachedCoreModel:
    def __init__(self, core: dict) -> None:
        self.core = core

    def generate(self, system: str, user: str) -> dict:
        return self.core


class CompilerFeedbackModel:
    """Ask the model for a new core; never mutate the prior candidate."""

    def __init__(self, base: LegacyReasonerTransport, prior_core: dict,
                 diagnostics: list[str]) -> None:
        self.base = base
        self.prior_core = prior_core
        self.diagnostics = diagnostics

    def __getattr__(self, name: str) -> Any:
        return getattr(self.base, name)

    def generate(self, system: str, user: str) -> dict:
        feedback = (
            "\nPrevious core passed semantic-core and full structural validation, "
            "but the deterministic compiler rejected it. Regenerate the COMPLETE "
            "seven-field semantic core from requirement_history. Correct only "
            "source-grounded omissions or mappings shown below. Do not delete a "
            "real requirement, invent a business fact, change resolution merely "
            "to match a compiler profile, or edit the previous candidate in place. "
            "Re-evaluate every unscored observation against later explicit "
            "revisions and already represented scopes/claims; do not preserve "
            "a superseded uncertainty as unsupported behavior. A named actor's "
            "approval can be encoded as that actor's Choice without requiring "
            "the user to specify wallet-signature, oracle, or multisig mechanics "
            "unless such a mechanism is itself a business requirement. "
            "If a later absolute deadline resolves an earlier relative date, "
            "retain the actual deadline claims but drop the obsolete uncertainty "
            "observation. A statement that the contract does not submit its own "
            "transactions describes normal ledger operation, not an autonomous "
            "contract feature or a missing trigger for a time-based payment; "
            "do not turn it into an autonomous_execution claim or question. "
            "The result will be independently validated and compiled again.\n"
            "Compiler diagnostics:\n"
            + json.dumps(self.diagnostics, ensure_ascii=False)
            + "\nPrevious valid core:\n"
            + json.dumps(self.prior_core, ensure_ascii=False)
        )
        return self.base.generate(system, user + feedback)


def load_compiler_feedback(path: Path, *, case_id: str, history: list[dict],
                           core_schema_version: str) -> tuple[dict, list[str]]:
    from research.stage2b.intent_spec import validate_shadow_semantic_core

    if not path.resolve().is_relative_to(RUN_DIR.resolve()):
        raise ValueError("compiler feedback must be a Batch 01 evidence file")
    evidence = json.loads(path.read_text(encoding="utf-8"))
    candidate = evidence.get("candidate")
    stages = evidence.get("stages")
    core = candidate.get("semantic_core") if isinstance(candidate, dict) else None
    compile_stage = stages.get("compile") if isinstance(stages, dict) else None
    accepted = stages.get("intent_acceptance") if isinstance(stages, dict) else None
    diagnostics = compile_stage.get("diagnostics") if isinstance(compile_stage, dict) else None
    if (evidence.get("case_id") != case_id or evidence.get("requirement_history") != history
            or evidence.get("core_schema_version") != core_schema_version
            or not isinstance(core, dict)
            or candidate.get("core_validation_errors")
            or candidate.get("full_validation_errors")
            or validate_shadow_semantic_core(core, expected_history=history)
            or not isinstance(accepted, dict) or accepted.get("run_status") != "SUCCEEDED"
            or not isinstance(compile_stage, dict)
            or compile_stage.get("run_status") != "UNSUPPORTED"
            or not isinstance(diagnostics, list) or not diagnostics
            or not all(isinstance(item, str) for item in diagnostics)):
        raise ValueError("compiler feedback requires same-case valid core and unsupported compile")
    return core, diagnostics


def load_replay_core(path: Path, *, case_id: str, history: list[dict],
                     core_schema_version: str) -> dict:
    """Explicitly replay an unchanged valid core under newer downstream code."""
    from research.stage2b.intent_spec import validate_shadow_semantic_core

    if not path.resolve().is_relative_to(RUN_DIR.resolve()):
        raise ValueError("replay evidence must be a Batch 01 evidence file")
    evidence = json.loads(path.read_text(encoding="utf-8"))
    candidate = evidence.get("candidate")
    core = candidate.get("semantic_core") if isinstance(candidate, dict) else None
    if (evidence.get("case_id") != case_id
            or evidence.get("core_schema_version") != core_schema_version
            or evidence.get("requirement_history") != history
            or not isinstance(core, dict)
            or candidate.get("core_validation_errors")
            or candidate.get("full_validation_errors")
            or validate_shadow_semantic_core(core, expected_history=history)):
        raise ValueError("replay requires same-case valid core and unchanged history")
    return core


def load_batch() -> tuple[dict, list[dict]]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    digest = hashlib.sha256()
    with DATASET.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != manifest["dataset_sha256"]:
        raise ValueError("batch dataset SHA-256 differs from manifest")
    with DATASET.open(encoding="utf-8") as source:
        cases = [json.loads(next(source)) for _ in manifest["case_ids"]]
    if [case["id"] for case in cases] != manifest["case_ids"]:
        raise ValueError("first 20 physical case IDs differ from manifest")
    return manifest, cases


def physical_call_limit(manifest: dict, journal_path: Path) -> int:
    base = manifest["max_physical_model_calls"]
    if not BUDGET_EXTENSION.exists():
        return base
    extension = json.loads(BUDGET_EXTENSION.read_text(encoding="utf-8"))
    if (extension.get("batch_id") != manifest["batch_id"]
            or extension.get("original_limit") != base
            or extension.get("journal_baseline_attempts") != base
            or type(extension.get("additional_attempts")) is not int
            or not 0 < extension["additional_attempts"] <= 22):
        raise ValueError("invalid Batch 01 budget extension")
    if not journal_path.exists():
        return base
    lines = journal_path.read_text(encoding="utf-8").splitlines()
    if len(lines) < base:
        return base
    try:
        original_entries = [json.loads(line) for line in lines[:base]]
    except json.JSONDecodeError as exc:
        raise ValueError("budget extension requires a valid original journal") from exc
    canonical = json.dumps(original_entries, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False).encode("utf-8")
    if hashlib.sha256(canonical).hexdigest() != extension.get("journal_baseline_sha256"):
        raise ValueError("budget extension journal fingerprint mismatch")
    return base + extension["additional_attempts"]


def load_synthetic_input(path: Path) -> tuple[list[list[str]], list[dict]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(value, dict)
            or set(value) not in ({"answers", "simulation_transcript"},
                                  {"revisions", "simulation_transcript"})):
        raise ValueError("synthetic input must contain answers/revisions and transcript")
    revisions = value.get("revisions", [value["answers"]] if "answers" in value else None)
    if (not isinstance(revisions, list) or not revisions
            or any(not isinstance(messages, list) or not messages
                   or not all(isinstance(item, str) and item.strip() for item in messages)
                   for messages in revisions)
            or not isinstance(value["simulation_transcript"], list)):
        raise ValueError("synthetic input arrays are invalid")
    if any(key in json.dumps(value, ensure_ascii=False) for key in (
            '"reference_contract"', '"checks"')):
        raise ValueError("evaluator-only fields are forbidden in synthetic input")
    return revisions, value["simulation_transcript"]


def next_attempt_paths(index: int) -> tuple[int, Path, Path]:
    """Allocate a fresh evidence pair; never overwrite a previous attempt."""
    attempt = 1
    while True:
        stem = f"case-{index:02d}" + (f"-attempt-{attempt:02d}" if attempt > 1 else "")
        result = RUN_DIR / f"{stem}.json"
        extraction = RUN_DIR / f"{stem}-extraction.json"
        if not result.exists():
            return attempt, result, extraction
        attempt += 1


def reusable_extraction(index: int, before_attempt: int, case_id: str,
                        history: list[dict], core_schema_version: str) -> tuple[dict, Path] | None:
    from research.stage2b.intent_spec import validate_shadow_semantic_core

    for attempt in range(before_attempt - 1, 0, -1):
        stem = f"case-{index:02d}" + (f"-attempt-{attempt:02d}" if attempt > 1 else "")
        path = RUN_DIR / f"{stem}-extraction.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        core = data.get("semantic_core")
        if (data.get("case_id") == case_id
                and data.get("source_sha256") == extraction_source_sha256()
                and data.get("core_schema_version") == core_schema_version
                and isinstance(core, dict)
                and core.get("requirement_history") == history
                and not validate_shadow_semantic_core(core, expected_history=history)):
            return core, path
    return None


class PhysicalCallJournal:
    def __init__(self, path: Path, *, limit: int | None = None) -> None:
        self.path = path
        self.limit = limit
        if path.exists():
            self.entries = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        else:
            self.entries = []
        if any(entry.get("attempt") != index for index, entry in enumerate(self.entries, 1)):
            raise ValueError("physical-call journal has a gap or duplicate")
        if limit is not None and len(self.entries) > limit:
            raise ValueError("physical-call journal exceeds batch limit")

    @property
    def used(self) -> int:
        return len(self.entries)

    def consume(self, case_id: str) -> None:
        if self.limit is not None and self.used >= self.limit:
            raise LLMBudgetError("BATCH_MODEL_BUDGET_EXHAUSTED")
        entry = {"attempt": self.used + 1, "case_id": case_id,
                 "at_utc": datetime.now(timezone.utc).isoformat()}
        with self.path.open("a", encoding="utf-8") as writer:
            writer.write(json.dumps(entry, ensure_ascii=False) + "\n")
            writer.flush()
            os.fsync(writer.fileno())
        self.entries.append(entry)


class ProviderLimitReached(LLMError):
    """The provider reported a request or account limit (never its raw body)."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"OpenRouter limit response (HTTP {status_code})")


@contextmanager
def model_request_deadline(seconds: int):
    """Bound total provider wall time, which an HTTP read timeout does not bound."""
    if not hasattr(signal, "setitimer") or threading.current_thread() is not threading.main_thread():
        yield
        return
    if signal.getitimer(signal.ITIMER_REAL)[0] > 0:
        raise RuntimeError("batch request cannot override an existing process alarm")
    previous = signal.getsignal(signal.SIGALRM)

    def expired(_signum: int, _frame: Any) -> None:
        raise LLMTransientError("batch provider request exceeded wall-clock deadline")

    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def attach_global_budget(model: LegacyReasonerTransport, journal: PhysicalCallJournal,
                         case_id: str) -> None:
    reasoner = model.reasoner
    if not hasattr(reasoner.client, "with_options"):
        raise RuntimeError("provider SDK cannot disable hidden automatic retries")
    reasoner.client = reasoner.client.with_options(max_retries=0)
    reasoner.set_call_budget(journal.limit)
    reasoner.llm_calls = journal.used
    reasoner.max_tokens = 16000
    reasoner.api_style = "chat"

    def consume() -> None:
        journal.consume(case_id)
        reasoner.llm_calls = journal.used

    reasoner._consume_call = consume
    original_request = reasoner._request
    model.request_diagnostics = []
    model.provider_limit_status = None

    def observe_request(create: Any, **kwargs: Any) -> Any:
        if "messages" in kwargs:
            kwargs.pop("response_format", None)
            kwargs["extra_body"] = {**kwargs.get("extra_body", {}),
                                    "reasoning": {"enabled": False},
                                    "chat_template_kwargs": {"enable_thinking": False}}
        try:
            with model_request_deadline(MODEL_REQUEST_WALL_SECONDS):
                response = original_request(create, **kwargs)
        except Exception as exc:
            status_code = getattr(exc, "status_code", None)
            if status_code in (402, 429):
                model.provider_limit_status = status_code
                raise ProviderLimitReached(status_code) from None
            raise
        choices = getattr(response, "choices", None)
        usage = getattr(response, "usage", None)
        details = getattr(usage, "completion_tokens_details", None)
        model.request_diagnostics.append({
            "finish_reason": getattr(choices[0], "finish_reason", None) if choices else None,
            "reasoning_tokens": getattr(details, "reasoning_tokens", None),
        })
        return response

    reasoner._request = observe_request
    raw_response = reasoner._raw_response
    model.response_diagnostics = []

    def observe_response(system: str, user: str) -> str:
        content = raw_response(system, user)
        item: dict[str, Any] = {
            "characters": len(content),
            "starts_with_object": content.lstrip().startswith("{"),
            "ends_with_object": content.rstrip().endswith("}"),
        }
        try:
            parse_json_text(content)
            item["json_parse_status"] = "valid_object"
        except json.JSONDecodeError as exc:
            item["json_parse_status"] = "invalid"
            item["error_kind"] = exc.msg
            item["error_position"] = exc.pos
        model.response_diagnostics.append(item)
        return content

    reasoner._raw_response = observe_response


def batch_wiring() -> ResearchPipelineWiring:
    return ResearchPipelineWiring(
        intent_acceptance_port=SimulatedIntentAcceptancePort(),
        profile_registry=ProfileRegistry([DIRECT_PAYMENT_PROFILE, FUNDED_CHOICE_PROFILE,
                                          FUNDED_SWAP_PROFILE, LINEAR_TIME_RELEASE_PROFILE,
                                          SEQUENTIAL_APPROVAL_PROFILE]),
        compiler_plugins={
            (DIRECT_PAYMENT_PROFILE.profile_id, DIRECT_PAYMENT_PROFILE.version):
                compile_direct_payment_v1,
            (FUNDED_CHOICE_PROFILE.profile_id, FUNDED_CHOICE_PROFILE.version):
                compile_funded_choice_v1,
            (FUNDED_SWAP_PROFILE.profile_id, FUNDED_SWAP_PROFILE.version):
                compile_funded_swap_v1,
            (LINEAR_TIME_RELEASE_PROFILE.profile_id, LINEAR_TIME_RELEASE_PROFILE.version):
                compile_linear_time_release_v1,
            (SEQUENTIAL_APPROVAL_PROFILE.profile_id, SEQUENTIAL_APPROVAL_PROFILE.version):
                compile_sequential_approval_v1,
        },
    )


def configured_ledger() -> MarloweCliSizeConfig | None:
    names = ("MARLOWE_LEDGER_BINARY", "MARLOWE_LEDGER_NODE_CLI",
             "MARLOWE_LEDGER_SOCKET", "MARLOWE_LEDGER_TEMPLATE",
             "MARLOWE_LEDGER_BINARY_SHA256", "MARLOWE_LEDGER_SOURCE_COMMIT",
             "MARLOWE_LEDGER_TEMPLATE_SHA256", "MARLOWE_LEDGER_TESTNET_MAGIC")
    values = {name: os.getenv(name) for name in names}
    if not any(values.values()):
        return None
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ValueError(f"incomplete ledger configuration: {', '.join(missing)}")
    return MarloweCliSizeConfig(
        binary=Path(values["MARLOWE_LEDGER_BINARY"]),
        node_cli_binary=Path(values["MARLOWE_LEDGER_NODE_CLI"]),
        socket=Path(values["MARLOWE_LEDGER_SOCKET"]),
        initialized_template=Path(values["MARLOWE_LEDGER_TEMPLATE"]),
        expected_binary_sha256=values["MARLOWE_LEDGER_BINARY_SHA256"],
        source_commit=values["MARLOWE_LEDGER_SOURCE_COMMIT"],
        expected_template_sha256=values["MARLOWE_LEDGER_TEMPLATE_SHA256"],
        testnet_magic=int(values["MARLOWE_LEDGER_TESTNET_MAGIC"]),
    )


def configure_downstream(pipeline: Any, accepted: Any, profile_id: str, *,
                         reference_binary: str, ledger_config: MarloweCliSizeConfig) -> Any:
    scenario = scenario_from_intent(accepted, profile_id)
    reference = PinnedMarloweReference(binary=reference_binary, hard_timeout_seconds=15)
    pipeline.ports["semantic_comparison"] = SemanticComparisonPort(
        reference, SyntheticExpectationPolicy())
    pipeline.ports["exploration"] = ExplorationPort(
        scenario.domain, reference, scenario.initial_state,
        ExplorationBounds(max_depth=max(2, len(scenario.expectation.payload["request"]["transactions"])),
                          max_traces=8))
    pipeline.ports["oracle_evaluation"] = OraclePort([NoWarningsOracle()])
    pipeline.ports["ledger_validation"] = MarloweCliSizeAnalysisPort(ledger_config)
    return scenario.expectation


def run_one(index: int, *, core_schema_version: str = CORE_SCHEMA_VERSION,
            history: list[dict[str, Any]] | None = None,
            simulation_transcript: list[dict[str, Any]] | None = None,
            feedback_from: Path | None = None,
            replay_core_from: Path | None = None,
            reference_binary: str | None = None,
            ledger_config: MarloweCliSizeConfig | None = None) -> dict:
    manifest, cases = load_batch()
    if index < 1 or index > len(cases):
        raise ValueError("case index must be within the frozen batch")
    if core_schema_version not in {CORE_SCHEMA_VERSION, CORE_SCHEMA_VERSION_V2,
                                   CORE_SCHEMA_VERSION_V3}:
        raise ValueError("unsupported core schema version")
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    journal_path = RUN_DIR / "physical-attempts.jsonl"
    journal = PhysicalCallJournal(journal_path)
    if feedback_from is not None and replay_core_from is not None:
        raise ValueError("feedback and core replay are mutually exclusive")
    physical_calls_at_start = journal.used
    case = cases[index - 1]
    history = history or [{"version": 1, "messages": [case["prompt"]]}]
    if (not isinstance(history, list) or not history
            or history[0] != {"version": 1, "messages": [case["prompt"]]}):
        raise ValueError("batch requirement history must begin with the original prompt")
    attempt, result_path, extraction_path = next_attempt_paths(index)
    cached: dict[str, Any] | None = None
    cached_from: Path | None = None
    if replay_core_from is not None:
        cached = {"semantic_core": load_replay_core(
            replay_core_from, case_id=case["id"], history=history,
            core_schema_version=core_schema_version)}
        cached_from = replay_core_from
    elif extraction_path.exists():
        cached = json.loads(extraction_path.read_text(encoding="utf-8"))
        cached_from = extraction_path
        if cached.get("source_sha256") != extraction_source_sha256():
            raise ValueError("cached extraction invalidated by Stage 2B source change")
        if cached.get("core_schema_version", CORE_SCHEMA_VERSION) != core_schema_version:
            raise ValueError("cached extraction belongs to another schema version")
        if cached.get("case_id") != case["id"]:
            raise ValueError("cached extraction belongs to another case")
        if not isinstance(cached.get("semantic_core"), dict):
            raise ValueError("cached extraction has no reusable semantic core")
    else:
        prior = (None if feedback_from is not None else
                 reusable_extraction(index, attempt, case["id"], history,
                                     core_schema_version))
        if prior is not None:
            core, cached_from = prior
            cached = {"semantic_core": core}
    model = CachedCoreModel(cached["semantic_core"]) if cached else LegacyReasonerTransport(manifest["model"])
    if cached is None:
        attach_global_budget(model, journal, case["id"])
        if feedback_from is not None:
            prior_core, diagnostics = load_compiler_feedback(
                feedback_from, case_id=case["id"], history=history,
                core_schema_version=core_schema_version)
            model = CompilerFeedbackModel(model, prior_core, diagnostics)
    pipeline = build_research_pipeline(model=model, wiring=batch_wiring())
    max_core_validation_repairs = 3
    run = pipeline.run(history, stop_after="intent_extraction",
                       options={"max_core_validation_repairs": max_core_validation_repairs,
                                "core_schema_version": core_schema_version})
    extraction_stage = run.stages["intent_extraction"]
    candidate = next((pipeline.store.get(artifact_id).payload for artifact_id in
                      extraction_stage.output_artifacts
                      if pipeline.store.get(artifact_id).artifact_type == "intent-candidate"), None)
    if extraction_stage.run_status == StageRunStatus.SUCCEEDED and candidate is None:
        raise RuntimeError("successful extraction returned no intent candidate")
    if candidate is not None and cached is None:
        write_json_exclusive(extraction_path, {
            "case_id": case["id"], "source_sha256": extraction_source_sha256(),
            "core_schema_version": core_schema_version,
            "semantic_core": candidate["semantic_core"],
            "attempt_physical_calls": journal.used - physical_calls_at_start})
    execution_error = None
    if extraction_stage.run_status == StageRunStatus.SUCCEEDED:
        try:
            run = pipeline.run(history, resume=run, stop_after="compile", options={
                "simulation_transcript": simulation_transcript or [],
                "allow_simulated_intent": True,
            })
        except Exception as exc:
            execution_error = {"stage": "intent_acceptance_or_compile",
                               "exception_type": type(exc).__name__}
    compile_stage = run.stages.get("compile")
    if (execution_error is None and compile_stage is not None
            and compile_stage.run_status == StageRunStatus.SUCCEEDED):
        if reference_binary is None or ledger_config is None:
            execution_error = {"stage": "downstream_configuration",
                               "exception_type": "ReferenceOrLedgerNotConfigured"}
        else:
            try:
                accepted = next(pipeline.store.get(item) for item in
                                run.stages["intent_acceptance"].output_artifacts
                                if item.startswith("accepted-intent:"))
                contract = next(pipeline.store.get(item) for item in
                                compile_stage.output_artifacts
                                if item.startswith("contract-candidate:"))
                expectation = configure_downstream(
                    pipeline, accepted, contract.payload["profile"]["profile_id"],
                    reference_binary=reference_binary, ledger_config=ledger_config)
                run = pipeline.run(history, resume=run, stop_after="ledger_validation",
                                   external_artifacts=[expectation],
                                   invalidate_from="semantic_comparison")
            except Exception as exc:
                execution_error = {"stage": "reference_to_ledger",
                                   "exception_type": type(exc).__name__}
    stages = {name: {"run_status": stage.run_status.value,
                     "semantic_status": stage.semantic_status,
                     "diagnostics": stage.diagnostics,
                     "safe_error": stage.safe_error}
              for name, stage in run.stages.items()}
    evidence = {"index": index, "attempt": attempt, "case_id": case["id"],
                "core_schema_version": core_schema_version, "prompt": case["prompt"],
                "type": case["type"], "difficulty": case["difficulty"],
                "language": case["language"], "info_mode": case["info_mode"],
                "model": manifest["model"],
                "cached_extraction_from": str(cached_from) if cached_from else None,
                "replayed_core_from": str(replay_core_from) if replay_core_from else None,
                "compiler_feedback_from": str(feedback_from) if feedback_from else None,
                "model_usage": model.usage() if hasattr(model, "usage") else None,
                "response_diagnostics": getattr(model, "response_diagnostics", []),
                "request_diagnostics": getattr(model, "request_diagnostics", []),
                "provider_limit_status": getattr(model, "provider_limit_status", None),
                "physical_calls": journal.used - physical_calls_at_start,
                "max_core_validation_repairs": max_core_validation_repairs,
                "case_physical_calls_total": sum(entry["case_id"] == case["id"]
                                                 for entry in journal.entries),
                "cumulative_physical_calls": journal.used,
                "requirement_history": history,
                "simulation_transcript": simulation_transcript or [],
                "stages": stages,
                "candidate": candidate, "execution_error": execution_error,
                "ledger_outcome": "NOT_REACHED_LEDGER"}
    compile_stage = run.stages.get("compile")
    if compile_stage and compile_stage.run_status == StageRunStatus.SUCCEEDED:
        evidence["contract_candidate"] = next((pipeline.store.get(artifact_id).to_dict()
                                                for artifact_id in compile_stage.output_artifacts
                                                if artifact_id.startswith("contract-candidate:")), None)
    ledger_stage = run.stages.get("ledger_validation")
    if ledger_stage is not None and ledger_stage.output_artifacts:
        ledger_artifact = pipeline.store.get(ledger_stage.output_artifacts[0])
        evidence["ledger_outcome"] = ledger_stage.semantic_status
        evidence["ledger_evidence"] = ledger_artifact.to_dict()
    comparison_stage = run.stages.get("semantic_comparison")
    if comparison_stage is not None and comparison_stage.output_artifacts:
        evidence["comparison_evidence"] = pipeline.store.get(
            comparison_stage.output_artifacts[0]).to_dict()
    write_json_exclusive(result_path, evidence)
    return {"case_id": case["id"], "attempt": attempt,
            "core_schema_version": core_schema_version,
            "physical_calls": evidence["physical_calls"],
            "provider_limit_status": evidence["provider_limit_status"],
            "cumulative_physical_calls": journal.used, "stages": stages,
            "candidate_core_errors": len((candidate or {}).get("core_validation_errors", [])),
            "candidate_full_errors": len((candidate or {}).get("full_validation_errors", []))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-index", type=int, required=True)
    parser.add_argument("--core-schema-version", choices=(CORE_SCHEMA_VERSION,
                                                          CORE_SCHEMA_VERSION_V2,
                                                          CORE_SCHEMA_VERSION_V3),
                        default=CORE_SCHEMA_VERSION)
    parser.add_argument("--reference-binary", default=os.getenv("MARLOWE_REFERENCE_BINARY"))
    parser.add_argument("--synthetic-input", type=Path)
    parser.add_argument("--feedback-from", type=Path)
    parser.add_argument("--replay-core-from", type=Path)
    args = parser.parse_args()
    revisions, transcript = (load_synthetic_input(args.synthetic_input)
                             if args.synthetic_input else ([], None))
    _, cases = load_batch()
    history = ([{"version": 1, "messages": [cases[args.case_index - 1]["prompt"]]}]
               + [{"version": index, "messages": messages}
                  for index, messages in enumerate(revisions, 2)] if revisions else None)
    result = run_one(args.case_index, core_schema_version=args.core_schema_version,
                     history=history, simulation_transcript=transcript,
                     feedback_from=args.feedback_from,
                     replay_core_from=args.replay_core_from,
                     reference_binary=args.reference_binary,
                     ledger_config=configured_ledger())
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
