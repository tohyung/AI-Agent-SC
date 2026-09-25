from __future__ import annotations

import json
from typing import Any

from marlowe_agent.openai_reasoner import parse_json_text

from .narrator import narrate


def judge(case: Any, contract: Any, transcript: list[dict[str, Any]], reasoner: Any) -> dict[str, Any]:
    payload = {"prompt": case.prompt, "qa_transcript": transcript,
               "hidden_facts": case.hidden_facts, "contract_description": narrate(contract)}
    system = ("Independently compare the customer's intent with the deterministic description of every "
              "contract path. Return JSON only: score (0-100), matches, mismatches, missing, "
              "hallucinated (arrays of short strings), asked_facts (object mapping fact id to true/false/unknown). "
              "Do not assume that the original agent's self-assessment is correct.")
    reasoner._consume_call()
    response = reasoner._request(
        reasoner.client.chat.completions.create, model=reasoner.model,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        temperature=0, response_format={"type": "json_object"}, max_tokens=1200)
    data = parse_json_text(response.choices[0].message.content or "")
    return {"score": max(0, min(100, float(data["score"]))),
            "matches": list(data.get("matches") or []),
            "mismatches": list(data.get("mismatches") or []),
            "missing": list(data.get("missing") or []),
            "hallucinated": list(data.get("hallucinated") or []),
            "asked_facts": dict(data.get("asked_facts") or {})}
