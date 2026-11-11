"""E6 baseline arm: a plain LLM that talks to the user and writes the Marlowe contract itself.

The model sees only the conversation. Every contract it writes is checked the way a user of a plain
chatbot would check it: structure validation, then the ledger transaction-size analysis. A failed
check is forwarded to the model automatically, as a user pasting the error back. When the model asks a
question, declines, or writes a contract that passes the checks, the run stops and waits for the
simulated user (`--message-file`, `--accept`, `--give-up`). The simulated user answers only from the
case's fact sheet and from what the model said; it never runs scenarios (docs/E6-Plan.md, decision 7).

Each case has its own request cap, equal to the requests the pipeline arm used on that case. A request
is any model call that got a response, error responses included; quota errors (429) and calls
that got no response are not counted.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
DATASET_V3 = ROOT / "dataset" / "v3" / "cases.jsonl"
# Dev cases 1-56 of dataset v2 are the only place the arm may be tried or tuned (E6-Plan, section 3).
DATASET_DEV = ROOT / "dataset" / "cases.jsonl"
DEV_CASES = 56
RUN_DIR = ROOT / "runs" / "E6-Baseline"
BASELINE_PROMPT_VERSION = "Baseline-Chat-v1"
PROVIDERS = ("default", "gemini")
MIN_REQUEST_INTERVAL_SECONDS = {"default": 0.0, "gemini": 5.0}

# Waiting states: the next move belongs to the simulated user.
AWAITING = {"question": "awaiting_answer", "decline": "awaiting_reaction",
            "contract": "awaiting_review"}
FINAL = {"accepted", "gave_up", "cap_reached"}
# No response reached us (quota, network): not a request; the run stops and is resumed later.
UNCOUNTED_FAILURES = {"provider_limit": "provider_limit",
                      "provider_request_failed": "provider_error"}


def _system_prompt() -> str:
    from research.analysis.marlowe_ast import prompt_contract_examples

    examples = json.dumps(prompt_contract_examples(), ensure_ascii=False, separators=(",", ":"))
    return f"""You are an assistant that writes Cardano Marlowe smart contracts for users.
You talk with the user, and when you have what you need you write the contract as Marlowe Core JSON
(the format marlowe-cli accepts).

Reply with exactly one JSON object, in one of these forms:
- {{"type": "question", "message": "<your questions to the user>"}} when facts you need are missing
  or unclear;
- {{"type": "contract", "message": "<plain-language explanation of what the contract does>",
   "contract": <Marlowe Core JSON>}} when you can write the contract;
- {{"type": "decline", "message": "<why>"}} when the request cannot be done as a Marlowe contract.
Write "message" in the user's language.

Marlowe Core JSON notes:
- times are POSIX milliseconds (UTC); amounts of ADA are in lovelace (1 ADA = 1 000 000 lovelace);
- ADA is {{"currency_symbol": "", "token_name": ""}}; parties are {{"role_token": "<name>"}};
- a contract is "close", a pay, a when, an if, a let or an assert, as in these examples:
{examples}"""


def load_case(index: int, dataset: str = "v3") -> dict[str, Any]:
    """Only the fields the arm may see: id, prompt and language (never the evaluator fields)."""
    if dataset not in {"v3", "dev"}:
        raise ValueError("dataset must be v3 or dev")
    with (DATASET_V3 if dataset == "v3" else DATASET_DEV).open(encoding="utf-8") as source:
        cases = [json.loads(line) for line in source]
    last = 100 if dataset == "v3" else DEV_CASES
    if len(cases) != 100 or not 1 <= index <= last:
        raise ValueError(f"case index outside {dataset} cases 1-{last}")
    case = cases[index - 1]
    return {"id": case["id"], "prompt": case["prompt"], "language": case["language"]}


def check_feedback(language: str, check: dict[str, Any]) -> str:
    """What the simulated user pastes back after a failed check: only the tool's own messages."""
    lines = "\n".join(f"- {item}" for item in check["messages"][:20])
    if check["stage"] == "format":
        head = ("Câu trả lời không đúng định dạng JSON đã yêu cầu:" if language == "vi"
                else "Your reply was not in the requested JSON format:")
    elif check["stage"] == "structure":
        head = ("Công cụ kiểm tra báo hợp đồng không hợp lệ:" if language == "vi"
                else "The checker says the contract is not valid:")
    else:
        head = ("Kiểm tra trên ledger không qua:" if language == "vi"
                else "The ledger check failed:")
    tail = "Sửa lại giúp mình." if language == "vi" else "Please fix it."
    return f"{head}\n{lines}\n{tail}"


class LedgerUnavailable(RuntimeError):
    """The ledger infrastructure, not the contract, failed; the case is resumed later."""


def make_checker(ledger_config: Any | None) -> Callable[[Any], dict[str, Any]]:
    """Structure validation, then ledger size analysis. `ledger_config=None` skips the ledger
    (dev smoke runs only; E6 runs require the ledger)."""
    from research.analysis.marlowe_validator import validate_contract

    def check(contract: Any) -> dict[str, Any]:
        errors = validate_contract(contract)
        if errors:
            return {"passed": False, "stage": "structure", "messages": errors}
        if ledger_config is None:
            return {"passed": True, "stage": "structure", "messages": [],
                    "ledger": "not_configured"}
        from research.ledger.marlowe_cli import MarloweCliSizeAnalysisPort
        from research.orchestration.artifacts import ArtifactEnvelope
        from research.orchestration.ports import StepContext
        from research.orchestration.status import (AuthorityLevel, ImplementationStatus,
                                                   StepRunStatus)

        envelope = ArtifactEnvelope("contract-candidate", "v1", "baseline",
                                    ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                                    AuthorityLevel.MODEL_CANDIDATE,
                                    {"contract": contract, "simulation_only": True})
        execution = MarloweCliSizeAnalysisPort(ledger_config).execute([envelope], StepContext("e6-baseline"))
        status = execution.result.run_status
        evidence = execution.artifacts[0].payload if execution.artifacts else {}
        evidence = json.loads(json.dumps(evidence, default=str))
        if status == StepRunStatus.UNAVAILABLE:
            raise LedgerUnavailable("; ".join(execution.result.diagnostics))
        # INCONCLUSIVE means the analyzer found no transaction to size: no error reaches the user.
        return {"passed": status != StepRunStatus.FAILED, "stage": "ledger",
                "messages": list(execution.result.diagnostics),
                "ledger": execution.result.semantic_status, "ledger_evidence": evidence}

    return check


def _render(transcript: list[dict[str, Any]]) -> str:
    lines = []
    for turn in transcript:
        if turn["role"] == "user":
            lines.append(f"USER: {turn['content']}")
        else:
            lines.append("ASSISTANT: " + json.dumps(turn["reply"], ensure_ascii=False))
    return ("Conversation so far:\n" + "\n\n".join(lines)
            + "\n\nWrite your next reply as one JSON object.")


def _parse_reply(reply: Any) -> tuple[str | None, list[str]]:
    if not isinstance(reply, dict):
        return None, ["the reply is not a JSON object"]
    kind = reply.get("type")
    if kind not in AWAITING:
        return None, ['"type" must be "question", "contract" or "decline"']
    if not isinstance(reply.get("message"), str) or not reply["message"].strip():
        return None, ['"message" must be a nonempty string']
    if kind == "contract" and "contract" not in reply:
        return None, ['a reply of type "contract" needs a "contract" field']
    return kind, []


# Transport exceptions that carry no model response; quota is a 402/429 provider code.
NO_RESPONSE_EXCEPTIONS = {"RateLimitError", "APIConnectionError", "APITimeoutError"}


def is_counted(entry: dict[str, Any]) -> bool:
    """One rule for both arms (E6-Plan, decision 4): a call counts when a response came back."""
    return not (entry.get("uncounted")
                or entry.get("exception_type") in NO_RESPONSE_EXCEPTIONS
                or entry.get("provider_error_code") in {402, 429})


def counted_requests(call_log: list[dict[str, Any]]) -> int:
    return sum(1 for entry in call_log if is_counted(entry))


def pipeline_requests(case_dir: Path) -> int:
    """The pipeline arm's counted requests on one case, over all its attempt records."""
    paths = sorted(case_dir.glob("attempt-*.json"))
    if not paths:
        raise ValueError(f"no pipeline attempt records in {case_dir}")
    return sum(counted_requests(json.loads(path.read_text(encoding="utf-8"))
                                .get("model_call_log_this_attempt", [])) for path in paths)


def _save(path: Path, session: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(session, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def new_session(case: dict[str, Any], cap: int, provider: str) -> dict[str, Any]:
    return {"case_id": case["id"], "language": case["language"], "cap": cap,
            "prompt_version": BASELINE_PROMPT_VERSION, "provider": provider, "model_name": None,
            "status": "running", "transcript": [{"role": "user", "source": "prompt",
                                                  "content": case["prompt"]}],
            "call_log": [], "checks": [], "user_turns": 0, "forwarded_errors": 0,
            "model_seconds": 0.0, "delivered_contract": None, "delivered_turn": None,
            "events": []}


def step(session: dict[str, Any], model: Any, check: Callable[[Any], dict[str, Any]], *,
         system: str) -> dict[str, Any]:
    """Run model turns until the simulated user must act, the cap is reached, or quota runs out."""
    from research.adapters.model_transport import ModelTransportError

    while True:
        used = counted_requests(session["call_log"])
        if used >= session["cap"]:
            session["status"] = "cap_reached"
            return session
        log_start = len(getattr(model, "call_log", []))
        if hasattr(model, "set_call_budget"):
            model.set_call_budget(session["cap"] - used)
        started = time.monotonic()
        reply: Any = None
        failure: str | None = None
        try:
            reply = model.generate(system, _render(session["transcript"]))
        except ModelTransportError as exc:
            failure = exc.code
        session["model_seconds"] += time.monotonic() - started
        new_entries = [dict(entry) for entry in getattr(model, "call_log", [])[log_start:]]
        if failure in UNCOUNTED_FAILURES and new_entries:
            new_entries[-1]["uncounted"] = True
        session["call_log"].extend(new_entries)
        session["model_name"] = getattr(model, "model", session["model_name"])
        if failure in UNCOUNTED_FAILURES:
            session["status"] = UNCOUNTED_FAILURES[failure]
            return session
        if failure is not None:
            session["events"].append({"kind": "model_error", "code": failure})
            reply = None
        kind, problems = _parse_reply(reply) if failure is None else (None, [failure])
        session["transcript"].append({"role": "assistant", "reply": reply})
        if kind is None:
            result = {"passed": False, "stage": "format", "messages": problems}
        elif kind != "contract":
            session["status"] = AWAITING[kind]
            return session
        else:
            result = check(reply["contract"])
        session["checks"].append({"turn": len(session["transcript"]) - 1,
                                  **{key: value for key, value in result.items()}})
        if result["passed"]:
            session["delivered_contract"] = reply["contract"]
            session["delivered_turn"] = len(session["transcript"]) - 1
            session["status"] = AWAITING["contract"]
            return session
        session["transcript"].append({"role": "user", "source": "forwarded_error",
                                      "content": check_feedback(session["language"], result)})
        session["forwarded_errors"] += 1


def run(index: int, *, cap: int | None = None, message: str | None = None,
        finish: str | None = None, run_dir: Path = RUN_DIR, provider: str = "gemini",
        dataset: str = "v3",
        model: Any | None = None, check: Callable[[Any], dict[str, Any]] | None = None
        ) -> dict[str, Any]:
    if provider not in PROVIDERS:
        raise ValueError(f"provider must be one of {', '.join(PROVIDERS)}")
    if message is not None and finish is not None:
        raise ValueError("give a user message or a finish action, not both")
    if finish not in {None, "accept", "give_up"}:
        raise ValueError("finish must be accept or give_up")
    case = load_case(index, dataset)
    case_dir = run_dir / f"case-{index:03d}"
    case_dir.mkdir(parents=True, exist_ok=True)
    path = case_dir / "session.json"
    if path.exists():
        session = json.loads(path.read_text(encoding="utf-8"))
        if session["case_id"] != case["id"]:
            raise ValueError("stored session belongs to another case")
        if cap is not None and cap != session["cap"]:
            raise ValueError("the cap of a started session cannot change")
    else:
        if type(cap) is not int or cap < 1:
            raise ValueError("a new session needs --cap, the pipeline arm's request count")
        if message is not None or finish is not None:
            raise ValueError("a new session starts from the case prompt alone")
        session = new_session(case, cap, provider)
    if session["status"] in FINAL:
        raise ValueError(f"session already ended: {session['status']}")
    if finish is not None:
        if finish == "accept" and session["status"] != "awaiting_review" and \
                session["status"] != "awaiting_reaction":
            raise ValueError("only a delivered contract or a refusal can be accepted")
        session["status"] = "accepted" if finish == "accept" else "gave_up"
        session["events"].append({"kind": finish, "at_utc": datetime.now(timezone.utc).isoformat()})
        _save(path, session)
        return session
    if message is not None:
        if not message.strip() or session["status"] not in set(AWAITING.values()):
            raise ValueError("a user message needs a nonempty text and a waiting session")
        session["transcript"].append({"role": "user", "source": "simulated_user",
                                      "content": message.strip()})
        session["user_turns"] += 1
    elif session["status"] not in {"running", *UNCOUNTED_FAILURES.values()}:
        raise ValueError(f"session waits for the simulated user ({session['status']})")
    session["status"] = "running"
    if model is None:
        model = _transport(case_dir, case["id"], provider)
    if check is None:
        from research.ledger.marlowe_cli import config_from_environment

        check = make_checker(config_from_environment())
    try:
        step(session, model, check, system=_system_prompt())
    finally:
        _save(path, session)
    return session


def _transport(case_dir: Path, case_id: str, provider: str) -> Any:
    from research.adapters.model_transport import ModelTransport

    journal = case_dir / "outbound-requests.jsonl"
    last: list[float] = []

    def before_request(phase: str) -> None:
        interval = MIN_REQUEST_INTERVAL_SECONDS[provider]
        if interval and last:
            wait = interval - (time.monotonic() - last[-1])
            if wait > 0:
                time.sleep(wait)
        last.append(time.monotonic())
        with journal.open("a", encoding="utf-8") as writer:
            writer.write(json.dumps({"case_id": case_id, "phase": phase, "provider": provider,
                                     "reserved_at_utc": datetime.now(timezone.utc).isoformat()})
                         + "\n")
            writer.flush()
            os.fsync(writer.fileno())

    return ModelTransport(before_request=before_request, api_style="chat", max_tokens=16000,
                          disable_reasoning=True, retry_empty=False, request_json_object=False,
                          provider=None if provider == "default" else provider)


def summary(session: dict[str, Any]) -> dict[str, Any]:
    log = [entry for entry in session["call_log"] if is_counted(entry)]
    return {"case_id": session["case_id"], "status": session["status"], "cap": session["cap"],
            "requests": len(log),
            "prompt_tokens": sum(entry.get("prompt_tokens") or 0 for entry in log),
            "completion_tokens": sum(entry.get("completion_tokens") or 0 for entry in log),
            "user_turns": session["user_turns"], "forwarded_errors": session["forwarded_errors"],
            "model_seconds": round(session["model_seconds"], 1),
            "delivered": session["delivered_contract"] is not None}


def main() -> int:
    if os.name == "nt":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="E6 baseline arm: plain LLM, one case")
    parser.add_argument("--case-index", type=int, required=True)
    parser.add_argument("--cap", type=int, help="pipeline arm's request count (new session)")
    parser.add_argument("--pipeline-case-dir", type=Path,
                        help="read the cap from the pipeline arm's attempt records instead")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--message-file", type=Path, help="simulated user's next message")
    action.add_argument("--accept", action="store_true")
    action.add_argument("--give-up", action="store_true")
    parser.add_argument("--provider", choices=PROVIDERS, default="gemini")
    parser.add_argument("--dataset", choices=["v3", "dev"], default="v3",
                        help="dev = dataset v2 cases 1-56, for trials and tuning only")
    parser.add_argument("--run-dir", type=Path, default=RUN_DIR)
    args = parser.parse_args()
    message = args.message_file.read_text(encoding="utf-8") if args.message_file else None
    finish = "accept" if args.accept else "give_up" if args.give_up else None
    if args.pipeline_case_dir is not None:
        if args.cap is not None:
            parser.error("give --cap or --pipeline-case-dir, not both")
        args.cap = pipeline_requests(args.pipeline_case_dir)
    session = run(args.case_index, cap=args.cap, message=message, finish=finish,
                  run_dir=args.run_dir, provider=args.provider, dataset=args.dataset)
    last = next((turn for turn in reversed(session["transcript"])
                 if turn["role"] == "assistant"), None)
    print(json.dumps(summary(session), ensure_ascii=False))
    if last is not None and session["status"] in set(AWAITING.values()):
        print((last["reply"] or {}).get("message", ""))
    return 3 if session["status"] in UNCOUNTED_FAILURES.values() else 0


if __name__ == "__main__":
    raise SystemExit(main())
