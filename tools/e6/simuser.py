"""Inputs and checks for the sim-user subagent (.claude/agents/sim-user.md, SimUser-v1).

  python tools/e6/simuser.py input N base|pipe [--turn K]   print the subagent's input for case N
  python tools/e6/simuser.py check N 'JSON' [base|pipe]      check a reply (format, language, unknown numbers)

The input holds only what a real user has: their own request, what they know (the fact sheet), and the
assistant's visible messages (no JSON, no POSIX times, no diagnostics). It never reads the evaluator
fields (spec, reference_contract, checks, expected_behavior, author_note).
--turn K stops the history at the assistant's K-th message (default: the latest).
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
DATASET = ROOT / "dataset" / "v3" / "cases.jsonl"
ACTIONS = {"answer", "accept", "object", "give_up"}


def user_view(index: int) -> dict:
    line = DATASET.read_text(encoding="utf-8").splitlines()[index - 1]
    case = json.loads(line)
    return {"prompt": case["prompt"], "language": case["language"],
            "facts": [item["answer"] for item in case.get("fact_sheet", [])]}


def baseline_history(index: int) -> list[tuple[str, str]]:
    session = json.loads((ROOT / "runs" / "E6-Baseline" / f"case-{index:03d}" / "session.json")
                         .read_text(encoding="utf-8"))
    history = []
    for turn in session["transcript"][1:]:
        if turn["role"] == "assistant":
            reply = turn.get("reply")
            text = reply.get("message", "") if isinstance(reply, dict) else "(no readable reply)"
            kind = reply.get("type") if isinstance(reply, dict) else None
            if kind == "contract":
                text = "[RESULT: the assistant delivered a contract and says:] " + text
            history.append(("assistant", text))
        elif turn.get("source") == "forwarded_error":
            history.append(("you", "(you pasted the error message from the contract checker)"))
        else:
            history.append(("you", turn["content"]))
    return history


def pipeline_history(index: int) -> list[tuple[str, str]]:
    case_dir = ROOT / "runs" / "E6-Pipeline" / f"case-{index:03d}"
    replies_path = case_dir / "replies.json"
    replies = json.loads(replies_path.read_text(encoding="utf-8")) if replies_path.exists() else []
    history = []
    for number, reply in enumerate(replies):
        history.append(("assistant", "\n".join(reply.get("questions") or [])))
        if reply.get("text"):
            history.append(("you", reply["text"]))
        elif number == len(replies) - 1:
            history.append(("you", "(you gave up)"))
    return history


def render_input(index: int, arm: str, turn: int | None) -> str:
    view = user_view(index)
    history = baseline_history(index) if arm == "base" else pipeline_history(index)
    if turn is not None:
        cut, seen = [], 0
        for item in history:
            if item[0] == "assistant":
                seen += 1
                if seen > turn:
                    break
            cut.append(item)
        history = cut
        while history and history[-1][0] != "assistant":
            history.pop()
    language = "Vietnamese" if view["language"] == "vi" else "English"
    lines = [f"YOUR LANGUAGE: {language}", "",
             "WHAT YOU WANT (your own first message):", view["prompt"], "",
             "WHAT YOU KNOW (facts you can give if asked):"]
    lines += [f"- {fact}" for fact in view["facts"]] or ["- (nothing beyond your request)"]
    lines += ["", "CONVERSATION SO FAR:"]
    lines += [f"{who.upper()}: {text}" for who, text in history]
    lines += ["", "Write your next message now, as the JSON object."]
    return "\n".join(lines)


def _numbers(text: str) -> set[str]:
    from research.formalization.number_words import digits_for_words

    text = digits_for_words(text)
    return {re.sub(r"[.,\s]", "", match) for match in re.findall(r"\d[\d.,]*", text)}


VIETNAMESE_MARKS = re.compile("[ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ]",
                              re.IGNORECASE)
VIETNAMESE_WORDS = {"toi", "minh", "khong", "ban", "cua", "cho", "duoc", "nhe", "hop", "dong", "tien"}


def check(index: int, raw: str, arm: str | None = None) -> list[str]:
    """Problems with a reply: bad JSON, unknown action, wrong language, or numbers the user never saw."""
    try:
        reply = json.loads(raw)
    except json.JSONDecodeError as exc:
        return [f"not JSON: {exc}"]
    problems = []
    if reply.get("action") not in ACTIONS:
        problems.append(f"unknown action {reply.get('action')!r}")
    view = user_view(index)
    message = str(reply.get("message", ""))
    words = set(re.findall(r"[a-z]+", message.lower()))
    if view["language"] == "en" and (VIETNAMESE_MARKS.search(message) or len(words & VIETNAMESE_WORDS) >= 2):
        problems.append("reply is not in English")
    seen = ""
    if arm is not None:
        history = baseline_history(index) if arm == "base" else pipeline_history(index)
        seen = " ".join(text for who, text in history if who == "assistant")
    known = " ".join([view["prompt"], *view["facts"], seen])
    known_numbers = _numbers(known) | {n.lstrip("0") for n in _numbers(known)}
    for number in _numbers(message):
        if number not in known_numbers and number.lstrip("0") not in known_numbers:
            problems.append(f"number {number} is not in the request or the fact sheet")
    if agrees_to_drop(message) and not any(DROP_PERMISSION.search(fact) for fact in view["facts"]):
        problems.append("agrees to drop part of the request, but the fact sheet does not allow it")
    return problems


# Agreement to drop a part (Q-NGƯỜI DÙNG 3). "Không cần bỏ" / "don't drop" keep it.
DROP_AGREEMENT = re.compile(
    r"(có thể bỏ|co the bo|cứ bỏ|cu bo|bỏ (?:phần|phan|đi|di|cũng được|qua)|bo (?:phan|di|qua)|"
    r"đồng ý bỏ|dong y bo|không cần (?:phần|phan|nhập|nhap|cái|cai)|khong can (?:phan|nhap|cai)|"
    r"(?:you can|can|ok to|okay to|fine to) (?:drop|skip|remove)|drop it|skip it|remove it|"
    r"don't need (?:it|that|this))", re.IGNORECASE)
KEEP = re.compile(r"(không cần bỏ|khong can bo|đừng bỏ|dung bo|không bỏ|khong bo|"
                  r"don't drop|do not drop|not drop|keep it)", re.IGNORECASE)
DROP_PERMISSION = re.compile(r"(\bbỏ\b|\bbo\b|bỏ qua|drop|skip|leave out|leave it out)", re.IGNORECASE)


def agrees_to_drop(message: str) -> bool:
    return bool(DROP_AGREEMENT.search(message)) and not KEEP.search(message)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    command, case = sys.argv[1], int(sys.argv[2])
    if command == "input":
        turn = int(sys.argv[sys.argv.index("--turn") + 1]) if "--turn" in sys.argv else None
        print(render_input(case, sys.argv[3], turn))
    elif command == "check":
        found = check(case, sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
        print("OK" if not found else "\n".join(found))
