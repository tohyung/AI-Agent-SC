"""Synthetic primitive combinations against the real pinned Haskell semantics.

These fixtures prove executor compatibility, not any Batch 01 candidate intent.
"""

from pathlib import Path
import shutil
import subprocess

import pytest

from research.stage3.contract_plan import (Case, Choice, ChoiceGuard, ClaimValue,
                                           Close, Deposit, IfChoice, Notify, Pay, When,
                                           lower_contract_plan)
from research.stage3.reference import PinnedMarloweReference, ReferenceRequest


T1 = 1799000000000
T2 = T1 + 600000
ADA = {"currency_symbol": "", "token_name": ""}
GOLD_ID = "native:" + "ab" * 28 + "/474f4c44"
GOLD = {"currency_symbol": "ab" * 28, "token_name": "GOLD"}
STATE = {"accounts": [], "choices": [], "boundValues": [], "minTime": 0}


def cv(value, name):
    return ClaimValue(value, name)


def payout(scope, account, recipient, amount, token="ADA", then=None):
    return Pay(scope, cv(account, scope + ":account"),
               cv(recipient, scope + ":recipient"), cv(token, scope + ":token"),
               cv(amount, scope + ":amount"), then or Close(scope + ":done"))


def deposit(scope, party, account, amount, token="ADA"):
    return Deposit(scope, cv(party, scope + ":party"),
                   cv(account, scope + ":account"), cv(token, scope + ":token"),
                   cv(amount, scope + ":amount"))


def tx(time, inputs=()):
    return {"interval": {"from": time, "to": time}, "inputs": list(inputs)}


def deposit_input(party, account, amount, token=ADA):
    return {"type": "Deposit", "party": {"role_token": party},
            "account": {"role_token": account}, "token": token, "amount": amount}


@pytest.fixture(scope="module")
def reference():
    if shutil.which("cabal") is None or shutil.which("ghc") is None:
        pytest.skip("Cabal/GHC unavailable; real Haskell reference not exercised")
    root = Path(__file__).resolve().parents[2] / "tools/marlowe_smt"
    resolved = subprocess.run(["cabal", "list-bin", "exe:marlowe-reference"],
                              cwd=root, capture_output=True, text=True, check=True)
    binary = resolved.stdout.strip()
    if not Path(binary).is_file():
        pytest.fail("pinned reference executable missing")
    return PinnedMarloweReference(binary=binary, hard_timeout_seconds=15)


def execute(reference, plan, transactions):
    contract = lower_contract_plan(plan).contract
    result = reference.execute(ReferenceRequest(contract, STATE, tuple(transactions)))
    assert result["status"] == "Success", result
    assert result["final_contract"] == "close"
    return [payment for step in result["steps"] for payment in step["payments"]]


def test_choice_branches_and_timeout_execute_on_real_reference(reference):
    guarded = IfChoice("decision", ChoiceGuard("vote", cv("Oracle", "chooser"), "ge", 1),
                       payout("release", "Alice", "Bob", 7),
                       payout("refund", "Alice", "Alice", 7))
    plan = When("fund-wait", (
        Case(deposit("fund", "Alice", "Alice", 7),
             When("vote-wait", (Case(Choice("vote", cv("Oracle", "chooser"), 0, 1),
                                     guarded),), cv(T2, "vote-deadline"),
                  payout("vote-timeout", "Alice", "Alice", 7))),
    ), cv(T1, "fund-deadline"), Close("fund-timeout"))
    funded = tx(T1 - 2, [deposit_input("Alice", "Alice", 7)])
    for selected, recipient in ((1, "Bob"), (0, "Alice")):
        choice = {"type": "Choice", "choice_id": {
            "choice_name": "vote", "choice_owner": {"role_token": "Oracle"}},
            "chosen": selected}
        payments = execute(reference, plan, (funded, tx(T1 - 1, [choice])))
        assert [(item["payee"]["party"]["role_token"], item["amount"])
                for item in payments] == [(recipient, 7)]
    timed_out = execute(reference, plan, (funded, tx(T2)))
    assert [(item["payee"]["party"]["role_token"], item["amount"])
            for item in timed_out] == [("Alice", 7)]


def test_native_asset_swap_and_refund_execute_on_real_reference(reference):
    plan = When("ada-wait", (
        Case(deposit("ada-fund", "Alice", "Alice", 5),
             When("gold-wait", (
                 Case(deposit("gold-fund", "Bob", "Bob", 2, GOLD_ID),
                      payout("gold-release", "Bob", "Alice", 2, GOLD_ID,
                             payout("ada-release", "Alice", "Bob", 5))),
             ), cv(T2, "gold-deadline"), payout("ada-refund", "Alice", "Alice", 5))),
    ), cv(T1, "ada-deadline"), Close("ada-timeout"))
    first = tx(T1 - 2, [deposit_input("Alice", "Alice", 5)])
    second = tx(T1 - 1, [deposit_input("Bob", "Bob", 2, GOLD)])
    payments = execute(reference, plan, (first, second))
    assert [(item["payee"]["party"]["role_token"], item["token"], item["amount"])
            for item in payments] == [("Alice", GOLD, 2), ("Bob", ADA, 5)]
    refunded = execute(reference, plan, (first, tx(T2)))
    assert [(item["payee"]["party"]["role_token"], item["amount"])
            for item in refunded] == [("Alice", 5)]


def test_two_deposits_and_timeout_refund_execute_on_real_reference(reference):
    plan = When("first-wait", (
        Case(deposit("first", "Alice", "Campaign", 4),
             When("second-wait", (
                 Case(deposit("second", "Bob", "Campaign", 6),
                      payout("goal", "Campaign", "Beneficiary", 10)),
             ), cv(T2, "second-deadline"),
                  payout("failed-goal", "Campaign", "Alice", 4))),
    ), cv(T1, "first-deadline"), Close("first-timeout"))
    first = tx(T1 - 2, [deposit_input("Alice", "Campaign", 4)])
    second = tx(T1 - 1, [deposit_input("Bob", "Campaign", 6)])
    reached = execute(reference, plan, (first, second))
    assert [(item["payee"]["party"]["role_token"], item["amount"])
            for item in reached] == [("Beneficiary", 10)]
    refunded = execute(reference, plan, (first, tx(T2)))
    assert [(item["payee"]["party"]["role_token"], item["amount"])
            for item in refunded] == [("Alice", 4)]


def test_notify_and_split_payment_execute_on_real_reference(reference):
    plan = When("fund-wait", (
        Case(deposit("fund", "Alice", "Alice", 10),
             When("notice-wait", (
                 Case(Notify("delivery-notice", True),
                      payout("fee", "Alice", "Inspector", 3,
                             then=payout("balance", "Alice", "Bob", 7))),
             ), cv(T2, "notice-deadline"),
                  payout("notice-timeout", "Alice", "Alice", 10))),
    ), cv(T1, "fund-deadline"), Close("fund-timeout"))
    first = tx(T1 - 2, [deposit_input("Alice", "Alice", 10)])
    delivered = execute(reference, plan, (first, tx(T1 - 1, [{"type": "Notify"}])))
    assert [(item["payee"]["party"]["role_token"], item["amount"])
            for item in delivered] == [("Inspector", 3), ("Bob", 7)]
    expired = execute(reference, plan, (first, tx(T2)))
    assert [(item["payee"]["party"]["role_token"], item["amount"])
            for item in expired] == [("Alice", 10)]
