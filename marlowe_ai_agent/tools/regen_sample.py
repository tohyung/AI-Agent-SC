from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from marlowe_agent.marlowe_ast import (
    ada_to_lovelace,
    escrow_contract,
    seconds_to_posix_ms,
)
from marlowe_agent.models import ContractDraft, PartySpec, VerificationResult
from marlowe_agent.nodes import AgentPipeline

from tools.fake_reasoner import FakeReasoner

SAMPLE_PROMPT = (
    "Alice ký quỹ 250 ADA cho Bob. Trước hạn nạp tiền Alice gửi đủ tiền; "
    "sau đó Alice chọn approve để trả Bob hoặc reject để hoàn tiền. "
    "Nếu hết hạn quyết định thì hoàn tiền Alice."
)


def generate_payload() -> dict[str, Any]:
    amount = ada_to_lovelace(250)
    deposit_timeout = seconds_to_posix_ms(1_893_456_000)
    decision_timeout = seconds_to_posix_ms(1_893_542_400)
    draft = ContractDraft(
        original_prompt=SAMPLE_PROMPT,
        intent="escrow",
        parties=[PartySpec("buyer", "Alice"), PartySpec("seller", "Bob")],
        amount=amount,
        token="ADA",
        deposit_timeout=deposit_timeout,
        decision_timeout=decision_timeout,
        clauses=[
            "Alice nạp 250 ADA trước hạn nạp tiền.",
            "Approve trả Bob; reject hoặc hết hạn quyết định hoàn Alice.",
        ],
        reasoning_summary="Hợp đồng ký quỹ hai bên.",
        reasoning_narrative="Node 1 tạo escrow với số tiền theo lovelace và deadline theo POSIX ms.",
        marlowe_contract=escrow_contract("Alice", "Bob", amount, deposit_timeout, decision_timeout),
    )
    semantic = VerificationResult(
        True, 1.0, ["Draft khớp với kịch bản ký quỹ."],
        reasoning_summary="Các bên, số tiền và nhánh xử lý đã rõ.",
        reasoning_narrative="Node 2 xác nhận các điều kiện nạp, duyệt, từ chối và hoàn tiền.",
    )
    result = AgentPipeline(FakeReasoner([draft], [semantic]), max_iterations=8).run(SAMPLE_PROMPT)
    if result.status != "done":
        raise RuntimeError(f"Sample generation failed: {result.stop_reason}")
    payload = result.to_dict()
    for event in payload["trace"]:
        if event["status"] == "iteration":
            event["data"]["elapsed_seconds"] = 0.0
    return payload


def main() -> None:
    target = Path(__file__).resolve().parents[1] / "sample_result.json"
    target.write_text(json.dumps(generate_payload(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()
