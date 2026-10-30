"""Two-asset swap lowering stays tied to explicit intent and conservation."""

from copy import deepcopy
from datetime import datetime, timezone

from research.architecture.bootstrap import build_research_pipeline
from research.architecture.status import StageRunStatus
from research.experiments.online_tuning_batch01 import batch_wiring
from research.stage2b.intent_spec import (CORE_SCHEMA_VERSION_V3,
                                          validate_shadow_semantic_core)
from research.stage2b.projector import project_intent_spec


ASSET = "native:" + "11" * 28 + "/474f4c44"
MESSAGE = (
    f"Giang deposits 29 ADA into Giang account before 2027-01-06T00:00:00Z. "
    f"Lan deposits 13 GOLD native token {ASSET} into Lan account before "
    "2027-01-13T00:00:00Z. After both deposits, pay 29 ADA from Giang account "
    f"to Lan, then pay 13 GOLD {ASSET} from Lan account to Giang. "
    "If Lan misses the second deposit, refund 29 ADA from Giang account to Giang."
)


def swap_core():
    scopes = [
        {"scope_id": "global", "scope_type": "global"},
        {"scope_id": "deposit-ada", "scope_type": "transition",
         "transition_kind": "deposit", "continuation_scope_id": "deposit-gold"},
        {"scope_id": "deposit-gold", "scope_type": "transition",
         "transition_kind": "deposit", "continuation_scope_id": "pay-ada"},
        {"scope_id": "timeout-ada", "scope_type": "timeout", "timeout_id": "ada-missing",
         "decision_id": "deposit-ada", "deadline_claim_id": "deadline-ada"},
        {"scope_id": "timeout-gold", "scope_type": "timeout", "timeout_id": "gold-missing",
         "decision_id": "deposit-gold", "deadline_claim_id": "deadline-gold",
         "continuation_scope_id": "refund-ada"},
        {"scope_id": "pay-ada", "scope_type": "terminal_outcome", "outcome_id": "pay-ada",
         "parent_scope_id": "deposit-gold", "continuation_scope_id": "pay-gold"},
        {"scope_id": "pay-gold", "scope_type": "terminal_outcome", "outcome_id": "pay-gold",
         "parent_scope_id": "deposit-gold"},
        {"scope_id": "refund-ada", "scope_type": "terminal_outcome",
         "outcome_id": "refund-ada", "parent_scope_id": "timeout-gold"},
    ]
    claims = []

    def claim(claim_id, kind, value, scope_id, span, *, derived=False):
        item = {"claim_id": claim_id, "kind": kind, "value": value,
                "criticality": "financial", "status": "derived" if derived else "explicit",
                "scope_id": scope_id,
                "evidence": [{"requirement_version": 1, "message_index": 0,
                              "span": span, "relation": "supports"}]}
        if derived:
            item["normalization_basis"] = "1 ADA = 1000000 lovelace"
        claims.append(item)

    claim("asset-ada", "asset", "ADA", "deposit-ada", "29 ADA")
    claim("amount-ada", "amount_lovelace", 29000000, "deposit-ada", "29 ADA", derived=True)
    claim("party-ada", "depositing_party", "Giang", "deposit-ada", "Giang deposits")
    claim("account-ada", "destination_account_owner", "Giang", "deposit-ada",
          "Giang account")
    claim("deadline-ada", "deposit_deadline_ms", int(datetime(2027, 1, 6,
          tzinfo=timezone.utc).timestamp() * 1000), "deposit-ada", "2027-01-06T00:00:00Z")
    claim("asset-gold", "asset", ASSET, "deposit-gold", ASSET)
    claim("amount-gold", "amount_token_units", 13, "deposit-gold", "13 GOLD")
    claim("party-gold", "depositing_party", "Lan", "deposit-gold", "Lan deposits")
    claim("account-gold", "destination_account_owner", "Lan", "deposit-gold", "Lan account")
    claim("deadline-gold", "deposit_deadline_ms", int(datetime(2027, 1, 13,
          tzinfo=timezone.utc).timestamp() * 1000), "deposit-gold", "2027-01-13T00:00:00Z")
    claim("asset-pay-ada", "asset", "ADA", "pay-ada", "pay 29 ADA")
    claim("amount-pay-ada", "amount_lovelace", 29000000, "pay-ada", "29 ADA", derived=True)
    claim("recipient-ada", "payment_recipient", "Lan", "pay-ada", "to Lan")
    claim("asset-pay-gold", "asset", ASSET, "pay-gold", ASSET)
    claim("amount-pay-gold", "amount_token_units", 13, "pay-gold", "13 GOLD")
    claim("recipient-gold", "payment_recipient", "Giang", "pay-gold", "to Giang")
    claim("asset-refund", "asset", "ADA", "refund-ada", "refund 29 ADA")
    claim("amount-refund", "amount_lovelace", 29000000, "refund-ada", "29 ADA", derived=True)
    claim("recipient-refund", "refund_recipient", "Giang", "refund-ada", "to Giang")
    return {"schema_version": CORE_SCHEMA_VERSION_V3,
            "requirement_history": [{"version": 1, "messages": [MESSAGE]}],
            "behavior_scopes": scopes, "claims": claims, "required_clarifications": [],
            "unscored_observations": [], "predicted_resolution": "accepted_interpretation"}


def _compile(core):
    class Model:
        def generate(self, system, user):
            return core

    pipeline = build_research_pipeline(model=Model(), wiring=batch_wiring())
    run = pipeline.run(core["requirement_history"], stop_after="compile", options={
        "core_schema_version": CORE_SCHEMA_VERSION_V3,
        "allow_simulated_intent": True,
    })
    return run, pipeline


def test_two_asset_swap_compiles_without_invented_choice():
    core = swap_core()
    assert validate_shadow_semantic_core(core) == []
    assert project_intent_spec(core).intent_spec.validation_errors() == []
    run, pipeline = _compile(core)
    assert run.stages["compile"].run_status == StageRunStatus.SUCCEEDED
    contract = next(pipeline.store.get(item).payload["contract"] for item in
                    run.stages["compile"].output_artifacts
                    if item.startswith("contract-candidate:"))
    assert contract["when"][0]["case"]["of_token"] == {"currency_symbol": "",
                                                        "token_name": ""}
    assert contract["when"][0]["then"]["when"][0]["case"]["of_token"] == {
        "currency_symbol": "11" * 28, "token_name": "GOLD"}
    assert contract["when"][0]["then"]["timeout_continuation"]["to"] == {
        "party": {"role_token": "Giang"}}


def test_swap_rejects_unfunded_extra_token_payout():
    core = deepcopy(swap_core())
    next(item for item in core["claims"] if item["claim_id"] == "amount-pay-gold")["value"] = 14
    run, _ = _compile(core)
    assert run.stages["compile"].run_status == StageRunStatus.UNSUPPORTED
    assert any("conserve" in item for item in run.stages["compile"].diagnostics)


def test_swap_supports_explicit_no_funding_close_and_sequential_payout_parent():
    core = swap_core()
    first_pay = next(item for item in core["behavior_scopes"]
                     if item["scope_id"] == "pay-ada")
    second_pay = next(item for item in core["behavior_scopes"]
                      if item["scope_id"] == "pay-gold")
    first_timeout = next(item for item in core["behavior_scopes"]
                         if item["scope_id"] == "timeout-ada")
    second_pay["parent_scope_id"] = first_pay["scope_id"]
    first_timeout["continuation_scope_id"] = "close-unfunded"
    core["behavior_scopes"].append({
        "scope_id": "close-unfunded", "scope_type": "terminal_outcome",
        "outcome_id": "close-unfunded", "parent_scope_id": "timeout-ada",
    })
    assert validate_shadow_semantic_core(core) == []
    run, _ = _compile(core)
    assert run.stages["compile"].run_status == StageRunStatus.SUCCEEDED
