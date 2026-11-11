"""What the E6 simulated user may see, and nothing more (docs/E6-Protocol.md, section 3).

  python tools/e6/show.py case N   prompt and fact sheet of dataset v3 case N
  python tools/e6/show.py pipe N   pipeline arm: state, questions, intent under review, ids
  python tools/e6/show.py base N   baseline arm: state and the model's last plain-language message

Never prints spec, reference_contract, checks or expected_behavior, and never the contract JSON.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from research.experiments.baseline_llm import counted_requests  # noqa: E402

VN = timezone(timedelta(hours=7))


def _when(ms: int) -> str:
    moment = datetime.fromtimestamp(ms / 1000, timezone.utc)
    return f"{ms} = {moment:%Y-%m-%d %H:%M} UTC = {moment.astimezone(VN):%Y-%m-%d %H:%M} VN"


def case(index: int) -> None:
    line = (ROOT / "dataset" / "v3" / "cases.jsonl").read_text(encoding="utf-8").splitlines()[index - 1]
    item = json.loads(line)
    print(f"{item['id']} ({item['language']})\nPROMPT: {item['prompt']}")
    for fact in item["fact_sheet"]:
        print(f"FACT [{fact['topic']}]: {fact['answer']}")
    if not item["fact_sheet"]:
        print("FACT: (none)")


def pipe(index: int) -> None:
    case_dir = ROOT / "runs" / "E6-Pipeline" / f"case-{index:03d}"
    paths = sorted(case_dir.glob("attempt-*.json"))
    if not paths:
        print("no pipeline attempt yet")
        return
    total = sum(counted_requests(json.loads(p.read_text(encoding="utf-8"))
                                 .get("model_call_log_this_attempt", [])) for p in paths)
    record = json.loads(paths[-1].read_text(encoding="utf-8"))
    print(f"{paths[-1].name}: {record['status']} / {record.get('stop_reason')} "
          f"at {record.get('blocking_step')}; requests so far {total}")
    for question in record.get("questions") or []:
        print(f"QUESTION: {question}")
    for item in record.get("blocking_diagnostics") or []:
        print(f"DIAG: {item}")
    steps = record.get("steps", {})
    for name, step in steps.items():
        if step.get("run_status") not in {"NOT_EVALUATED", None}:
            print(f"  step {name}: {step['run_status']} {step.get('semantic_status') or ''}")
    candidate = record.get("candidate")
    if isinstance(candidate, dict):
        ids = steps.get("intent_extraction", {}).get("output_artifacts", [])
        print(f"INTENT CANDIDATE: {ids[0] if ids else '?'}")
        core = candidate.get("semantic_core") or {}
        for claim in core.get("claims", []):
            if claim.get("status") in {"superseded", "unresolved"}:
                continue
            value = claim["value"]
            shown = _when(value) if claim["kind"].endswith("_ms") and type(value) is int else \
                json.dumps(value, ensure_ascii=False)
            print(f"  {claim['kind']} = {shown} @ {claim['scope_id']}")
        drafts = candidate.get("fact_drafts") or []
        if drafts:
            draft = drafts[-1]["draft"]
            for step in draft.get("steps", []):
                summary = {key: step[key] for key in ("id", "kind", "by", "into", "amount", "deadline",
                                                      "bounds", "branches", "on_timeout", "then")
                           if key in step}
                print(f"  draft step {json.dumps(summary, ensure_ascii=False)}")
            for outcome in draft.get("outcomes", []):
                summary = {key: outcome[key] for key in outcome if key != "evidence"}
                print(f"  draft outcome {json.dumps(summary, ensure_ascii=False)}")
            notes = draft.get("notes") or {}
            for kind in ("clarifications", "unsupported"):
                for note in notes.get(kind, []):
                    print(f"  note {kind}: {json.dumps(note, ensure_ascii=False)}")
    compiled = steps.get("compile", {}).get("output_artifacts", [])
    if compiled:
        print(f"CONTRACT: {compiled[0]}")


def base(index: int) -> None:
    path = ROOT / "runs" / "E6-Baseline" / f"case-{index:03d}" / "session.json"
    if not path.exists():
        print("no baseline session yet")
        return
    session = json.loads(path.read_text(encoding="utf-8"))
    print(f"{session['status']}; requests {counted_requests(session['call_log'])}/{session['cap']}; "
          f"user turns {session['user_turns']}; forwarded errors {session['forwarded_errors']}; "
          f"delivered {session['delivered_contract'] is not None}")
    last = next((turn for turn in reversed(session["transcript"]) if turn["role"] == "assistant"), None)
    if last is not None:
        reply = last["reply"] or {}
        print(f"MODEL ({reply.get('type')}): {reply.get('message')}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    {"case": case, "pipe": pipe, "base": base}[sys.argv[1]](int(sys.argv[2]))
