"""A2 Stage 2B extraction: the model writes a FactDraft v5, code builds the core.

Repairs address atomic draft items only (`DraftError`). A core the builder made
that the v4 validator still rejects is a builder bug and is never sent back to
the model. Examples in the prompt are synthetic, never dataset cases.
"""

from __future__ import annotations

import json
from typing import Any

from research.stage2b.fact_builder import FACT_DRAFT_VERSION, DraftError, build_core
from research.stage2b.intent_spec import validate_intent_spec
from research.stage2b.projector import classify_projection, project_intent_spec

FACT_PROMPT_VERSION = "stage2b-fact-prompt-v1"

SYSTEM = f"""You read a request for a Cardano Marlowe contract and write a FactDraft
({FACT_DRAFT_VERSION}) as one JSON object. Code computes every amount, time and
graph edge from your draft, so never do arithmetic, unit conversion or time zone
conversion yourself.

Rules
- Every item has an "id" and "evidence": a nonempty list of
  {{"requirement_version": V, "message_index": I, "span": "<exact substring>"}}.
  Copy spans character for character from the request.
- Every literal you write (a name, an amount, a count, a date part, a number of
  days) must appear inside that item's own spans.
- Write only what the request says. If a fact is missing, use {{"unknown": true}}
  and add a question in notes.clarifications. Never guess a time of day, a time
  zone, a token policy id or a rounding rule.
- If the request states different values for one fact, give "alternatives"
  instead of "expr": [{{"expr": ..., "evidence": [...]}}, ...]. If it names
  different parties for one role, give a list of party ids.

Fields
- "schema_version": "{FACT_DRAFT_VERSION}"
- "parties": [{{"id", "name", "evidence"}}]
- "assets": [{{"id", "ada": true, "evidence"}}] for ADA, and
  [{{"id", "name": "<token name as written>", "native": "native:<56-hex policy>/<hex of name>" or null,
  "evidence"}}] for a native token. "native" is null unless the policy id is written.
- "quantities": [{{"id", "expr", "evidence"}}] where expr is one of
  {{"ada": "60"}}, {{"lovelace": "1500000"}}, {{"tokens": "5", "asset": "<asset id>"}},
  {{"sum": ["q_a", "q_b"]}}, {{"subtract": {{"from": "q_a", "minus": ["q_b"]}}}},
  {{"times": {{"of": "q_unit", "count": 3}}}},
  {{"fraction": {{"of": "q_total", "num": 1, "den": 2}}}} (also percentages: num 5, den 100),
  {{"unknown": true}}, or {{"dynamic": "<what decides it while the contract runs>"}}.
- "instants": [{{"id", "expr", "evidence"}}] where expr is one of
  {{"date": {{"y", "m", "d", "h", "min", "tz": "+07:00"}}}} (h, min or tz null when not written),
  {{"offset": {{"from": "<instant id>", "days": 7}}}}, or {{"unknown": true}}.
- "steps": ordered actions, linked by id. Kinds:
  deposit {{"by", "into", "amount", "deadline", "then", "on_timeout"}};
  choice {{"by", "deadline", "bounds": {{"from", "to"}},
          "branches": [{{"guard": {{"op": "ge|gt|le|lt|eq", "value"}}, "then"}}], "on_timeout"}};
  notify {{"deadline", "then", "on_timeout"}};
  wait_until {{"at": "<instant id>", "then"}} for "not before" release times.
  "then"/"on_timeout" is "end" or a list of outcome ids optionally ending with one step id.
- "outcomes": [{{"id", "kind": "payment|refund|release", "from_account": "<party id>",
  "to": "<party id>", "amount": "<quantity id>" or "remaining", "asset": "<asset id, only
  with remaining>", "evidence"}}]. "remaining" is whatever is left in that account on that path.
- "notes": {{"clarifications": [{{"target_id", "question"}}],
  "unsupported": [{{"kind": "ledger_history_deletion" or "other", "text", "evidence"}}],
  "resolution_hint": "accept|clarify|conflict|unsupported"}}.
  Write questions in the language of the request.

Do not write scope ids, claim ids, lovelace values or POSIX times."""

EXAMPLE_REQUEST = (
    "Lan thuê Tú làm hai giai đoạn, tổng 60 ADA, Lan nạp trước 00:00 ngày 02/03/2027 "
    "(UTC+7). Lan duyệt giai đoạn một trong năm ngày sau hạn nạp thì Tú nhận một nửa; "
    "duyệt phần còn lại trong mười ngày sau hạn nạp thì nhận nốt. "
    "Phần chưa duyệt hoàn cho Lan."
)


def _ev(*spans: str) -> list[dict[str, Any]]:
    return [{"requirement_version": 1, "message_index": 0, "span": span} for span in spans]


EXAMPLE_DRAFT = {
    "schema_version": FACT_DRAFT_VERSION,
    "parties": [{"id": "p_lan", "name": "Lan", "evidence": _ev("Lan thuê Tú")},
                {"id": "p_tu", "name": "Tú", "evidence": _ev("Lan thuê Tú")}],
    "assets": [{"id": "a_ada", "ada": True, "evidence": _ev("tổng 60 ADA")}],
    "quantities": [
        {"id": "q_total", "expr": {"ada": "60"}, "evidence": _ev("tổng 60 ADA")},
        {"id": "q_half", "expr": {"fraction": {"of": "q_total", "num": 1, "den": 2}},
         "evidence": _ev("Tú nhận một nửa")},
        {"id": "q_rest", "expr": {"subtract": {"from": "q_total", "minus": ["q_half"]}},
         "evidence": _ev("duyệt phần còn lại")}],
    "instants": [
        {"id": "i_d1", "expr": {"date": {"y": 2027, "m": 3, "d": 2, "h": 0, "min": 0,
                                         "tz": "+07:00"}},
         "evidence": _ev("00:00 ngày 02/03/2027 (UTC+7)")},
        {"id": "i_d2", "expr": {"offset": {"from": "i_d1", "days": 5}},
         "evidence": _ev("trong năm ngày sau hạn nạp")},
        {"id": "i_d3", "expr": {"offset": {"from": "i_d1", "days": 10}},
         "evidence": _ev("trong mười ngày sau hạn nạp")}],
    "steps": [
        {"id": "s1", "kind": "deposit", "by": "p_lan", "into": "p_lan", "amount": "q_total",
         "deadline": "i_d1", "on_timeout": "end", "then": ["s2"],
         "evidence": _ev("Lan nạp trước 00:00 ngày 02/03/2027")},
        {"id": "s2", "kind": "choice", "by": "p_lan", "deadline": "i_d2",
         "bounds": {"from": 1, "to": 1},
         "branches": [{"guard": {"op": "eq", "value": 1}, "then": ["o_pay1", "s3"]}],
         "on_timeout": ["o_refund_all"], "evidence": _ev("Lan duyệt giai đoạn một")},
        {"id": "s3", "kind": "choice", "by": "p_lan", "deadline": "i_d3",
         "bounds": {"from": 1, "to": 1},
         "branches": [{"guard": {"op": "eq", "value": 1}, "then": ["o_pay2"]}],
         "on_timeout": ["o_refund_rest"], "evidence": _ev("duyệt phần còn lại")}],
    "outcomes": [
        {"id": "o_pay1", "kind": "payment", "from_account": "p_lan", "to": "p_tu",
         "amount": "q_half", "evidence": _ev("Tú nhận một nửa")},
        {"id": "o_pay2", "kind": "payment", "from_account": "p_lan", "to": "p_tu",
         "amount": "q_rest", "evidence": _ev("nhận nốt")},
        {"id": "o_refund_all", "kind": "refund", "from_account": "p_lan", "to": "p_lan",
         "amount": "remaining", "evidence": _ev("Phần chưa duyệt hoàn cho Lan")},
        {"id": "o_refund_rest", "kind": "refund", "from_account": "p_lan", "to": "p_lan",
         "amount": "remaining", "evidence": _ev("Phần chưa duyệt hoàn cho Lan")}],
    "notes": {"clarifications": [], "unsupported": [], "resolution_hint": "accept"},
}


def build_prompt(history: list[dict[str, Any]]) -> tuple[str, str]:
    example = {"requirement_history": [{"version": 1, "messages": [EXAMPLE_REQUEST]}],
               "draft": EXAMPLE_DRAFT}
    user = ("Synthetic example (not the request below):\n"
            + json.dumps(example, ensure_ascii=False)
            + "\n\nRequest:\n"
            + json.dumps({"requirement_history": history}, ensure_ascii=False)
            + "\n\nReturn only the FactDraft JSON object for this request.")
    return SYSTEM, user


def repair_prompt(history: list[dict[str, Any]], draft: Any,
                  problems: list[tuple[str, str]]) -> tuple[str, str]:
    system, user = build_prompt(history)
    listed = "\n".join(f"- {item}: {message}" for item, message in problems)
    return system, (user + "\n\nYour previous draft:\n" + json.dumps(draft, ensure_ascii=False)
                    + "\n\nCode rejected these items:\n" + listed
                    + "\n\nReturn the whole corrected draft. Change only the listed items "
                      "and what they reference; keep every other item as it was.")


def _check_core(core: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any]:
    projection = project_intent_spec(core, expected_history=history)
    core_errors = projection.projection_diagnostics.get("core_validation_errors", [])
    full_errors = [] if core_errors else validate_intent_spec(
        projection.intent_spec.to_dict(), expected_history=history, projected_core=core)
    return {"core_validation_errors": core_errors, "full_validation_errors": full_errors,
            "projection_classification": classify_projection(
                core_errors, full_errors, projection.projection_diagnostics)}


def extract_fact_core(model: Any, history: list[dict[str, Any]], *,
                      max_repairs: int = 3) -> dict[str, Any]:
    """Return drafts, per-attempt draft problems, and the built core with its checks.

    Model transport errors propagate to the caller unchanged.
    """
    attempts: list[dict[str, Any]] = []
    system, user = build_prompt(history)
    for attempt in range(max_repairs + 1):
        draft = model.generate(system, user)
        try:
            if not isinstance(draft, dict):
                raise DraftError([("draft", "must be a JSON object")])
            core = build_core(draft, history)
        except DraftError as exc:
            attempts.append({"draft": draft, "problems": [list(item) for item in exc.problems]})
            if attempt == max_repairs:
                break
            system, user = repair_prompt(history, draft, exc.problems)
            continue
        checks = _check_core(core, history)
        attempts.append({"draft": draft, "problems": []})
        # A rejected core here is a builder bug: report it, never repair it via the model.
        return {"attempts": attempts, "semantic_core": core,
                "builder_bug": checks["projection_classification"] != "PASS", **checks}
    return {"attempts": attempts, "semantic_core": None, "builder_bug": False,
            "core_validation_errors": [], "full_validation_errors": [],
            "projection_classification": "DRAFT_INVALID"}
