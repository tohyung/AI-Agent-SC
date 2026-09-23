from __future__ import annotations

import json
from pathlib import Path

from marlowe_agent.logic_graph import LogicGraphVerifier
from marlowe_agent.marlowe_validator import validate_contract
from tools.regen_sample import generate_payload


def test_sample_result_is_valid_and_up_to_date() -> None:
    target = Path(__file__).resolve().parents[1] / "sample_result.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload == generate_payload()
    assert payload["trace"]
    assert payload["status"] == "done"
    assert payload["stop_reason"] == "ok"
    assert validate_contract(payload["marlowe_contract"]) == []
    assert LogicGraphVerifier().verify(payload["marlowe_contract"]).passed
