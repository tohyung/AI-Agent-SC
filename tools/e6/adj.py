"""E6 blind adjudication helper. Never reads blind-key.json.

  python tools/e6/adj.py show FROM TO      packets FROM..TO (1-based, shuffled order)
  python tools/e6/adj.py set CODE RIGHT|WRONG|UND|NONE TOLD "reason"
                                           TOLD = 1 if the arm told the user a part cannot be done
  python tools/e6/adj.py todo              codes still without a verdict
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "runs" / "E6-Adjudication"
VERDICTS = DIR / "verdicts.json"
VN = timezone(timedelta(hours=7))
ADA = {"currency_symbol": "", "token_name": ""}


def _packets() -> list[dict]:
    return [json.loads(line) for line in (DIR / "packets.jsonl").read_text(encoding="utf-8").splitlines()]


def _when(ms) -> str:
    if type(ms) is not int:
        return json.dumps(ms)
    moment = datetime.fromtimestamp(ms / 1000, timezone.utc)
    return f"{moment:%Y-%m-%d %H:%M}Z ({moment.astimezone(VN):%m-%d %H:%M} VN)"


def _party(p) -> str:
    if isinstance(p, dict) and "role_token" in p:
        return p["role_token"]
    if isinstance(p, dict) and "address" in p:
        return f"addr:{p['address']}"
    return json.dumps(p, ensure_ascii=False)


def _token(t) -> str:
    return "ADA" if t == ADA else f"{t.get('token_name')}@{str(t.get('currency_symbol'))[:6]}"


def _value(v, token=None) -> str:
    if type(v) is int:
        return f"{v / 1_000_000:g} ADA" if token == ADA else str(v)
    if isinstance(v, dict):
        if "value_of_choice" in v:
            c = v["value_of_choice"]
            return f"choice({c.get('choice_name')}/{_party(c.get('choice_owner'))})"
        if "amount_of_token" in v:
            return f"balance({_party(v.get('in_account'))},{_token(v['amount_of_token'])})"
        if "use_value" in v:
            return f"let:{v['use_value']}"
        for op, sym in (("add", "+"), ("and", "-"), ("times", "*")):
            pass
    return json.dumps(v, ensure_ascii=False)


def _obs(o) -> str:
    return json.dumps(o, ensure_ascii=False) if not isinstance(o, bool) else str(o)


def render(c, depth: int = 0) -> list[str]:
    pad = "  " * depth
    if c == "close":
        return [pad + "Close"]
    if not isinstance(c, dict):
        return [pad + json.dumps(c, ensure_ascii=False)]
    if "pay" in c:
        to = c["to"]
        dest = f"party {_party(to['party'])}" if "party" in to else f"account {_party(to.get('account'))}"
        return [pad + f"Pay {_value(c['pay'], c.get('token'))} {_token(c.get('token', {}))} "
                      f"from {_party(c['from_account'])} to {dest}"] + render(c["then"], depth)
    if "when" in c:
        lines = [pad + f"When (timeout {_when(c.get('timeout'))}):"]
        for case in c["when"]:
            action = case.get("case", {})
            if "deposits" in action:
                head = (f"Deposit {_value(action['deposits'], action.get('of_token'))} "
                        f"{_token(action.get('of_token', {}))} by {_party(action['party'])} "
                        f"into {_party(action['into_account'])}")
            elif "for_choice" in action:
                fc = action["for_choice"]
                head = (f"Choice '{fc.get('choice_name')}' by {_party(fc.get('choice_owner'))} "
                        f"in {[(b['from'], b['to']) for b in action.get('choose_between', [])]}")
            elif "notify_if" in action:
                head = f"Notify if {_obs(action['notify_if'])}"
            else:
                head = json.dumps(action, ensure_ascii=False)
            lines.append(pad + "  case " + head + " ->")
            lines += render(case.get("then"), depth + 2)
        lines.append(pad + "  on timeout ->")
        lines += render(c.get("timeout_continuation"), depth + 2)
        return lines
    if "if" in c:
        return ([pad + f"If {_obs(c['if'])}:"] + render(c["then"], depth + 1)
                + [pad + "Else:"] + render(c["else"], depth + 1))
    if "let" in c:
        return [pad + f"Let {c['let']} = {_value(c['be'])}"] + render(c["then"], depth)
    if "assert" in c:
        return [pad + f"Assert {_obs(c['assert'])}"] + render(c["then"], depth)
    return [pad + json.dumps(c, ensure_ascii=False)[:400]]


def show(first: int, last: int) -> None:
    packets = _packets()
    done = json.loads(VERDICTS.read_text(encoding="utf-8")) if VERDICTS.exists() else {}
    for number, packet in enumerate(packets[first - 1:last], first):
        print(f"===== #{number} code {packet['code']} case {packet['case_index']} {packet['case_id']}"
              f"{'  [done]' if packet['code'] in done else ''}")
        print("PROMPT:", packet["prompt"])
        for fact in packet["fact_sheet"]:
            print("FACT:", fact["answer"])
        for message in packet["user_messages"]:
            print("USER SAID:", message.replace("\n", " | "))
        print("FINAL MESSAGE:", (packet["final_message"] or "").replace("\n", " | ")[:600])
        if packet["contract"] is None:
            print("CONTRACT: (none delivered)")
        else:
            print("\n".join(render(packet["contract"])))


def set_verdict(code: str, contract: str, told: str, reason: str) -> None:
    codes = {packet["code"] for packet in _packets()}
    if code not in codes:
        raise SystemExit(f"unknown code {code}")
    mapping = {"RIGHT": "RIGHT", "WRONG": "WRONG", "UND": "UNDETERMINED", "NONE": None}
    done = json.loads(VERDICTS.read_text(encoding="utf-8")) if VERDICTS.exists() else {}
    done[code] = {"contract": mapping[contract], "told_unsupported": told == "1", "reason": reason}
    VERDICTS.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    command = sys.argv[1]
    if command == "show":
        show(int(sys.argv[2]), int(sys.argv[3]))
    elif command == "set":
        set_verdict(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
    elif command == "bulk":
        # one verdict per stdin line: CODE|RIGHT|WRONG|UND|NONE|TOLD|reason
        for line in sys.stdin.read().splitlines():
            if line.strip():
                code, contract, told, reason = line.split("|", 3)
                set_verdict(code.strip(), contract.strip(), told.strip(), reason.strip())
        done = json.loads(VERDICTS.read_text(encoding="utf-8"))
        print(len(done), "verdicts recorded")
    elif command == "todo":
        done = json.loads(VERDICTS.read_text(encoding="utf-8")) if VERDICTS.exists() else {}
        todo = [number for number, packet in enumerate(_packets(), 1) if packet["code"] not in done]
        print(len(todo), "left:", todo[:40])
