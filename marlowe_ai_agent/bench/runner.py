"""Case execution, append-only results, cooperative limits and budget guard."""

from __future__ import annotations

import hashlib
import json
import random
import re
import subprocess
import traceback
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

from marlowe_agent.marlowe_ast import walk_contract
from marlowe_agent.models import ContractDraft, PartySpec, VerificationResult
from marlowe_agent.nodes import AgentPipeline
from marlowe_agent.openai_reasoner import OpenAIReasoner

from .config import DATASET
from .evaluator import evaluate
from .judge import judge
from .narrator import narrate
from .user_sim import SimulatedUser


class BenchTimeout(RuntimeError):
    pass


class CapturedReasoner:
    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.last_draft: ContractDraft | None = None

    def draft_from_prompt(self, prompt: str) -> ContractDraft:
        self.last_draft = self.inner.draft_from_prompt(prompt)
        return self.last_draft

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


class FakeBenchReasoner:
    def __init__(self, case: Any, wrong: bool = False) -> None:
        self.case = case
        self.wrong = wrong
        self.calls: list[str] = []
        self.llm_calls = 0
        self.call_log: list[dict[str, Any]] = []
        self.model = "fake"
        self.base_url = None

    def set_call_budget(self, limit: int | None) -> None:
        self.limit = limit
        self.llm_calls = 0

    def draft_from_prompt(self, prompt: str) -> ContractDraft:
        self.llm_calls += 1
        contract = deepcopy(self.case.reference_contract)
        if self.wrong:
            def double_amounts(node: Any) -> None:
                if isinstance(node, dict):
                    for key, value in node.items():
                        if key in {"deposits", "pay"} and type(value) is int:
                            node[key] = value * 2
                        else:
                            double_amounts(value)
                elif isinstance(node, list):
                    for item in node:
                        double_amounts(item)

            double_amounts(contract)
        names = self.case.params["roles"]
        return ContractDraft(prompt, self.case.type,
                             [PartySpec(key, name) for key, name in names.items()],
                             self.case.params["amount"] if names else None,
                             marlowe_contract=contract)

    def semantic_verify(self, prompt: str, draft: ContractDraft) -> VerificationResult:
        self.llm_calls += 1
        return VerificationResult(True, 1.0, [])

    def logic_feedback_to_clarification(self, prompt: str, draft: ContractDraft, logic: Any) -> dict[str, Any]:
        self.llm_calls += 1
        return {"needs_user_input": False, "questions": [], "internal_instruction": "Try again"}

    def usage_summary(self) -> dict[str, Any]:
        return {"calls": 0, "latency_seconds": 0.0, "prompt_tokens": 0,
                "completion_tokens": 0, "cost": 0.0}


def _redact(value: Any) -> Any:
    if isinstance(value, str):
        value = re.sub(r"\b(?:sk|or)-[A-Za-z0-9_-]{8,}\b", "[REDACTED]", value)
        value = re.sub(r"(?i)(api[_-]?key\s*[=:]\s*)[^\s,;]+", r"\1[REDACTED]", value)
        return value
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, dict):
        return {key: _redact(item) for key, item in value.items()}
    return value


def _usage(reasoners: list[Any], prices: tuple[float | None, float | None]) -> dict[str, Any]:
    logs = [row for reasoner in reasoners if reasoner is not None for row in reasoner.call_log]
    prompt = sum(row["prompt_tokens"] or 0 for row in logs)
    completion = sum(row["completion_tokens"] or 0 for row in logs)
    reported = [row["cost"] for row in logs if row["cost"] is not None]
    if len(reported) == len(logs) and logs:
        cost, source = sum(reported), "provider"
    elif all(price is not None for price in prices) and all(
            row["prompt_tokens"] is not None and row["completion_tokens"] is not None for row in logs):
        cost = (prompt * prices[0] + completion * prices[1]) / 1_000_000
        source = "estimated_from_config"
    else:
        cost, source = None, "unknown"
    return {"llm_calls": len(logs), "prompt_tokens": prompt, "completion_tokens": completion,
            "llm_seconds": sum(row["latency_seconds"] for row in logs),
            "cost_usd": cost, "cost_source": source, "call_log": logs}


def _complexity(contract: Any) -> dict[str, Any]:
    nodes = walk_contract(contract) if contract else []
    kinds = ["close" if node == "close" else next(iter(node), "unknown")
             for _, node in nodes if node == "close" or isinstance(node, dict)]
    return {"ast_nodes": len(nodes), "depth": max((path.count(".then") + path.count(".when")
                                                     for path, _ in nodes), default=0),
            "when_count": kinds.count("when"),
            "case_count": sum(len(node["when"]) for _, node in nodes if isinstance(node, dict) and "when" in node),
            "path_count": sum(node == "close" for _, node in nodes),
            "party_count": len({n["role_token"] for _, node in nodes if isinstance(node, dict)
                                for n in [node] if "role_token" in n}),
            "constructors": sorted(set(kinds))}


def _history(trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for event in trace:
        if event["node"] == "pipeline" and event["status"] == "iteration":
            result.append(event["data"].copy())
    return result


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def run_case(case: Any, *, model: str | None = None, judge_model: str | None = None,
             user_model: str | None = None, max_iterations: int = 30, max_llm_calls: int = 250,
             wall_clock: float = 900, attempt: int = 1, fake: bool = False,
             fake_wrong: bool = False, dataset_sha256: str = "", workers: int = 1,
             prices: tuple[float | None, float | None] = (None, None),
             timing_probe: bool = False) -> dict[str, Any]:
    started = perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()
    agent = user_reasoner = judge_reasoner = None
    captured = pipeline = simulated = None
    result = None
    stop_reason = "harness_error"
    error = None
    try:
        agent = FakeBenchReasoner(case, fake_wrong) if fake else OpenAIReasoner(model=model)
        captured = CapturedReasoner(agent)
        if not fake:
            user_reasoner = OpenAIReasoner(model=user_model or judge_model or model)
            if not timing_probe:
                judge_reasoner = OpenAIReasoner(model=judge_model or model)
        simulated = SimulatedUser(case, user_reasoner)

        def trace_callback(_event: Any) -> None:
            if perf_counter() - started > wall_clock:
                raise BenchTimeout("case wall-clock limit")

        pipeline = AgentPipeline(captured, interactive=True, max_iterations=max_iterations,
                                 max_llm_calls=max_llm_calls, answer_provider=simulated.answer,
                                 trace_callback=trace_callback)
        result = pipeline.run(case.prompt)
        stop_reason = result.stop_reason
    except BenchTimeout:
        stop_reason = "wallclock_timeout"
    except KeyboardInterrupt:
        stop_reason = "interrupted"
    except Exception:
        error = _redact(traceback.format_exc(limit=8))
    agent_wall = perf_counter() - started
    draft = result.draft if result else (captured.last_draft if captured else None)
    contract = draft.marlowe_contract if draft else None
    status = result.status if result else "blocked"
    try:
        evaluation = evaluate(case, contract, status) if contract else None
    except Exception:
        evaluation = None
        error = _redact(traceback.format_exc(limit=8))
    judgment = None
    if contract and not fake and judge_reasoner is not None:
        try:
            judgment = judge(case, contract, simulated.transcript if simulated else [], judge_reasoner)
        except Exception:
            judgment = {"error": _redact(traceback.format_exc(limit=5))}
    wall = perf_counter() - started
    usage = _usage([agent, user_reasoner, judge_reasoner], prices)
    agent_seconds = max(0.0, agent_wall - (simulated.seconds if simulated else 0.0))
    agent_llm_seconds = sum(row["latency_seconds"] for row in agent.call_log) if agent else 0.0
    trace = [event.to_dict() for event in pipeline.trace] if pipeline else []
    history = _history(trace)
    record = {
        "case_id": case.id, "attempt": attempt, "prompt": case.prompt,
        "run_kind": "timing_probe" if timing_probe else "benchmark",
        "language": case.language, "type": case.type, "difficulty": case.difficulty,
        "info_mode": case.info_mode, "challenges": case.challenges,
        "status": status, "stop_reason": stop_reason,
        "iterations": result.iterations if result else (pipeline._iteration_number if pipeline else 0),
        "converged": status == "done", "iteration_history": history,
        "convergence_path": " -> ".join("".join(k[0].upper() + ("+" if row.get(k) == "pass" else "-")
                                                  for k in ("structural", "semantic", "logic") if row.get(k) != "skip")
                                          for row in history),
        "semantic_history": [entry.to_dict() for entry in pipeline.semantic_history] if pipeline else [],
        "trace": trace, "qa_transcript": simulated.transcript if simulated else [],
        "contract": contract, "draft": draft.to_dict() if draft else None,
        "first_structural_pass_iter": next((row["iteration"] for row in history if row["structural"] == "pass"), None),
        "first_semantic_pass_iter": next((row["iteration"] for row in history if row["semantic"] == "pass"), None),
        "first_logic_pass_iter": next((row["iteration"] for row in history if row["logic"] == "pass"), None),
        "wall_seconds": wall, "agent_seconds": agent_seconds,
        "overhead_seconds": max(0.0, agent_seconds - agent_llm_seconds),
        "seconds_per_iteration": agent_seconds / max(1, len(history)),
        **usage,
        "agent_llm_calls": len(agent.call_log) if agent else 0,
        "user_llm_calls": len(user_reasoner.call_log) if user_reasoner else 0,
        "complexity": _complexity(contract), "evaluation": evaluation,
        "judge": judgment, "contract_description": narrate(contract) if contract else None,
        "self_reported_semantic_score": result.semantic_verification.score if result else None,
        "questions": len(simulated.transcript) if simulated else 0,
        "answers": sum(bool(item["answer"]) for item in simulated.transcript) if simulated else 0,
        "question_redundancy": "unknown" if judgment is None else judgment.get("redundant_questions", "unknown"),
        "git_commit": _git_commit(), "dataset_sha256": dataset_sha256,
        "model": model or getattr(agent, "model", None),
        "judge_model": judge_model, "user_model": user_model,
        "provider": getattr(agent, "base_url", None), "workers": workers,
        "limits": {"max_iterations": max_iterations, "max_llm_calls": max_llm_calls,
                   "wall_clock": wall_clock}, "started_at": started_at, "error": error,
    }
    return _redact(record)


def read_runs(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def run_many(cases: list[Any], directory: Path, *, workers: int = 3, seed: int = 1234,
             max_usd: float | None = None, attempt: int = 1,
             preserve_order: bool = False, **kwargs: Any) -> list[dict[str, Any]]:
    directory.mkdir(parents=True, exist_ok=True)
    file = directory / "runs.jsonl"
    existing = read_runs(file)
    completed = {(record["case_id"], record["attempt"]) for record in existing}
    queue = [case for case in cases if (case.id, attempt) not in completed]
    if not preserve_order:
        random.Random(seed).shuffle(queue)
    if existing and any(record.get("dataset_sha256") != kwargs.get("dataset_sha256") for record in existing):
        raise ValueError("Resume dataset hash mismatch")
    spent = sum(record.get("cost_usd") or 0 for record in existing)
    known_costs = [record["cost_usd"] for record in existing if record.get("cost_usd") is not None]
    with file.open("a", encoding="utf-8") as handle, ThreadPoolExecutor(max_workers=workers) as pool:
        futures: dict[Any, Any] = {}
        while queue or futures:
            while queue and len(futures) < workers:
                estimate = max(known_costs) if known_costs else 0.0
                if max_usd is not None and spent + estimate * (len(futures) + 1) >= max_usd:
                    queue.clear()
                    break
                case = queue.pop(0)
                future = pool.submit(run_case, case, workers=workers, attempt=attempt, **kwargs)
                futures[future] = case
            if not futures:
                break
            done, _ = wait(futures, return_when=FIRST_COMPLETED)
            for future in done:
                case = futures.pop(future)
                try:
                    record = future.result()
                except Exception:
                    record = {"case_id": case.id, "attempt": attempt, "status": "blocked",
                              "stop_reason": "harness_error", "error": _redact(traceback.format_exc(limit=8)),
                              "dataset_sha256": kwargs.get("dataset_sha256")}
                handle.write(json.dumps(_redact(record), ensure_ascii=False) + "\n")
                handle.flush()
                existing.append(record)
                if record.get("cost_usd") is not None:
                    spent += record["cost_usd"]
                    known_costs.append(record["cost_usd"])
    return existing


def dataset_hash(path: Path = DATASET) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
