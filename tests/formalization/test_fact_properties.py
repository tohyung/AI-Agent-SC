"""Builder theorems T1–T7 (docs/archive/E4-Formalization-Comparison.md, Part III), checked on seeded random drafts.

Each property runs over a fixed range of seeds, so a failure names the draft
that breaks it (`random_draft(seed)`). These tests need no model, network or
Haskell binary; the reference and SMT checks of the same theorems are in
`test_fact_reference.py`.
"""

from copy import deepcopy
import random

import pytest

from research.formalization.fact_builder import DraftError, build_core
from research.formalization.fact_semantics import NotDenotable, denote, paths
from research.formalization.intent_spec import validate_intent_spec, validate_shadow_semantic_core
from research.formalization.projector import classify_projection, project_intent_spec
from tests.formalization.fact_draft_gen import core_path, random_draft

SEEDS = range(300)
FIELDS = ("parties", "quantities", "instants", "steps", "outcomes")


def _ids(draft):
    return {item["id"] for field in FIELDS for item in draft.get(field) or []}


@pytest.mark.parametrize("seed", SEEDS)
def test_t1_t2_determinism_and_declaration_order_invariance(seed):
    draft, history = random_draft(seed)
    core = build_core(draft, history)
    assert build_core(deepcopy(draft), history) == core
    shuffled = deepcopy(draft)
    rng = random.Random(seed)
    for field in FIELDS:
        rng.shuffle(shuffled[field])
    assert build_core(shuffled, history) == core


@pytest.mark.parametrize("seed", SEEDS)
def test_t3_every_built_core_passes_the_unchanged_v4_validator_and_projector(seed):
    draft, history = random_draft(seed)
    core = build_core(draft, history)
    errors = validate_shadow_semantic_core(core, expected_history=history)
    assert errors == []
    projection = project_intent_spec(core, expected_history=history)
    full = validate_intent_spec(projection.intent_spec.to_dict(), expected_history=history,
                                projected_core=core)
    assert classify_projection(errors, full, projection.projection_diagnostics) == "PASS"


@pytest.mark.parametrize("seed", SEEDS)
def test_t4_core_agrees_with_the_denotation_on_every_path(seed):
    draft, history = random_draft(seed)
    core = build_core(draft, history)
    runs = paths(denote(draft))
    assert runs
    for run in runs:
        outcomes, deadlines = core_path(core, run.moves)
        # Explicit outcomes are the Pays of ⟦D⟧, in order, with the same amounts.
        assert run.payments[:len(outcomes)] == outcomes, run.moves
        assert run.deadlines == deadlines, run.moves


@pytest.mark.parametrize("seed", SEEDS)
def test_t5_money_is_conserved_and_never_overdrawn(seed):
    draft, history = random_draft(seed)
    core = build_core(draft, history)
    for run in paths(denote(draft)):
        outcomes, _ = core_path(core, run.moves)
        deposited = sum(transaction["inputs"][0]["amount"] for transaction in run.transactions
                        if transaction["inputs"] and transaction["inputs"][0]["type"] == "Deposit")
        assert run.partial_pays == 0, run.moves
        assert sum(amount for _, _, amount in run.payments) == deposited
        # Whatever the outcomes leave is refunded to its owner when the contract closes.
        assert all(source == payee for source, payee, _ in run.payments[len(outcomes):])


def _open_variants(draft, rng):
    """Drafts that leave one fact open, with the resolution v4 requires for it."""
    unknown = deepcopy(draft)
    # Only a literal or a date: opening a derived item would orphan what it refers to.
    item = rng.choice([item for item in unknown["quantities"] + unknown["instants"]
                       if "ada" in item["expr"] or "date" in item["expr"]])
    item["expr"] = {"unknown": True}
    yield unknown, "clarification_required"
    if draft["quantities"]:
        conflicting = deepcopy(draft)
        quantity = next(item for item in conflicting["quantities"] if "ada" in item["expr"])
        literal = quantity["expr"]["ada"]
        quantity["alternatives"] = [{"expr": {"ada": literal}, "evidence": quantity["evidence"]},
                                    {"expr": {"ada": literal + "0"},
                                     "evidence": quantity["evidence"]}]
        del quantity["expr"]
        yield conflicting, "conflict_requires_resolution"
    deletion = deepcopy(draft)
    deletion["notes"] = {"unsupported": [{"kind": "ledger_history_deletion",
                                          "evidence": draft["parties"][0]["evidence"]}]}
    yield deletion, "unsupported_for_current_study"


@pytest.mark.parametrize("seed", range(100))
def test_t6_accepted_exactly_when_the_draft_has_a_meaning(seed):
    draft, history = random_draft(seed)
    assert build_core(draft, history)["predicted_resolution"] == "accepted_interpretation"
    denote(draft)
    rng = random.Random(seed)
    for variant, resolution in _open_variants(draft, rng):
        # A conflicting literal is a draft error when its text is not in the source.
        try:
            core = build_core(variant, history)
        except DraftError as error:
            assert resolution == "conflict_requires_resolution", error
            continue
        assert core["predicted_resolution"] == resolution
        assert validate_shadow_semantic_core(core, expected_history=history) == []
        if resolution != "unsupported_for_current_study":
            assert core["required_clarifications"]
        with pytest.raises(NotDenotable):
            denote(variant)


MUTATIONS = ("drop_key", "dangling_ref", "wrong_type", "bad_span", "bad_literal", "bad_kind")


def _mutate(draft, rng):
    mutant = deepcopy(draft)
    field = rng.choice([field for field in FIELDS if mutant[field]])
    item = rng.choice(mutant[field])
    mutation = rng.choice(MUTATIONS)
    keys = [key for key in item if key != "id"]
    if mutation == "drop_key" and keys:
        del item[rng.choice(keys)]
    elif mutation == "dangling_ref":
        refs = [key for key, value in item.items() if isinstance(value, str) and key != "id"]
        if refs:
            item[rng.choice(refs)] = "missing_item"
    elif mutation == "wrong_type" and keys:
        item[rng.choice(keys)] = rng.choice([None, 7, [], {}, "x", True])
    elif mutation == "bad_span":
        item["evidence"] = [{"requirement_version": 1, "message_index": 0,
                             "span": "không có trong yêu cầu", "relation": "supports"}]
    elif mutation == "bad_literal" and field == "quantities" and "ada" in item.get("expr", {}):
        item["expr"]["ada"] = "999999"
    elif mutation == "bad_kind":
        item["kind"] = "transfer_everything"
    return mutant


@pytest.mark.parametrize("seed", range(500))
def test_t7_builder_is_total_and_errors_name_draft_items(seed):
    draft, history = random_draft(seed % 100)
    mutant = _mutate(draft, random.Random(seed))
    allowed = _ids(draft) | set(FIELDS) | {"schema_version", "asset", "missing_item"} | {
        f"unsupported_{index}" for index in range(1, 4)}
    try:
        core = build_core(mutant, history)
    except DraftError as error:
        # Repair is per atomic item: every problem must point at something the model wrote.
        names = {item.split(":")[0] for item, _ in error.problems}
        assert names <= allowed, error.problems
        return
    # A mutation the builder accepts must still yield a valid core.
    assert validate_shadow_semantic_core(core, expected_history=history) == []
