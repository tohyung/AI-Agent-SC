from __future__ import annotations

import json
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from marlowe_agent.openai_reasoner import parse_json_text


class SimulatedUser:
    def __init__(self, case: Any, reasoner: Any | None) -> None:
        self.case = case
        self.reasoner = reasoner
        self.transcript: list[dict[str, Any]] = []
        self.seconds = 0.0

    def answer(self, question: str) -> str:
        started = perf_counter()
        fallback = False
        unspecified = False
        try:
            if self.reasoner is None:
                raise RuntimeError("offline user")
            system = ("Act as this ordinary customer. Respond in the customer's language with JSON "
                      '{"answer":"brief natural answer","unspecified_answer":boolean}. '
                      "Use only the original request and hidden facts. Do not describe any contract structure. "
                      "If the answer is absent, say it was not planned and choose a simple reasonable option.")
            payload = {"persona": self.case.persona, "language": self.case.language,
                       "prompt": self.case.prompt, "hidden_facts": self.case.hidden_facts,
                       "question": question}
            self.reasoner._consume_call()
            response = self.reasoner._request(
                self.reasoner.client.chat.completions.create, model=self.reasoner.model,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                temperature=0, response_format={"type": "json_object"}, max_tokens=400)
            data = parse_json_text(response.choices[0].message.content or "")
            answer = str(data["answer"]).strip()
            unspecified = bool(data.get("unspecified_answer"))
            if not answer:
                raise ValueError("empty answer")
        except (RuntimeError, ValueError, KeyError, AttributeError, IndexError, TypeError):
            fallback = True
            facts = self.case.hidden_facts
            words = question.casefold()
            match = next((fact for fact in facts if fact["id"].casefold() in words
                          or (fact["id"] == "amount" and any(term in words for term in
                              ("bao nhiêu", "số tiền", "amount", "price", "giá")))
                          or (fact["id"] == "deadline" and any(term in words for term in
                              ("khi nào", "hạn", "ngày", "deadline", "date", "when")))), None)
            answer = match["canned_answer"] if match else (
                "Tôi chưa nghĩ tới, xin chọn cách đơn giản nhất." if self.case.language == "vi"
                else "I had not considered that; please choose the simplest option.")
            unspecified = match is None
        duration = perf_counter() - started
        self.seconds += duration
        self.transcript.append({"question": question, "answer": answer,
                                "time": datetime.now(timezone.utc).isoformat(),
                                "fallback_answer": fallback, "unspecified_answer": unspecified,
                                "seconds": duration})
        return answer
