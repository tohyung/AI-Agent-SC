"""Turn the user's examples, written in words, into expectation scenarios (E7, Q-KỊCH BẢN 2).

The pipeline asks the user for a few situations and the outcome they expect. A model maps each
situation onto the actions and deadlines of the intent under review; code computes every time and
amount, writes the compact scenario form of `tools/e6/expect.py`, and renders the scenarios back
in words so the user can confirm them before they are run on the contract.

The model may name any party the user mentions, including one the intent lacks, and may use
"notify" (anyone presses) even when the intent has no such step: the scenario follows the user's
words, the intent only supplies names and deadlines (Q-KỊCH BẢN 1).

  python -m research.synthesis.example_scenarios --case-dir DIR --candidate-file F \
      --examples-file F --out F [--provider gemini]
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from typing import Any

from research.formalization.intent_summary import _Summary
from research.formalization.fact_builder import request_language
from research.formalization.party_names import fold_name

PROMPT_VERSION = "E7-ExampleScenarios-v1"
DEADLINE_KINDS = ("deposit_deadline_ms", "choice_deadline_ms", "timeout_ms",
                  "payment_release_time_ms")

SYSTEM = """You turn a user's example situations for a Cardano contract into test scenarios.
You get the parties, the deadlines (D1, D2, ...) and the user's own words. Reply with one JSON
object: {"scenarios": [{"name": "<short_snake_case>", "steps": [...], "receive": [...]}]}.

Each step is one of:
  {"do": "deposit", "party": "<name>", "ada": "<amount>", "before": "<deadline label>"}
  {"do": "deposit", "party": "<name>", "tokens": "<count>", "token": "<token name>", "before": "<label>"}
  {"do": "choose", "party": "<name>", "value": <integer>, "before": "<label>"}
  {"do": "press", "before": "<label>"}      (anyone presses / confirms)
  {"do": "wait", "past": "<label>"}         (nobody acts until that deadline has passed)
"receive" lists what each party receives in total in that situation:
  [{"party": "<name>", "ada": "<amount>"}] or {"party", "tokens", "token"}.

Rules
- Follow the user's words only. Never invent a situation, a party, an amount or a value the user
  did not give. Use the party names as the user writes them.
- Use only the deadline labels given. Never write a date or a time yourself.
- Every situation runs until nothing more can happen: if it ends because someone does not act,
  end it with a "wait" past that deadline.
- A party who gets their own money back receives it too: list it in "receive".
- Write amounts as plain digits with "." as the decimal point."""

WORDS = {
    "vi": {"intro": "Tôi sẽ kiểm tra hợp đồng bằng các tình huống bạn mô tả:",
           "deposit": "{party} nạp {amount} trước {time}",
           "choose": "{party} chọn {value} trước {time}",
           "press": "có người bấm xác nhận trước {time}",
           "wait": "không ai làm gì đến sau {time}",
           "receive": "Kết quả: {items}.", "nothing": "Kết quả: không ai nhận gì.",
           "question": "Các tình huống này có đúng ý bạn không? Nếu sai chỗ nào, xin nói rõ."},
    "en": {"intro": "I will test the contract with the situations you described:",
           "deposit": "{party} deposits {amount} by {time}",
           "choose": "{party} chooses {value} by {time}",
           "press": "someone presses confirm by {time}",
           "wait": "nobody acts until after {time}",
           "receive": "Result: {items}.", "nothing": "Result: nobody receives anything.",
           "question": "Are these situations what you mean? If something is wrong, please say what."},
}


def _deadlines(core: dict[str, Any]) -> dict[str, int]:
    values = sorted({claim["value"] for claim in core.get("claims", [])
                     if claim.get("kind") in DEADLINE_KINDS and type(claim.get("value")) is int})
    return {f"D{number}": value for number, value in enumerate(values, 1)}


def _parties(core: dict[str, Any]) -> list[str]:
    kinds = {"depositing_party", "destination_account_owner", "choice_owner",
             "payment_recipient", "refund_recipient", "release_recipient",
             "payment_source_account_owner"}
    return sorted({claim["value"] for claim in core.get("claims", [])
                   if claim.get("kind") in kinds and isinstance(claim.get("value"), str)})


def _language(core: dict[str, Any]) -> str:
    return request_language([message for version in core.get("requirement_history", [])
                             for message in version.get("messages", [])])


def build_prompt(core: dict[str, Any], examples: str) -> tuple[str, str]:
    summary = _Summary(core, _language(core))
    lines = ["Parties: " + ", ".join(_parties(core)), "Deadlines:"]
    lines += [f"  {label}: {summary.time(value)}" for label, value in _deadlines(core).items()]
    lines += ["", "The user's situations:", examples.strip()]
    return SYSTEM, "\n".join(lines)


def _decimal(text: Any) -> Decimal | None:
    try:
        value = Decimal(str(text).replace(",", "."))
    except InvalidOperation:
        return None
    return value if value.is_finite() and value >= 0 else None


def _account_for(core: dict[str, Any], party: str) -> str:
    """The account the intent deposits a party's money into, by folded name; else the party."""
    claims = core.get("claims", [])
    for claim in claims:
        if claim.get("kind") == "depositing_party" and fold_name(str(claim.get("value"))) == \
                fold_name(party):
            owner = next((item["value"] for item in claims if item["scope_id"] == claim["scope_id"]
                          and item["kind"] == "destination_account_owner"), None)
            if isinstance(owner, str):
                return owner
    return party


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat(timespec="milliseconds")


def to_compact(core: dict[str, Any], reply: Any, tokens: dict[str, list[str]] | None = None
               ) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Compact scenarios (tools/e6/expect.py form) and the problems that dropped any of them.

    `tokens` maps a token name to [currency_symbol, token_name] from the intent's assets."""
    deadlines = _deadlines(core)
    tokens = tokens or {}
    scenarios: dict[str, dict[str, Any]] = {}
    problems: list[str] = []
    items = reply.get("scenarios") if isinstance(reply, dict) else None
    if not isinstance(items, list) or not items:
        return {}, ["reply has no scenarios"]
    for number, item in enumerate(items, 1):
        name = str(item.get("name") or f"situation_{number}")
        try:
            tx = []
            for step in item.get("steps") or []:
                label = step.get("before") or step.get("past")
                if label not in deadlines:
                    raise ValueError(f"unknown deadline {label!r}")
                at = _iso(deadlines[label])
                kind = step.get("do")
                if kind == "deposit":
                    party = str(step["party"])
                    if "tokens" in step:
                        token = tokens.get(str(step.get("token")))
                        if token is None:
                            raise ValueError(f"unknown token {step.get('token')!r}")
                        tx.append([at, [["deposit", party, _account_for(core, party), 0,
                                         [*token, int(step["tokens"])]]]])
                    else:
                        amount = _decimal(step.get("ada"))
                        if amount is None:
                            raise ValueError(f"bad amount {step.get('ada')!r}")
                        tx.append([at, [["deposit", party, _account_for(core, party),
                                         float(amount)]]])
                elif kind == "choose":
                    tx.append([at, [["choice", str(step["party"]), int(step["value"])]]])
                elif kind == "press":
                    tx.append([at, [["notify"]]])
                elif kind == "wait":
                    tx.append([at, []])
                else:
                    raise ValueError(f"unknown step {kind!r}")
            pay = []
            for row in item.get("receive") or []:
                party = str(row["party"])
                if "tokens" in row:
                    token = tokens.get(str(row.get("token")))
                    if token is None:
                        raise ValueError(f"unknown token {row.get('token')!r}")
                    pay.append([party, party, 0, [*token, int(row["tokens"])]])
                else:
                    amount = _decimal(row.get("ada"))
                    if amount is None:
                        raise ValueError(f"bad amount {row.get('ada')!r}")
                    if amount:
                        pay.append([party, party, float(amount)])
            if not tx:
                raise ValueError("no steps")
            scenarios[name] = {"tx": tx, "pay": pay}
        except (KeyError, TypeError, ValueError) as exc:
            problems.append(f"{name}: {exc}")
    return scenarios, problems


def describe(core: dict[str, Any], scenarios: dict[str, dict[str, Any]]) -> str:
    """The scenarios in the user's language, for the user to confirm."""
    language = _language(core)
    words = WORDS[language]
    summary = _Summary(core, language)

    def amount(value: Any, token: list | None) -> str:
        if token:
            return f"{token[2]} {token[1]}"
        return f"{Decimal(str(value)).normalize():f} ADA"

    lines = [words["intro"]]
    for number, (name, compact) in enumerate(scenarios.items(), 1):
        steps = []
        for at, inputs in compact["tx"]:
            time = summary.time(int(datetime.fromisoformat(at).timestamp() * 1000))
            if not inputs:
                steps.append(words["wait"].format(time=time))
            for item in inputs:
                if item[0] == "deposit":
                    steps.append(words["deposit"].format(
                        party=item[1], amount=amount(item[3], item[4] if len(item) > 4 else None),
                        time=time))
                elif item[0] == "choice":
                    steps.append(words["choose"].format(party=item[1], value=item[2], time=time))
                else:
                    steps.append(words["press"].format(time=time))
        received = [f"{row[1]} {amount(row[2], row[3] if len(row) > 3 else None)}"
                    for row in compact["pay"]]
        result = (words["receive"].format(items=", ".join(received)) if received
                  else words["nothing"])
        lines.append(f"{number}. " + "; ".join(steps) + ". " + result)
    lines.append(words["question"])
    return "\n".join(lines)


REQUEST = {
    "vi": {"intro": "Để kiểm tra hợp đồng, xin mô tả 2 đến 4 tình huống và kết quả bạn mong muốn: "
                    "ai làm gì, trước hạn nào, và cuối cùng mỗi người nhận bao nhiêu.",
           "timeout": "Có ít nhất một tình huống có người không làm kịp hạn.",
           "choice": "Có các lựa chọn khác nhau của {owners}.",
           "notify": "Có tình huống có người bấm và tình huống không ai bấm.",
           "many": "Nếu nhiều người cùng có thể làm một việc, cho hai tình huống với hai người khác nhau."},
    "en": {"intro": "To test the contract, please describe 2 to 4 situations and the outcome you "
                    "expect: who does what, before which deadline, and what each person receives in the end.",
           "timeout": "Include at least one situation where someone misses a deadline.",
           "choice": "Include different choices by {owners}.",
           "notify": "Include one situation where someone presses and one where nobody does.",
           "many": "If several people can do the same thing, give two situations with two different people."},
}


def examples_request(core: dict[str, Any]) -> str:
    """The pipeline's request for examples, shaped by the intent (Q-KỊCH BẢN 3)."""
    language = _language(core)
    words = REQUEST[language]
    kinds = {scope.get("transition_kind") for scope in core.get("behavior_scopes", [])
             if scope.get("scope_type") == "transition"}
    owners = sorted({claim["value"] for claim in core.get("claims", [])
                     if claim.get("kind") == "choice_owner" and isinstance(claim.get("value"), str)})
    lines = [words["intro"], "- " + words["timeout"]]
    if owners:
        lines.append("- " + words["choice"].format(owners=", ".join(owners)))
    if "notify" in kinds:
        lines.append("- " + words["notify"])
    lines.append("- " + words["many"])
    return "\n".join(lines)


def _token_table(intent_spec: dict[str, Any]) -> dict[str, list[str]]:
    table: dict[str, list[str]] = {}
    for claim in intent_spec.get("claims", []):
        value = claim.get("value")
        if claim.get("kind") == "asset" and isinstance(value, str) and value.startswith("native:"):
            policy, _, hex_name = value[len("native:"):].partition("/")
            try:
                name = bytes.fromhex(hex_name).decode("utf-8")
            except ValueError:
                continue
            table[name] = [policy, name]
    return table


def main() -> int:
    from research.experiments.baseline_llm import _transport

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--candidate-file", type=Path, required=True,
                        help="attempt record whose candidate is under review")
    parser.add_argument("--examples-file", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--provider", default="gemini")
    args = parser.parse_args()
    record = json.loads(args.candidate_file.read_text(encoding="utf-8"))
    core = record["candidate"]["semantic_core"]
    examples = args.examples_file.read_text(encoding="utf-8")
    model = _transport(args.case_dir, record.get("case_id", ""), args.provider)
    system, user = build_prompt(core, examples)
    from research.adapters.model_transport import ModelTransportError

    reply: Any = None
    error = None
    try:
        reply = model.generate(system, user)
    except ModelTransportError as exc:
        error = exc.code
    scenarios, problems = ({}, [f"model error {error}"]) if error else to_compact(
        core, reply, _token_table(record["candidate"]["intent_spec"]))
    result = {"prompt_version": PROMPT_VERSION, "examples": examples, "reply": reply,
              "error": error, "scenarios": scenarios, "problems": problems,
              "readback": describe(core, scenarios) if scenarios else None,
              "model_call_log": [dict(entry) for entry in getattr(model, "call_log", [])],
              "recorded_at_utc": datetime.now(timezone.utc).isoformat()}
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"scenarios": list(scenarios), "problems": problems, "error": error},
                     ensure_ascii=False))
    return 3 if error in {"provider_limit"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
