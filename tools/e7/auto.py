"""E7 driver: both arms with the sim-user subagent as the user (docs/E7-Conventions.md).

  python tools/e7/auto.py pipe N              drive the pipeline arm of case N
  python tools/e7/auto.py base N              drive the baseline arm (after the pipeline arm ended)
  python tools/e7/auto.py reply pipe|base N '<sim-user JSON>'   record the sim-user's reply

When an arm needs the user, the driver writes `simuser-input.txt` in the case directory and stops
with exit 5 (NEED_SIMUSER). The operator gives that file, verbatim, to a fresh `sim-user` subagent
(Claude Haiku 5.5, effort medium) and records its JSON reply, verbatim, with `reply`. The operator
never writes or edits a reply (Q-NGƯỜI DÙNG 6). `reply` checks it (Q-NGƯỜI DÙNG 3); a reply that
fails asks for a new one (exit 6) at most twice, then a fixed "I know nothing more" reply is used.

What the user sees (Q-NHÁNH 2-3):
- pipeline: its questions; a plain-language summary of the intent under review; a request for
  example situations; the scenarios read back in words;
- baseline: its questions, refusals and contract explanations.
The user's action label is not trusted (Q-NGƯỜI DÙNG 4): on a result, only "accept" with an empty
message accepts; any message is an objection sent to the arm.

Exit codes: 0 the arm ended, 3 quota, 4 infrastructure, 5 sim-user reply needed, 6 reply rejected.
"""

from __future__ import annotations

import json
import re
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "e6"))

from expect import build  # noqa: E402
from simuser import check_reply, situation, user_view  # noqa: E402
from research.experiments.baseline_llm import counted_requests, pipeline_requests  # noqa: E402

# E7_DATASET=v4 (dev, default) or v5 (the evaluation set, run only after the code is frozen).
DATASET = os.environ.get("E7_DATASET", "v4")
if DATASET not in {"v4", "v5"}:
    raise SystemExit("E7_DATASET must be v4 or v5")
RUNNER = "/mnt/d/code/marlowe_ai_agent/tools/e6/run_wsl.sh"
_SUFFIX = "" if DATASET == "v4" else "-Eval"
PIPE_DIR = ROOT / "runs" / f"E7{_SUFFIX}-Pipeline"
BASE_DIR = ROOT / "runs" / f"E7{_SUFFIX}-Baseline"
DELIVERED = "SIMULATED_LEDGER_SIZE_CHECKED"
MAX_RETRIES = 2
MAX_USER_MESSAGES = 6
MAX_REPLY_RETRIES = 2
MAX_EXAMPLE_ROUNDS = 2
AGENT_FILE = ROOT / ".claude" / "agents" / "sim-user.md"


def _persona() -> str:
    """The sim-user rules (SimUser-v3), copied into every input so each turn carries them."""
    text = AGENT_FILE.read_text(encoding="utf-8")
    return text.split("---", 2)[2].strip()


HEADER = ("Do not use any tools except the one that hands your final report back. Your final "
          "report must be exactly the one JSON object described under OUTPUT, nothing else.\n\n"
          + _persona() + "\n\n=== YOUR SITUATION ===\n")
FALLBACK = {"vi": "Tôi không biết thêm, bạn làm theo những gì tôi đã nói.",
            "en": "I don't know anything more; please go with what I already said."}
RESULT = {"result": "[RESULT: the assistant shows how it understood your request:] ",
          "readback": "[RESULT: the assistant shows the test situations it will use:] ",
          "contract": "[RESULT: the assistant delivered a contract and says:] ",
          "decline": "[RESULT: the assistant declined and says:] "}


# -- sim-user exchange ---------------------------------------------------------------------------

def _log(case_dir: Path) -> dict:
    path = case_dir / "simuser.json"
    return (json.loads(path.read_text(encoding="utf-8")) if path.exists()
            else {"history": [], "turns": [], "user_messages": 0})


def _save_log(case_dir: Path, log: dict) -> None:
    (case_dir / "simuser.json").write_text(json.dumps(log, ensure_ascii=False, indent=1) + "\n",
                                           encoding="utf-8")


def _need(case_dir: Path, index: int, kind: str, text: str) -> int:
    """Show `text` to the user and stop until the sim-user's reply is recorded."""
    log = _log(case_dir)
    shown = RESULT.get(kind, "") + text.replace("[restate] ", "")
    if not log["history"] or log["history"][-1] != ["assistant", shown]:
        log["history"].append(["assistant", shown])
    _save_log(case_dir, log)
    (case_dir / "simuser-pending.json").write_text(
        json.dumps({"kind": kind, "shown": shown, "retries": 0}, ensure_ascii=False), encoding="utf-8")
    view = user_view(index, DATASET)
    (case_dir / "simuser-input.txt").write_text(
        HEADER + situation(view, [tuple(item) for item in log["history"]]), encoding="utf-8")
    print(f"NEED_SIMUSER {case_dir.parent.name} {index} {case_dir / 'simuser-input.txt'}")
    return 5


AFFIRM = re.compile(r"^\s*(?:yes|yep|ok|okay|correct|right|that's right|exactly|looks good|đúng|đúng rồi|"
                    r"đúng vậy|dung roi|dung|ok|được|duoc|đồng ý|dong y|chuẩn|chuan|vâng|vang|ừ|u)\b",
                    re.IGNORECASE)
DISSENT = re.compile(r"\b(?:but|however|wrong|incorrect|instead|should|shouldn't|not right|change|fix|"
                     r"missing|nhưng|nhung|sai|không đúng|khong dung|chưa đúng|chua dung|phải là|phai la|"
                     r"thay vì|thay vi|nhầm|nham|sửa|sua|thiếu|thieu|chứ không|chu khong)\b", re.IGNORECASE)


def plain_agreement(message: str) -> bool:
    """A message that only agrees ("Yes, these are what I mean") accepts, whatever its label;
    any sign of dissent keeps it an objection (Q-NGƯỜI DÙNG 4, bản 3)."""
    return bool(message) and bool(AFFIRM.search(message)) and not DISSENT.search(message)


def reply(arm: str, index: int, raw: str) -> int:
    case_dir = (PIPE_DIR if arm == "pipe" else BASE_DIR) / f"case-{index:03d}"
    pending_path = case_dir / "simuser-pending.json"
    if not pending_path.exists():
        raise SystemExit("reply: nothing is waiting for the sim-user")
    pending = json.loads(pending_path.read_text(encoding="utf-8"))
    view = user_view(index, DATASET)
    log = _log(case_dir)
    seen = " ".join(text for who, text in log["history"] if who == "assistant")
    problems = check_reply(view, seen, raw)
    log["turns"].append({"kind": pending["kind"], "raw": raw, "problems": problems,
                         "retry": pending["retries"]})
    if problems and pending["retries"] < MAX_REPLY_RETRIES:
        pending["retries"] += 1
        pending_path.write_text(json.dumps(pending, ensure_ascii=False), encoding="utf-8")
        _save_log(case_dir, log)
        print("RETRY " + "; ".join(problems))
        return 6
    if problems:
        decision = {"action": "answer", "message": FALLBACK[view["language"]], "fallback": True}
    else:
        parsed = json.loads(raw)
        decision = {"action": parsed.get("action"), "message": str(parsed.get("message", "")).strip()}
    if decision["action"] == "give_up":
        outcome = {"kind": "give_up"}
    elif pending["kind"] in RESULT:
        accepted = ((decision["action"] == "accept" and not decision["message"])
                    or plain_agreement(decision["message"]))
        outcome = {"kind": "accept"} if accepted else {
            "kind": "message", "text": decision["message"] or FALLBACK[view["language"]]}
    else:
        outcome = {"kind": "message", "text": decision["message"] or FALLBACK[view["language"]]}
    if outcome["kind"] == "message":
        log["history"].append(["you", outcome["text"]])
        log["user_messages"] += 1
    elif outcome["kind"] == "accept":
        log["history"].append(["you", "(you accepted)"])
    else:
        log["history"].append(["you", "(you gave up)"])
    _save_log(case_dir, log)
    pending_path.unlink()
    (case_dir / "simuser-decision.json").write_text(
        json.dumps({**outcome, "for": pending["kind"], "shown": pending["shown"]},
                   ensure_ascii=False), encoding="utf-8")
    print(f"recorded {outcome['kind']} for {arm} {case_dir.name}")
    return 0


def _decision(case_dir: Path) -> dict | None:
    path = case_dir / "simuser-decision.json"
    if not path.exists():
        return None
    decision = json.loads(path.read_text(encoding="utf-8"))
    path.unlink()
    return decision


def _out_of_turns(case_dir: Path) -> bool:
    return _log(case_dir)["user_messages"] >= MAX_USER_MESSAGES


# -- infrastructure ---------------------------------------------------------------------------

def _keys() -> list[int] | None:
    """Gemini keys this run may use, from E7_GEMINI_KEYS (for example "1,2"); None = the shared
    E6 rotation over all keys. Infrastructure only: lets two runs use separate keys in parallel."""
    import os

    value = os.environ.get("E7_GEMINI_KEYS", "").strip()
    return [int(item) for item in value.split(",") if item.strip()] if value else None


def _pool_file(keys: list[int]) -> Path:
    return ROOT / "runs" / f"E7-gemini-slot-{'-'.join(map(str, keys))}.json"


def _current_slot() -> int:
    sys.path.insert(0, str(ROOT / "tools" / "e6"))
    from auto import _quota_day, _slot  # the E6 key rotation state is shared

    keys = _keys()
    if keys is None:
        return _slot()
    path = _pool_file(keys)
    if path.exists():
        state = json.loads(path.read_text(encoding="utf-8"))
        if state.get("day") == _quota_day() and state.get("slot") in keys:
            return int(state["slot"])
    return keys[0]


def _wsl(module: str, *args: str) -> subprocess.CompletedProcess:
    import os

    env = {**os.environ, "E6_GEMINI_SLOT": str(_current_slot()), "WSLENV": "E6_GEMINI_SLOT"}
    return subprocess.run(["wsl", "-d", "Ubuntu", "--", "bash", RUNNER, module, *args],
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=1800, env=env)


def _rotate() -> bool:
    keys = _keys()
    if keys is None:
        from auto import _rotate as rotate

        return rotate()
    from auto import _quota_day

    slot = _current_slot()
    if keys.index(slot) + 1 >= len(keys):
        return False
    _pool_file(keys).write_text(json.dumps({"day": _quota_day(), "slot": keys[keys.index(slot) + 1]}),
                                encoding="utf-8")
    print(f"  quota on key {slot}: switching to key {keys[keys.index(slot) + 1]}")
    return True


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _last(case_dir: Path) -> dict | None:
    paths = sorted(case_dir.glob("attempt-*.json"))
    return json.loads(paths[-1].read_text(encoding="utf-8")) if paths else None


def _last_path(case_dir: Path) -> Path:
    return sorted(case_dir.glob("attempt-*.json"))[-1]


def _finish(case_dir: Path, record: dict | None, end: str, **extra) -> int:
    final = {"end": end, "status": record.get("status") if record else None,
             "stop_reason": record.get("stop_reason") if record else None,
             "delivered": bool(record) and record.get("status") == DELIVERED,
             "requests": pipeline_requests(case_dir) if record else 0,
             "user_messages": _log(case_dir)["user_messages"], **extra}
    (case_dir / "final.json").write_text(json.dumps(final, ensure_ascii=False, indent=1) + "\n",
                                         encoding="utf-8")
    print(f"PIPE {case_dir.name} END {json.dumps(final, ensure_ascii=False)}")
    return 0


def _pipe_run(index: int, *args: str) -> tuple[int | None, dict | None]:
    case_dir = PIPE_DIR / f"case-{index:03d}"
    result = _wsl("research.experiments.roleplay_case", "--case-index", str(index),
                  "--dataset", DATASET, "--formalization", "AFF", "--provider", "gemini",
                  "--run-dir", _rel(PIPE_DIR), *args)
    record = _last(case_dir)
    line = next((item for item in result.stdout.splitlines() if item.startswith("case ")), "")
    print(f"  run {' '.join(args) or '(plain)'} -> {line or result.returncode}")
    if result.returncode == 3 or (record and record.get("provider_limit")):
        if _rotate():
            retry = () if "--revision-file" in args else args
            return _pipe_run(index, *retry)
        return 3, record
    if result.returncode != 0:
        print(result.stdout[-1500:], result.stderr[-1500:])
        return 4, record
    ledger = (record or {}).get("steps", {}).get("ledger_validation", {})
    if ledger.get("run_status") == "UNAVAILABLE":
        return 4, record
    return None, record


def _revise(index: int, case_dir: Path, text: str, question: str) -> tuple[int | None, dict | None]:
    number = len(list(case_dir.glob("reply-*.txt"))) + 1
    answer, asked = case_dir / f"reply-{number}.txt", case_dir / f"question-{number}.txt"
    answer.write_text(text, encoding="utf-8")
    asked.write_text(question, encoding="utf-8")
    return _pipe_run(index, "--revision-file", _rel(answer), "--revision-question-file", _rel(asked))


# -- pipeline arm -----------------------------------------------------------------------------

def _stage(case_dir: Path) -> dict:
    path = case_dir / "stage.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _set_stage(case_dir: Path, stage: dict) -> None:
    (case_dir / "stage.json").write_text(json.dumps(stage, ensure_ascii=False, indent=1) + "\n",
                                         encoding="utf-8")


def _convert(index: int, case_dir: Path, examples: str) -> dict:
    number = len(list(case_dir.glob("examples-*.json"))) + 1
    source = case_dir / f"examples-{number}.txt"
    source.write_text(examples, encoding="utf-8")
    out = case_dir / f"examples-{number}.json"
    result = _wsl("research.synthesis.example_scenarios", "--case-dir", _rel(case_dir),
                  "--candidate-file", _rel(_last_path(case_dir)), "--examples-file", _rel(source),
                  "--out", _rel(out))
    print(f"  examples {number} -> {result.stdout.strip()[-300:] or result.returncode}")
    return json.loads(out.read_text(encoding="utf-8")) if out.exists() else {
        "scenarios": {}, "problems": [f"converter failed: {result.stderr[-300:]}"]}


NO_RESPONSE_ERRORS = {"provider_request_failed", "provider_error", "provider_limit"}


def _convert_with_retries(index: int, case_dir: Path, examples: str) -> dict:
    """Convert examples, retrying a call that got no model response (network, timeout, 5xx)
    up to three times a minute apart, and switching key on quota."""
    import time

    for attempt in range(3):
        converted = _convert(index, case_dir, examples)
        error = converted.get("error")
        if error not in NO_RESPONSE_ERRORS:
            return converted
        if error == "provider_limit" and not _rotate():
            return converted
        if attempt < 2 and error != "provider_limit":
            print(f"  conversion got no model response ({error}); retry in 60 s")
            time.sleep(60)
    return converted


def pipe(index: int) -> int:
    from research.formalization.intent_summary import summarize
    from research.synthesis.example_scenarios import examples_request

    case_dir = PIPE_DIR / f"case-{index:03d}"
    case_dir.mkdir(parents=True, exist_ok=True)
    if (case_dir / "final.json").exists():
        print(f"PIPE case-{index:03d} already ended")
        return 0
    language = user_view(index, DATASET)["language"]
    retries = 0
    outage_waits = 0
    record = _last(case_dir)
    code = None
    resumed = _resume_scenarios(index, case_dir, record)
    if resumed is not None:
        return resumed
    while True:
        decision = _decision(case_dir)
        if record is None:
            code, record = _pipe_run(index)
        elif record["status"] == "WAITING_USER" and record.get("stop_reason") == "no_user_input":
            questions = "\n".join(record.get("questions") or [])
            if decision is None:
                if _out_of_turns(case_dir):
                    return _finish(case_dir, record, "user_out_of_turns")
                return _need(case_dir, index, "question", questions)
            if decision["kind"] == "give_up":
                return _finish(case_dir, record, "user_gave_up")
            code, record = _revise(index, case_dir, decision["text"], questions)
        elif record["status"] == "WAITING_RESEARCH_REVIEW":
            candidate = record["steps"]["intent_extraction"]["output_artifacts"][0]
            core = record["candidate"]["semantic_core"]
            stage = _stage(case_dir)
            if stage.get("candidate") != candidate:
                stage = {"candidate": candidate, "step": "review", "rounds": 0}
                _set_stage(case_dir, stage)
            if decision is None and stage["step"] == "converting":
                # A conversion stopped by infrastructure resumes with the same examples (D3).
                decision = {"kind": "message", "text": stage["pending_examples"], "resume": True}
            if decision is None:
                if _out_of_turns(case_dir):
                    return _finish(case_dir, record, "user_out_of_turns")
                if stage["step"] == "review":
                    return _need(case_dir, index, "result", summarize(core))
                if stage["step"] == "examples":
                    return _need(case_dir, index, "examples", examples_request(core))
                return _need(case_dir, index, "readback", stage["readback"])
            if decision["kind"] == "give_up":
                return _finish(case_dir, record, "user_gave_up")
            if stage["step"] == "review":
                if decision["kind"] == "message":
                    # An objection to the summary is a revision of the request.
                    code, record = _revise(index, case_dir, decision["text"], decision["shown"])
                else:
                    stage["step"] = "examples"
                    _set_stage(case_dir, stage)
                    continue
            elif stage["step"] in {"examples", "converting"} or (stage["step"] == "readback"
                                                                 and decision["kind"] == "message"):
                if stage["step"] == "converting":
                    examples = stage["pending_examples"]
                elif stage["step"] == "examples":
                    examples = decision["text"]
                else:
                    examples = stage["examples"] + "\n" + decision["text"]
                if stage["rounds"] + 1 > MAX_EXAMPLE_ROUNDS:
                    return _finish(case_dir, record, "scenarios_not_confirmed")
                converted = _convert_with_retries(index, case_dir, examples)
                if converted.get("error") in NO_RESPONSE_ERRORS:
                    # No usable model response: infrastructure, not a failed round (D3). The
                    # same examples are converted again when the case resumes.
                    stage.update(step="converting", pending_examples=examples)
                    _set_stage(case_dir, stage)
                    return 3 if converted.get("error") == "provider_limit" else 4
                stage.pop("pending_examples", None)
                stage["rounds"] += 1
                if not converted.get("scenarios"):
                    stage.update(step="examples", examples=examples)
                    _set_stage(case_dir, stage)
                    if stage["rounds"] >= MAX_EXAMPLE_ROUNDS:
                        return _finish(case_dir, record, "no_scenarios",
                                       problems=converted.get("problems"))
                    continue
                stage.update(step="readback", examples=examples, scenarios=converted["scenarios"],
                             readback=converted["readback"])
                _set_stage(case_dir, stage)
                continue
            else:  # the user accepted the read-back scenarios
                spec = {"intent_id": candidate, "scenarios": stage["scenarios"]}
                (case_dir / "scenarios.json").write_text(
                    json.dumps(spec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
                code, record = _pipe_run(index, "--review-candidate-id", candidate)
                if code is None:
                    return _scenarios(index, case_dir, record, candidate, spec)
        elif (record["status"] in {"BLOCKED", "WAITING_USER"}
              and record.get("stop_reason") == "llm_error" and _no_response(record)):
            # No model response (quota, network, 5xx) is infrastructure, never a failed retry
            # (D6): run again after a wait; after 3 waits exit 4 and resume later.
            if outage_waits >= 3:
                print(f"PIPE {case_dir.name}: model gave no response; resume later")
                return 4
            import time

            outage_waits += 1
            print(f"  model gave no response; retry {outage_waits} in 60 s")
            time.sleep(60)
            code, record = _pipe_run(index)
        elif (record["status"] in {"BLOCKED", "WAITING_USER"}
              and record.get("stop_reason") in {"invalid_candidate", "llm_error"}
              and retries < MAX_RETRIES):
            retries += 1
            code, record = _pipe_run(index)
        else:
            return _finish(case_dir, record, "pipeline_stopped")
        if code is not None:
            return code


def _no_response(record: dict) -> bool:
    """The blocking step failed with no model content at all (quota, network, 5xx)."""
    error = (record.get("steps", {}).get(record.get("blocking_step") or "", {}).get("safe_error")
             or {})
    return (error.get("code") in {"provider_request_failed", "provider_limit"}
            and not error.get("model_content_received"))


def _resume_scenarios(index: int, case_dir: Path, record: dict | None) -> int | None:
    """Resume a case whose confirmed scenarios were being run when infrastructure stopped it
    (E7 protocol 2.4): run the review again if it never compiled, else every scenario again on the
    compiled contract. None when the case is not at that point."""
    spec_path = case_dir / "scenarios.json"
    if record is None or not spec_path.exists():
        return None
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    candidate = spec.get("intent_id")
    if record["status"] == "WAITING_RESEARCH_REVIEW":
        current = record["steps"]["intent_extraction"]["output_artifacts"][0]
        if current != candidate or _stage(case_dir).get("step") != "readback" or \
                (case_dir / "simuser-pending.json").exists():
            return None
        code, compiled = _pipe_run(index, "--review-candidate-id", candidate)
        return code if code is not None else _scenarios(index, case_dir, compiled, candidate, spec)
    compiled = None
    for path in sorted(case_dir.glob("attempt-*.json")):
        attempt = json.loads(path.read_text(encoding="utf-8"))
        if (attempt.get("reviewed_candidate_id") == candidate
                and not attempt.get("replayed_contract_candidate_id")):
            compiled = attempt
    if compiled is None:
        return None
    error = (compiled.get("steps", {}).get("compile", {}).get("safe_error") or {}).get("code")
    if error in {"provider_request_failed", "provider_limit"}:
        # The compile got no model response: run the review again, not the failed attempt (D4).
        # Such a case is never ended for it; it waits for the provider (D5).
        print(f"PIPE {case_dir.name}: compile got no model response; running the review again")
        code, compiled = _pipe_run(index, "--review-candidate-id", candidate)
        return code if code is not None else _scenarios(index, case_dir, compiled, candidate, spec)
    print(f"PIPE {case_dir.name}: resuming the scenario runs on the compiled contract")
    return _scenarios(index, case_dir, compiled, candidate, spec)


def _scenarios(index: int, case_dir: Path, record: dict, candidate: str, spec: dict) -> int:
    compiled = record.get("steps", {}).get("compile", {})
    if (compiled.get("safe_error") or {}).get("code") in {"provider_request_failed", "provider_limit"}:
        # No model response (quota, network, 5xx) is infrastructure (protocol 2.2, 2.4, 6): the
        # case is never ended for it, like the baseline arm on provider_error; it resumes later
        # with the review run again (D5).
        print(f"PIPE {case_dir.name}: compile got no model response; resume later")
        return 4
    if compiled.get("run_status") != "SUCCEEDED" or record.get("blocking_step") != "semantic_comparison":
        return _finish(case_dir, record, "pipeline_stopped_before_scenarios")
    return _scenario_pass(index, case_dir, candidate, compiled["output_artifacts"][0], spec)


def _scenario_pass(index: int, case_dir: Path, candidate: str, contract: str, spec: dict,
                   restarts: int = 0) -> int:
    """Every scenario on one contract; a regenerated contract is checked by all of them again."""
    done = {}
    for name, compact in spec["scenarios"].items():
        path = case_dir / f"scenario-{name}.json"
        path.write_text(json.dumps(build(compact), ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")
        code, record = _pipe_run(index, "--review-candidate-id", candidate,
                                 "--replay-contract-id", contract, "--expectation-file", _rel(path),
                                 "--answers-file", "tools/e6/confirm.json")
        if code is not None:
            return code
        done[name] = record["status"]
        regenerated = sum(1 for item in record["execution_history"] if item["step"] == "compile") > 1
        if record["status"] == DELIVERED and regenerated and restarts < 3:
            new = record["steps"]["compile"]["output_artifacts"][0]
            print(f"  scenario {name} regenerated the contract; rerunning all scenarios on it")
            return _scenario_pass(index, case_dir, candidate, new, spec, restarts + 1)
        if record["status"] != DELIVERED:
            return _finish(case_dir, record, f"scenario_not_delivered:{name}", scenarios=done)
    return _finish(case_dir, record, "all_scenarios_delivered", scenarios=done)


# -- baseline arm -----------------------------------------------------------------------------

def base(index: int) -> int:
    pipe_dir = PIPE_DIR / f"case-{index:03d}"
    if not (pipe_dir / "final.json").exists():
        print(f"BASE case-{index:03d}: pipeline arm has not ended")
        return 4
    case_dir = BASE_DIR / f"case-{index:03d}"
    case_dir.mkdir(parents=True, exist_ok=True)
    path = case_dir / "session.json"
    args: list[str] = [] if path.exists() else ["--cap", str(max(pipeline_requests(pipe_dir), 1))]
    server_retries = 0
    while True:
        if path.exists():
            session = json.loads(path.read_text(encoding="utf-8"))
            status = session["status"]
            if status in {"accepted", "gave_up", "cap_reached"}:
                print(f"BASE {case_dir.name} END {status} requests "
                      f"{counted_requests(session['call_log'])}/{session['cap']} "
                      f"delivered {session['delivered_contract'] is not None}")
                return 0
            if status in {"awaiting_answer", "awaiting_review", "awaiting_reaction"}:
                decision = _decision(case_dir)
                if decision is None:
                    last = next(turn for turn in reversed(session["transcript"])
                                if turn["role"] == "assistant")
                    message = (last.get("reply") or {}).get("message", "")
                    kind = {"awaiting_answer": "question", "awaiting_review": "contract",
                            "awaiting_reaction": "decline"}[status]
                    if _out_of_turns(case_dir):
                        args = ["--give-up"]
                    else:
                        return _need(case_dir, index, kind, message)
                elif decision["kind"] == "give_up":
                    args = ["--give-up"]
                elif decision["kind"] == "accept":
                    args = ["--accept"]
                else:
                    number = len(list(case_dir.glob("reply-*.txt"))) + 1
                    message_path = case_dir / f"reply-{number}.txt"
                    message_path.write_text(decision["text"], encoding="utf-8")
                    args = ["--message-file", _rel(message_path)]
            elif status not in {"running", "provider_limit", "provider_error"}:
                print(f"BASE {case_dir.name}: unexpected status {status}")
                return 4
        result = _wsl("research.experiments.baseline_llm", "--case-index", str(index),
                      "--dataset", DATASET, "--run-dir", _rel(BASE_DIR), *args)
        print(f"  base {' '.join(args) or '(resume)'} -> rc {result.returncode}")
        if result.returncode == 3:
            stopped = json.loads(path.read_text(encoding="utf-8"))["status"]
            if stopped == "provider_error" and server_retries < 3:
                import time

                server_retries += 1
                print(f"  provider server error; retry {server_retries} in 60 s")
                time.sleep(60)
                args = []
                continue
            if stopped == "provider_limit" and _rotate():
                args = []
                continue
            return 3
        if result.returncode != 0:
            print(result.stdout[-1500:], result.stderr[-1500:])
            return 4
        args = []


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.argv[1] == "reply":
        raise SystemExit(reply(sys.argv[2], int(sys.argv[3]), sys.argv[4]))
    raise SystemExit({"pipe": pipe, "base": base}[sys.argv[1]](int(sys.argv[2])))
