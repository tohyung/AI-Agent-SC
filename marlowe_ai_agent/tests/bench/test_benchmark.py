from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

from bench.cases import load_cases
from bench import run as run_cli
from bench.evaluator import _run, evaluate
from bench.marlowe_sim import run_scenario
from bench.narrator import narrate
from bench.runner import FakeBenchReasoner, dataset_hash, read_runs, run_case, run_many
from bench.stats import percentile, spearman, wilson
from bench.validate_dataset import validate
from marlowe_agent.marlowe_ast import case, choice_action, close, deposit, escrow_contract, pay, when
from marlowe_agent.nodes import PromptToDraftNode
from marlowe_agent.openai_reasoner import OpenAIReasoner


CASES = load_cases()


def _case(kind: str):
    return next(item for item in CASES if item.type == kind)


def _audit(case_id: str):
    path = Path(__file__).parents[2] / "bench" / "audit" / f"{case_id}-full.json"
    return json.loads(path.read_text(encoding="utf-8"))["contract"]


def test_every_reference_scores_100_and_passes_dataset_validation():
    assert validate(CASES) == []
    assert all(evaluate(item, item.reference_contract)["strict_correct"]
               for item in CASES if item.type != "infeasible")


def test_simulator_escrow_approve_and_timeout_by_hand():
    contract = escrow_contract("buyer", "seller", 10, 100, 200)
    approved = run_scenario(contract, [{"kind": "deposit", "party": "buyer", "amount": 10,
                                        "token": "", "time": 50},
                                       {"kind": "choice", "party": "buyer", "name": "approve",
                                        "value": 1, "time": 150}], 0)
    assert approved["received"] == {"seller": {"": 10}}
    expired = run_scenario(contract, [{"kind": "deposit", "party": "buyer", "amount": 10,
                                       "token": "", "time": 50},
                                      {"kind": "advance", "time": 201}], 0)
    assert expired["received"] == {"buyer": {"": 10}}
    no_deposit = run_scenario(contract, [{"kind": "advance", "time": 101}], 0)
    assert no_deposit["received"] == {}


def test_simulator_partial_pay_rejection_refund_and_divvalue():
    partial = run_scenario(pay("a", "b", 11), [], 0)
    assert partial["partial_pay"] and partial["received"] == {}
    contract = when([case(deposit("a", "a", 7), close())], 100)
    refund = run_scenario(contract, [{"kind": "deposit", "party": "a", "amount": 7,
                                     "token": "", "time": 50}], 0)
    assert refund["received"] == {"a": {"": 7}}
    rejected = run_scenario(contract, [{"kind": "deposit", "party": "b", "amount": 7,
                                       "token": "", "time": 50}], 0)
    assert rejected["input_rejected"]
    divided = pay("a", "b", {"divide": 8, "by": 2})
    assert run_scenario(divided, [], 0)["not_evaluable"]


def test_choice_exact_match_requires_owner_and_bound_not_just_name():
    contract = when([
        case(choice_action("decision", "alice", 0, 0), close()),
        case(choice_action("decision", "bob", 1, 1), close()),
    ], 100)
    wrong_bound_and_owner = {"kind": "choice", "party": "alice", "name": "decision",
                             "value": 1, "time": 50}
    assert run_scenario(contract, [wrong_bound_and_owner], 0)["input_rejected"]
    valid = {"kind": "choice", "party": "alice", "name": "decision", "value": 0, "time": 50}
    assert not run_scenario(contract, [valid], 0)["input_rejected"]


@pytest.mark.parametrize("case_id", ["vi-rental_deposit-L3-003", "vi-milestone-L4-003"])
def test_audit_choice_name_fallback_runs_original_scenarios(case_id):
    item = next(case for case in CASES if case.id == case_id)
    contract = _audit(case_id)
    mapping = evaluate(item, contract)["mapping"]
    for scenario in item.checks["scenarios"]:
        outcome = _run(contract, scenario, mapping)
        assert not outcome["input_rejected"]
        assert outcome["closed"] == scenario["closed"]
        assert outcome["received"] == scenario["received"]


def test_choice_name_fallback_rejects_ambiguous_and_unmatched_candidates():
    ambiguous = when([
        case(choice_action("first", "alice", 1, 1), close()),
        case(choice_action("second", "alice", 1, 1), close()),
    ], 100)
    unmatched_name = {"kind": "choice", "party": "alice", "name": "expected",
                      "value": 1, "time": 50}
    assert run_scenario(ambiguous, [unmatched_name], 0)["input_rejected"]

    no_candidate = when([case(choice_action("actual", "bob", 0, 0), close())], 100)
    assert run_scenario(no_candidate, [unmatched_name], 0)["input_rejected"]


def test_choice_name_fallback_never_looks_into_a_case_continuation():
    nested = when([case(choice_action("nested", "bob", 1, 1), close())], 200)
    contract = when([case(choice_action("outer", "alice", 0, 0), nested)], 100)
    step = {"kind": "choice", "party": "bob", "name": "expected", "value": 1, "time": 50}
    assert run_scenario(contract, [step], 0)["input_rejected"]


def test_choice_exact_match_does_not_emit_fallback_warning():
    contract = when([case(choice_action("decision", "alice", 1, 1), close())], 100)
    step = {"kind": "choice", "party": "alice", "name": "decision", "value": 1,
            "time": 50}
    outcome = run_scenario(contract, [step], 0)
    assert not outcome["input_rejected"]
    assert outcome["warnings"] == []

    fallback_step = {**step, "name": "expected"}
    fallback = run_scenario(contract, [fallback_step], 0)
    assert not fallback["input_rejected"]
    assert fallback["warnings"] == ["choice_name_fallback:expected->decision"]


def test_evaluator_counts_scenarios_using_choice_name_fallback():
    rental = next(case for case in CASES if case.id == "vi-rental_deposit-L3-003")
    milestone = next(case for case in CASES if case.id == "vi-milestone-L4-003")
    assert evaluate(rental, _audit(rental.id))["diagnostics"]["choice_name_fallback_count"] == 2
    assert evaluate(milestone, _audit(milestone.id))["diagnostics"]["choice_name_fallback_count"] == 2


def test_reference_scenarios_cover_swap_vesting_loan():
    for kind in ("swap", "vesting", "loan"):
        item = _case(kind)
        assert evaluate(item, item.reference_contract)["scenario_accuracy"] == 1


def test_mutated_amount_degrades_accuracy_and_unit_error_is_labeled():
    item = _case("escrow_2party")
    doubled = FakeBenchReasoner(item, wrong=True).draft_from_prompt(item.prompt).marlowe_contract
    assert evaluate(item, doubled)["overall_accuracy"] < 1
    wrong_unit = deepcopy(item.reference_contract)
    wrong_unit["when"][0]["case"]["deposits"] //= 1000000
    score = evaluate(item, wrong_unit)
    assert "lovelace_unit_error" in score["diagnostics"]


def test_shifted_deadline_gap_is_not_hidden_by_24h_tolerance():
    item = _case("escrow_2party")
    shifted = deepcopy(item.reference_contract)
    shifted["when"][0]["then"]["timeout"] += 86400000
    result = evaluate(item, shifted)
    assert result["timing_accuracy"] < 1


def test_dataset_validator_detects_duplicate_banned_word_and_drift():
    repeated = CASES.copy()
    repeated[1] = replace(repeated[1], prompt=repeated[0].prompt)
    assert "duplicate_prompts" in validate(repeated)
    banned = CASES.copy()
    banned[0] = replace(banned[0], prompt=banned[0].prompt + " smart contract")
    assert any(item.startswith("banned:") for item in validate(banned))
    drift = CASES.copy()
    drift[0] = replace(drift[0], reference_contract="close")
    assert any(item.startswith("ground_truth_drift:") for item in validate(drift))


def test_narrator_deterministic_and_lists_paths():
    contract = escrow_contract("a", "b", 10, 100, 200)
    first = narrate(contract)
    assert first == narrate(contract)
    assert len(first.splitlines()) == 4


def test_answer_provider_bypasses_stdin(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: pytest.fail("stdin was called"))
    node = PromptToDraftNode(object(), interactive=True, answer_provider=lambda _: "42 ADA")
    outcome = node.ask_for_clarifications("Prompt", ["How much?"], "Answers")
    assert outcome.user_answered and "42 ADA" in outcome.prompt


def test_usage_log_counts_real_sdk_request_without_prompt_data():
    reasoner = object.__new__(OpenAIReasoner)
    reasoner.model = "requested"
    reasoner.call_log = []
    response = SimpleNamespace(model="served", usage=SimpleNamespace(prompt_tokens=12,
                                completion_tokens=5, cost=0.01))
    assert reasoner._request(lambda **_: response, secret="do-not-log") is response
    assert reasoner.usage_summary()["cost"] == 0.01
    assert reasoner.call_log[0]["model"] == "served"
    assert "do-not-log" not in str(reasoner.call_log)


def test_runner_fake_reference_mutation_resume_and_budget(tmp_path):
    item = _case("escrow_2party")
    good = run_case(item, fake=True)
    bad = run_case(item, fake=True, fake_wrong=True)
    assert good["evaluation"]["strict_correct"]
    assert bad["evaluation"]["overall_accuracy"] < 1
    rows = run_many([item], tmp_path, workers=1, fake=True, dataset_sha256=dataset_hash())
    assert len(rows) == 1
    assert len(run_many([item], tmp_path, workers=1, fake=True, dataset_sha256=dataset_hash())) == 1
    assert len(read_runs(tmp_path / "runs.jsonl")) == 1
    other = _case("loan")
    assert len(run_many([other], tmp_path, workers=1, fake=True, dataset_sha256=dataset_hash(),
                        max_usd=0)) == 1


def test_runner_cooperative_timeout_keeps_partial_trace():
    record = run_case(_case("escrow_2party"), fake=True, wall_clock=1e-12)
    assert record["stop_reason"] == "wallclock_timeout"
    assert record["trace"]


def test_secret_like_text_is_redacted_from_run_record():
    item = replace(_case("escrow_2party"), prompt="My key is sk-test-secret-123456789.")
    record = run_case(item, fake=True)
    assert "sk-test-secret-123456789" not in str(record)


def test_statistics_known_values():
    lo, hi = wilson(5, 10)
    assert 0.23 < lo < 0.24 and 0.76 < hi < 0.77
    assert percentile([1, 2, 3, 4], 50) == 2.5
    assert spearman([1, 2, 3], [3, 2, 1]) == pytest.approx(-1)


def test_case_ids_selection_preserves_order_and_rejects_unknown():
    ids = [CASES[3].id, CASES[0].id, CASES[8].id]
    selected = run_cli.select_case_ids(CASES, ",".join(ids))
    assert [case.id for case in selected] == ids
    with pytest.raises(ValueError, match="Unknown case ID"):
        run_cli.select_case_ids(CASES, "does-not-exist")
    with pytest.raises(ValueError, match="duplicate"):
        run_cli.select_case_ids(CASES, f"{ids[0]},{ids[0]}")


def test_case_ids_cli_is_real_timing_probe_without_budget_or_summary(monkeypatch, tmp_path, capsys):
    ids = [CASES[3].id, CASES[0].id]
    captured = {}

    def fake_run_many(selected, directory, **kwargs):
        captured.update(ids=[item.id for item in selected], options=kwargs)
        return []

    monkeypatch.setattr(run_cli, "OpenAIReasoner", lambda model=None: SimpleNamespace(model="free:free"))
    monkeypatch.setattr(run_cli, "run_many", fake_run_many)
    monkeypatch.setattr(run_cli, "RESULTS", tmp_path)
    monkeypatch.setattr(run_cli, "generate", lambda _: pytest.fail("official report generated"))
    monkeypatch.setattr(sys, "argv", ["bench.run", "--case-ids", ",".join(ids)])
    run_cli.main()
    assert captured["ids"] == ids
    assert captured["options"]["preserve_order"] is True
    assert captured["options"]["timing_probe"] is True
    assert captured["options"]["max_usd"] is None
    assert "Timing probe only" in capsys.readouterr().out


def test_case_ids_cli_rejects_fake(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["bench.run", "--case-ids", CASES[0].id, "--fake"])
    with pytest.raises(SystemExit) as exc:
        run_cli.main()
    assert exc.value.code == 2


@pytest.mark.parametrize("raw", ["", "does-not-exist"])
def test_case_ids_cli_rejects_invalid_ids_before_llm_bootstrap(monkeypatch, capsys, raw):
    monkeypatch.setattr(sys, "argv", ["bench.run", "--case-ids", raw])
    monkeypatch.setattr(run_cli, "OpenAIReasoner", lambda model=None: pytest.fail("LLM was initialized"))
    with pytest.raises(SystemExit) as exc:
        run_cli.main()
    assert exc.value.code == 2
    assert "case-ids" in capsys.readouterr().err


def test_runner_preserve_order_with_one_worker(tmp_path):
    selected = [CASES[3], CASES[0]]
    rows = run_many(selected, tmp_path, workers=1, fake=True,
                    preserve_order=True, dataset_sha256=dataset_hash())
    assert [row["case_id"] for row in rows] == [case.id for case in selected]
