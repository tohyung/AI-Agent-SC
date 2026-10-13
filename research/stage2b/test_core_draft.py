"""Offline, source-grounded variants; production never loads this corpus."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from research.stage2b.core_draft import DRAFT_FIELDS, materialize_core_draft
from research.stage2b.intent_spec import CORE_SCHEMA_VERSION_V3, validate_shadow_semantic_core
from research.stage2b.repair_policy import diagnostic_code, diagnostic_codes
from research.stage2b.shadow_extractor import IntentShadowExtractor, build_prompt


CORPUS = Path(__file__).parent / "fixtures" / "semantic_variants.jsonl"
VARIANTS = [json.loads(line) for line in CORPUS.read_text(encoding="utf-8").splitlines()]


def draft_for(row):
    return {
        "behavior_scopes": [
            {"scope_id": "global", "scope_type": "global"},
            {"scope_id": "deposit", "scope_type": "transition", "transition_kind": "deposit"},
        ],
        "claims": deepcopy(row["claims"]),
        "required_clarifications": [],
        "unscored_observations": [],
        "predicted_resolution": "accepted_interpretation",
    }


@pytest.mark.parametrize("row", VARIANTS, ids=lambda row: row["id"])
def test_source_grounded_draft_corpus(row):
    draft = draft_for(row)
    original = deepcopy(draft)
    core, actions = materialize_core_draft(draft, row["history"], CORE_SCHEMA_VERSION_V3)
    assert draft == original
    assert set(draft) == DRAFT_FIELDS
    assert core["requirement_history"] == row["history"]
    assert core["claims"][0]["value"] == row["expected_value"]
    assert bool(actions) is (type(row["expected_value"]) is int)
    assert (len(validate_shadow_semantic_core(
        core, expected_history=row["history"])) == 0) is row["expected_valid"]


def test_compact_model_draft_materializes_without_second_model_call():
    row = VARIANTS[0]

    class DraftModel:
        calls = 0

        def generate(self, _system, _user):
            self.calls += 1
            return draft_for(row)

    model = DraftModel()
    extractor = IntentShadowExtractor(model, core_schema_version=CORE_SCHEMA_VERSION_V3)
    core = extractor.extract(row["history"])
    assert model.calls == 1
    assert core.to_dict()["claims"][0]["value"] == 101_000_000
    assert extractor.normalization_actions[0]["claim_id"] == "principal"
    system, user = build_prompt(row["history"], core_schema_version=CORE_SCHEMA_VERSION_V3)
    assert "five internal draft fields" in system
    assert "five internal draft fields" in user


def test_legacy_full_core_and_unbacked_draft_are_never_rewritten():
    row = VARIANTS[1]
    full = {"schema_version": CORE_SCHEMA_VERSION_V3,
            "requirement_history": deepcopy(row["history"]), **draft_for(row)}
    result, actions = materialize_core_draft(full, row["history"], CORE_SCHEMA_VERSION_V3)
    assert result == full and actions == []
    compact, actions = materialize_core_draft(draft_for(row), row["history"],
                                              CORE_SCHEMA_VERSION_V3)
    assert compact["claims"][0]["value"] == "101 ADA" and actions == []


def test_normalization_preserves_source_backed_supersession():
    row = VARIANTS[0]
    draft = draft_for(row)
    draft["claims"] = [
        {"claim_id": "old", "kind": "amount_lovelace", "value": "102 ADA",
         "criticality": "financial", "status": "superseded", "scope_id": "deposit",
         "superseded_by": "principal",
         "evidence": [{"requirement_version": 1, "message_index": 0,
                       "span": "102 ADA", "relation": "supports"}]},
        {**draft["claims"][0], "status": "user_confirmed"},
    ]
    core, actions = materialize_core_draft(draft, row["history"], CORE_SCHEMA_VERSION_V3)
    assert [item["value"] for item in core["claims"]] == [102_000_000, 101_000_000]
    assert [item["status"] for item in core["claims"]] == ["superseded", "user_confirmed"]
    assert len(actions) == 2
    assert validate_shadow_semantic_core(core, expected_history=row["history"]) == []


def test_repair_codes_are_invariants_not_case_specific_strings():
    errors = ["scope deposit-1: invalid continuation_scope_id",
              "scope deposit-2: invalid continuation_scope_id",
              "claim first: invalid evidence target/span",
              "claim second: invalid evidence target/span"]
    assert diagnostic_codes(errors) == ["SCOPE_GRAPH", "SOURCE_EVIDENCE"]
    assert diagnostic_code("claim amount: invalid derived_from source claim") == "PROVENANCE_LINK"
