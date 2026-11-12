"""Audit one sim-user subagent turn and record its reply (E7 protocol, section 2.3).

  python tools/e7/audit_agent.py AGENT_ID pipe|base N

The subagent is told to read its own input file (`simuser-input.txt` of case N) with the Read
tool, so the long input is not pasted through the operator. Its transcript is then checked:
- every assistant message comes from claude-haiku-5-5 at effort medium;
- its only tool calls are one Read of exactly that input file and one SubagentHandback;
- the handback carries the reply.
If the turn is valid, its reply is recorded verbatim with `tools/e7/auto.py reply`; otherwise
nothing is recorded and the problems are printed (call a new subagent, and log the invalid turn).
Exit codes: 0 recorded, 6 the reply checker rejected it (call a new subagent), 7 invalid turn.
"""

from __future__ import annotations

import glob
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
PROJECTS = Path.home() / ".claude" / "projects"
MODEL = "claude-haiku-5-5"


def _transcript(agent_id: str) -> Path:
    found = glob.glob(str(PROJECTS / "*" / "*" / "subagents" / f"agent-{agent_id}.jsonl"))
    if len(found) != 1:
        raise SystemExit(f"transcript for agent {agent_id} not found ({len(found)} matches)")
    return Path(found[0])


def audit(agent_id: str, input_file: Path) -> tuple[list[str], str | None]:
    problems: list[str] = []
    reads: list[str] = []
    handbacks: list[str] = []
    others: list[str] = []
    models: set[str] = set()
    for line in _transcript(agent_id).read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        message = entry.get("message") or {}
        if entry.get("type") != "assistant":
            continue
        models.add(str(message.get("model")))
        for item in message.get("content") or []:
            if not isinstance(item, dict) or item.get("type") != "tool_use":
                continue
            name, payload = item.get("name"), item.get("input") or {}
            if name == "Read":
                reads.append(str(payload.get("file_path", "")))
            elif name == "SubagentHandback":
                handbacks.append(str(payload.get("message", "")))
            else:
                others.append(str(name))
    if models != {MODEL}:
        problems.append(f"models {sorted(models)}, expected {MODEL}")
    expected = os.path.normcase(os.path.abspath(input_file))
    if [os.path.normcase(os.path.abspath(path)) for path in reads] != [expected]:
        problems.append(f"reads {reads}, expected exactly one read of {input_file}")
    if others:
        problems.append(f"other tools used: {others}")
    if len(handbacks) != 1:
        problems.append(f"{len(handbacks)} handbacks, expected 1")
    return problems, (handbacks[0].strip() if len(handbacks) == 1 else None)


def main() -> int:
    agent_id, arm, index = sys.argv[1], sys.argv[2], int(sys.argv[3])
    dataset = os.environ.get("E7_DATASET", "v4")
    suffix = "" if dataset == "v4" else "-Eval"
    case_dir = ROOT / "runs" / f"E7{suffix}-{'Pipeline' if arm == 'pipe' else 'Baseline'}" / f"case-{index:03d}"
    problems, raw = audit(agent_id, case_dir / "simuser-input.txt")
    log_path = case_dir / "subagent-audit.jsonl"
    with log_path.open("a", encoding="utf-8") as writer:
        writer.write(json.dumps({"agent_id": agent_id, "problems": problems, "raw": raw},
                                ensure_ascii=False) + "\n")
    if problems:
        print("INVALID " + "; ".join(problems))
        return 7
    result = subprocess.run([sys.executable, str(ROOT / "tools" / "e7" / "auto.py"), "reply", arm,
                             str(index), raw], capture_output=True, text=True, encoding="utf-8",
                            env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    print(result.stdout.strip(), result.stderr.strip()[-300:])
    return result.returncode


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
