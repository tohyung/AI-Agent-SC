"""E6 automatic driver for both arms (run from Windows; the arms run inside WSL).

  python tools/e6/auto.py pipe N    drive the pipeline arm of case N as far as it can go
  python tools/e6/auto.py base N    drive the baseline arm of case N (after the pipeline arm ended)
  python tools/e6/auto.py answer pipe|base N auto|giveup|"<restatement>"
  python tools/e6/auto.py scen N '{"<name>": <compact scenario>, ...}'   (for the intent under review)

When an arm asks, the driver stops (exit 5) and prints the questions and the automatic reply. The
simulated user then records one answer (replies.json of the case):
  auto          the automatic reply of research.experiments.e6_user (fact sheet, then fixed lines);
  "<text>"      a restatement of what the prompt already says, for a question the prompt answers
                (no new facts); on the first reply the fact sheet, if any, is appended;
  giveup        the same questions came back after being answered twice.

The only manual step is `runs/E6-Pipeline/case-NNN/scenarios.json`, written by the simulated user
from the prompt, fact sheet and the intent under review (never the contract):
  {"intent_id": "<candidate id>", "scenarios": {"<name>": <compact form of tools/e6/expect.py>}}
When it is missing the driver stops with exit code 2 and prints the intent.

Exit codes: 0 the arm ended (final.json written), 2 scenarios needed, 3 quota (resume later),
4 infrastructure (ledger or harness) problem, 5 a reply is needed.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "e6"))

from expect import build  # noqa: E402
from research.experiments.baseline_llm import counted_requests, pipeline_requests  # noqa: E402
from research.experiments.e6_user import reply, user_view  # noqa: E402

RUNNER = "/mnt/d/code/marlowe_ai_agent/tools/e6/run_wsl.sh"
PIPE_DIR = ROOT / "runs" / "E6-Pipeline"
BASE_DIR = ROOT / "runs" / "E6-Baseline"
DELIVERED = "SIMULATED_LEDGER_SIZE_CHECKED"
MAX_RETRIES = 2  # plain reruns after a failed extraction, as the E3 runner allowed
MAX_COMPILE_FAILURES = 3  # runs whose compile got no usable model response


SLOT_FILE = ROOT / "runs" / "E6-gemini-slot.json"
SLOTS = 2


def _quota_day() -> str:
    """The free-tier quota day: it resets at 08:00 UTC."""
    from datetime import datetime, timedelta, timezone

    return (datetime.now(timezone.utc) - timedelta(hours=8)).date().isoformat()


def _slot() -> int:
    """Which Gemini key to use today; back to the first key when the quota day changes."""
    if SLOT_FILE.exists():
        state = json.loads(SLOT_FILE.read_text(encoding="utf-8"))
        if state.get("day") == _quota_day():
            return int(state["slot"])
    return 1


def _rotate() -> bool:
    """Switch to the next key after a quota error; False when every key is used up today."""
    slot = _slot()
    if slot >= SLOTS:
        return False
    SLOT_FILE.write_text(json.dumps({"day": _quota_day(), "slot": slot + 1}), encoding="utf-8")
    print(f"  quota on key {slot}: switching to key {slot + 1}")
    return True


def _wsl(module: str, *args: str) -> subprocess.CompletedProcess:
    import os

    env = {**os.environ, "E6_GEMINI_SLOT": str(_slot()), "WSLENV": "E6_GEMINI_SLOT"}
    return subprocess.run(["wsl", "-d", "Ubuntu", "--", "bash", RUNNER, module, *args],
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=1800, env=env)


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _last(case_dir: Path) -> dict | None:
    paths = sorted(case_dir.glob("attempt-*.json"))
    return json.loads(paths[-1].read_text(encoding="utf-8")) if paths else None


def _finish(case_dir: Path, record: dict | None, end: str, **extra) -> int:
    final = {"end": end, "status": record.get("status") if record else None,
             "stop_reason": record.get("stop_reason") if record else None,
             "delivered": bool(record) and record.get("status") == DELIVERED,
             "requests": pipeline_requests(case_dir), **extra}
    (case_dir / "final.json").write_text(json.dumps(final, ensure_ascii=False, indent=1) + "\n",
                                         encoding="utf-8")
    print(f"PIPE {case_dir.name} END {json.dumps(final, ensure_ascii=False)}")
    return 0


def _replies(case_dir: Path) -> list[dict]:
    path = case_dir / "replies.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def _pending(case_dir: Path) -> dict | None:
    path = case_dir / "pending-answer.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _take_reply(case_dir: Path, view: dict, questions: list[str]) -> tuple[str, Path | None]:
    """("need", None), ("giveup", None) or ("text", path of the reply file)."""
    pending = _pending(case_dir)
    log = _replies(case_dir)
    autos = sum(1 for item in log if item["mode"] == "auto")
    if pending is None:
        print("NEED_REPLY " + case_dir.name)
        for question in questions:
            print(f"  QUESTION: {question}")
        print(f"  AUTO REPLY: {reply(view, autos)!r}")
        return "need", None
    (case_dir / "pending-answer.json").unlink()
    if pending["mode"] == "giveup":
        log.append({"mode": "giveup", "questions": questions, "text": None})
        (case_dir / "replies.json").write_text(json.dumps(log, ensure_ascii=False, indent=1),
                                               encoding="utf-8")
        return "giveup", None
    if pending["mode"] == "auto":
        text = reply(view, autos)
        if text is None:
            return _take_giveup(case_dir, log, questions)
    else:
        text = pending["text"].strip()
        if not log and view["fact_sheet"]:
            text += "\n" + reply(view, 0)
    log.append({"mode": pending["mode"], "questions": questions, "text": text})
    (case_dir / "replies.json").write_text(json.dumps(log, ensure_ascii=False, indent=1),
                                           encoding="utf-8")
    path = case_dir / f"reply-{len(log)}.txt"
    path.write_text(text, encoding="utf-8")
    return "text", path


def _take_giveup(case_dir: Path, log: list, questions: list[str]) -> tuple[str, None]:
    log.append({"mode": "giveup", "questions": questions, "text": None})
    (case_dir / "replies.json").write_text(json.dumps(log, ensure_ascii=False, indent=1),
                                           encoding="utf-8")
    return "giveup", None


def answer(arm: str, index: int, value: str) -> int:
    case_dir = (PIPE_DIR if arm == "pipe" else BASE_DIR) / f"case-{index:03d}"
    case_dir.mkdir(parents=True, exist_ok=True)
    mode = value if value in {"auto", "giveup"} else "restate"
    payload = {"mode": mode, "text": value if mode == "restate" else None}
    (case_dir / "pending-answer.json").write_text(json.dumps(payload, ensure_ascii=False),
                                                 encoding="utf-8")
    print(f"recorded {mode} for {arm} {case_dir.name}")
    return 0


def _pipe_run(index: int, *args: str) -> tuple[int | None, dict | None]:
    result = _wsl("research.experiments.roleplay_case", "--case-index", str(index),
                  "--dataset", "v3", "--formalization", "AFF", "--provider", "gemini", *args)
    case_dir = PIPE_DIR / f"case-{index:03d}"
    record = _last(case_dir)
    line = next((item for item in result.stdout.splitlines() if item.startswith("case ")), "")
    print(f"  run {' '.join(args) or '(plain)'} -> {line or result.returncode}")
    if result.returncode == 3 or (record and record.get("provider_limit")):
        if _rotate():
            # A revision is already in the stored history: resume without sending it again.
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


def pipe(index: int) -> int:
    case_dir = PIPE_DIR / f"case-{index:03d}"
    case_dir.mkdir(parents=True, exist_ok=True)
    if (case_dir / "final.json").exists():
        print(f"PIPE case-{index:03d} already ended")
        return 0
    view = user_view(index)
    retries = 0
    record = _last(case_dir)
    while True:
        if record is None:
            code, record = _pipe_run(index)
        elif record["status"] == "WAITING_USER" and record.get("stop_reason") == "no_user_input":
            kind, path = _take_reply(case_dir, view, record.get("questions") or [])
            if kind == "need":
                return 5
            if kind == "giveup":
                return _finish(case_dir, record, "user_gave_up", replies=len(_replies(case_dir)))
            code, record = _pipe_run(index, "--revision-file", _rel(path))
        elif record["status"] == "WAITING_RESEARCH_REVIEW":
            candidate = record["steps"]["intent_extraction"]["output_artifacts"][0]
            spec_path = case_dir / "scenarios.json"
            spec = json.loads(spec_path.read_text(encoding="utf-8")) if spec_path.exists() else None
            if spec is None or spec.get("intent_id") != candidate:
                print(f"NEED_SCENARIOS case {index} intent {candidate}")
                return 2
            code, record = _pipe_run(index, "--review-candidate-id", candidate)
            if code is None:
                return _scenarios(index, case_dir, record, candidate, spec,
                                  len(_replies(case_dir)))
        elif (record["status"] in {"BLOCKED", "WAITING_USER"}
              and record.get("stop_reason") in {"invalid_candidate", "llm_error", "repair_stalled"}
              and retries < MAX_RETRIES and record.get("stop_reason") != "repair_stalled"):
            retries += 1
            code, record = _pipe_run(index)
        else:
            return _finish(case_dir, record, "pipeline_stopped", replies=len(_replies(case_dir)))
        if code is not None:
            return code


def _scenarios(index: int, case_dir: Path, record: dict, candidate: str, spec: dict,
               replies: int) -> int:
    compiled = record.get("steps", {}).get("compile", {})
    if (compiled.get("safe_error") or {}).get("code") in {"provider_request_failed",
                                                           "provider_limit"}:
        # No usable response: infrastructure at first (protocol, section 2), retried by a later
        # run; after MAX_COMPILE_FAILURES such runs the case ends as not delivered.
        failures = sum(
            1 for path in case_dir.glob("attempt-*.json")
            if ((json.loads(path.read_text(encoding="utf-8")).get("steps", {}).get("compile", {})
                 .get("safe_error") or {}).get("code") in {"provider_request_failed",
                                                           "provider_limit"}))
        if failures >= MAX_COMPILE_FAILURES:
            return _finish(case_dir, record, "compile_model_failed", replies=replies)
        print(f"PIPE {case_dir.name}: compile got no model response; resume later")
        return 4
    if compiled.get("run_status") != "SUCCEEDED" or record.get("blocking_step") != "semantic_comparison":
        return _finish(case_dir, record, "pipeline_stopped_before_scenarios", replies=replies)
    contract = compiled["output_artifacts"][0]
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
        if record["status"] != DELIVERED:
            return _finish(case_dir, record, f"scenario_not_delivered:{name}",
                           replies=replies, scenarios=done)
    return _finish(case_dir, record, "all_scenarios_delivered", replies=replies, scenarios=done)


def base(index: int) -> int:
    pipe_final = PIPE_DIR / f"case-{index:03d}" / "final.json"
    if not pipe_final.exists():
        print(f"BASE case-{index:03d}: pipeline arm has not ended")
        return 4
    case_dir = BASE_DIR / f"case-{index:03d}"
    view = user_view(index)
    path = case_dir / "session.json"
    args: list[str] = []
    server_retries = 0
    if not path.exists():
        args = ["--pipeline-case-dir", _rel(PIPE_DIR / f"case-{index:03d}")]
    while True:
        if path.exists():
            session = json.loads(path.read_text(encoding="utf-8"))
            status = session["status"]
            if status in {"accepted", "gave_up", "cap_reached"}:
                print(f"BASE {case_dir.name} END {status} requests "
                      f"{counted_requests(session['call_log'])}/{session['cap']} "
                      f"delivered {session['delivered_contract'] is not None}")
                return 0
            if status == "awaiting_answer":
                last = next(turn for turn in reversed(session["transcript"])
                            if turn["role"] == "assistant")
                kind, message = _take_reply(case_dir, view, [(last["reply"] or {}).get("message", "")])
                if kind == "need":
                    return 5
                args = ["--give-up"] if kind == "giveup" else ["--message-file", _rel(message)]
            elif status in {"awaiting_review", "awaiting_reaction"}:
                args = ["--accept"]
            elif status not in {"running", "provider_limit", "provider_error"}:
                print(f"BASE {case_dir.name}: unexpected status {status}")
                return 4
        result = _wsl("research.experiments.baseline_llm", "--case-index", str(index), *args)
        print(f"  base {' '.join(args) or '(resume)'} -> rc {result.returncode}")
        if result.returncode == 3:
            stopped = json.loads(path.read_text(encoding="utf-8"))["status"]
            if stopped == "provider_error" and server_retries < 3:
                # A provider server error, not quota: wait and resume on the same key.
                import time

                server_retries += 1
                print(f"  provider server error; retry {server_retries} in 60 s")
                time.sleep(60)
                args = []
                continue
            if stopped == "provider_limit" and _rotate():
                args = []  # the session resumes where the quota error stopped it
                continue
            return 3
        if result.returncode != 0:
            print(result.stdout[-1500:], result.stderr[-1500:])
            return 4
        args = []


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.argv[1] == "scen":
        index = int(sys.argv[2])
        case_dir = PIPE_DIR / f"case-{index:03d}"
        record = _last(case_dir)
        if record is None or record["status"] != "WAITING_RESEARCH_REVIEW":
            raise SystemExit("scen: the case is not waiting for intent review")
        candidate = record["steps"]["intent_extraction"]["output_artifacts"][0]
        spec = {"intent_id": candidate, "scenarios": json.loads(sys.argv[3])}
        (case_dir / "scenarios.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1) + "\n",
                                                 encoding="utf-8")
        print(f"scenarios for {candidate}: {', '.join(spec['scenarios'])}")
        raise SystemExit(0)
    if sys.argv[1] == "answer":
        raise SystemExit(answer(sys.argv[2], int(sys.argv[3]), sys.argv[4]))
    raise SystemExit({"pipe": pipe, "base": base}[sys.argv[1]](int(sys.argv[2])))
