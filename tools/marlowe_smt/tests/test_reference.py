"""Regression fixtures for the pinned executable Marlowe semantics."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("run_reference", ROOT / "run_reference.py")
assert SPEC and SPEC.loader
reference = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reference)

ALICE = {"role_token": "Alice"}
BOB = {"role_token": "Bob"}
ADA = {"currency_symbol": "", "token_name": ""}


def state(amount: int = 0, *, min_time: int = 0) -> dict:
    accounts = [[[ALICE, ADA], amount]] if amount else []
    return {"accounts": accounts, "choices": [], "boundValues": [], "minTime": min_time}


def tx(lower: int | str, upper: int | str, inputs: list | None = None) -> dict:
    return {"interval": {"from": lower, "to": upper}, "inputs": inputs or []}


def pay(amount: int, payee: dict, continuation: object = "close") -> dict:
    return {"pay": amount, "from_account": ALICE, "to": payee,
            "token": ADA, "then": continuation}


def when(action: dict, continuation: object = "close", *, timeout: int = 100,
         timeout_continuation: object = "close") -> dict:
    return {"when": [{"case": action, "then": continuation}], "timeout": timeout,
            "timeout_continuation": timeout_continuation}


def deposit(amount: int) -> dict:
    return {"party": ALICE, "deposits": amount, "of_token": ADA, "into_account": ALICE}


def deposit_input(amount: int) -> dict:
    return {"type": "Deposit", "account": ALICE, "party": ALICE,
            "token": ADA, "amount": amount}


CHOICE_ID = {"choice_name": "approve", "choice_owner": BOB}
CHOICE = {"for_choice": CHOICE_ID, "choose_between": [{"from": 1, "to": 2}]}


class ReferenceSemanticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            result = subprocess.run(["cabal", "list-bin", "exe:marlowe-reference"],
                                    cwd=ROOT, check=True, capture_output=True, text=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            raise unittest.SkipTest("cabal reference executable unavailable")
        cls.binary = result.stdout.strip()

    def execute(self, contract: object, transactions: list[dict],
                initial_state: dict | None = None) -> dict:
        return reference.execute({"contract": contract,
                                  "state": initial_state or state(),
                                  "transactions": transactions}, binary=self.binary)

    def test_close_refunds_account_owner(self) -> None:
        result = self.execute("close", [tx(0, 0)], state(10))
        self.assertEqual(result["status"], "Success")
        self.assertEqual(result["steps"][0]["payments"], [
            {"source_account": ALICE, "payee": {"party": ALICE}, "token": ADA, "amount": 10}])
        self.assertEqual(result["final_state"]["accounts"], [])

    def test_pay_to_party_and_full_continuation(self) -> None:
        result = self.execute(pay(4, {"party": BOB}), [tx(0, 0)], state(10))
        self.assertEqual(result["steps"][0]["payments"][0],
                         {"source_account": ALICE, "payee": {"party": BOB},
                          "token": ADA, "amount": 4})
        self.assertEqual(result["final_contract"], "close")
        self.assertEqual(result["steps"][0]["payments"][1]["amount"], 6)

    def test_pay_to_account_and_same_account(self) -> None:
        result = self.execute(pay(4, {"account": BOB}), [tx(0, 0)], state(10))
        self.assertEqual(result["steps"][0]["payments"][0]["payee"], {"account": BOB})
        self.assertEqual(sum(item["amount"] for item in result["steps"][0]["payments"]), 14)
        same = self.execute(pay(4, {"account": ALICE}), [tx(0, 0)], state(10))
        self.assertEqual(same["steps"][0]["payments"][0]["amount"], 4)
        self.assertEqual(same["steps"][0]["payments"][1]["amount"], 10)

    def test_partial_and_nonpositive_pay(self) -> None:
        partial = self.execute(pay(10, {"party": BOB}), [tx(0, 0)], state(4))
        self.assertEqual(partial["steps"][0]["warnings"][0]["type"], "TransactionPartialPay")
        self.assertEqual(partial["steps"][0]["warnings"][0]["paid"], 4)
        self.assertEqual(partial["steps"][0]["payments"][0]["amount"], 4)
        nonpositive = self.execute(pay(-1, {"party": BOB}), [tx(0, 0)], state(4))
        self.assertEqual(nonpositive["steps"][0]["warnings"][0]["type"],
                         "TransactionNonPositivePay")
        self.assertEqual(nonpositive["steps"][0]["payments"][0]["payee"], {"party": ALICE})

    def test_nonpositive_deposit(self) -> None:
        result = self.execute(when(deposit(-1)), [tx(0, 0, [deposit_input(-1)])])
        self.assertEqual(result["steps"][0]["warnings"][0]["type"],
                         "TransactionNonPositiveDeposit")
        self.assertEqual(result["final_state"]["accounts"], [])

    def test_let_shadowing_and_assertion(self) -> None:
        contract = {"let": "x", "be": 1,
                    "then": {"let": "x", "be": 2, "then": {"assert": False, "then": "close"}}}
        result = self.execute(contract, [tx(0, 0)])
        self.assertEqual([w["type"] for w in result["steps"][0]["warnings"]],
                         ["TransactionShadowing", "TransactionAssertionFailed"])
        self.assertEqual(result["final_state"]["boundValues"], [["x", 2]])

    def test_choice_in_bounds_and_out_of_bounds(self) -> None:
        contract = when(CHOICE)
        valid = self.execute(contract, [tx(0, 0, [
            {"type": "Choice", "choice_id": CHOICE_ID, "chosen": 2}])])
        self.assertEqual(valid["status"], "Success")
        self.assertEqual(valid["final_state"]["choices"], [[CHOICE_ID, 2]])
        invalid = self.execute(contract, [tx(0, 0, [
            {"type": "Choice", "choice_id": CHOICE_ID, "chosen": 3}])])
        self.assertEqual(invalid["steps"][0]["error"]["type"], "TEApplyNoMatchError")
        self.assertEqual(invalid["final_contract"], contract)

    def test_notify_true_and_false(self) -> None:
        valid = self.execute(when({"notify_if": True}), [tx(0, 0, [{"type": "Notify"}])])
        self.assertEqual(valid["status"], "Success")
        invalid = self.execute(when({"notify_if": False}), [tx(0, 0, [{"type": "Notify"}])])
        self.assertEqual(invalid["steps"][0]["error"]["type"], "TEApplyNoMatchError")

    def test_timeout_interval_classes(self) -> None:
        contract = when({"notify_if": True})
        before = self.execute(contract, [tx(99, 99, [{"type": "Notify"}])])
        after = self.execute(contract, [tx(100, 100)])
        straddle = self.execute(contract, [tx(99, 100)])
        self.assertEqual(before["status"], "Success")
        self.assertEqual(after["status"], "Success")
        self.assertEqual(after["final_contract"], "close")
        self.assertEqual(straddle["steps"][0]["error"]["type"],
                         "TEAmbiguousTimeIntervalError")

    def test_nested_timeout_regions_are_distinct(self) -> None:
        inner = when({"notify_if": True}, timeout=200)
        contract = when({"notify_if": True}, inner, timeout=100)
        case_path = self.execute(contract, [tx(99, 99, [{"type": "Notify"}]),
                                            tx(199, 199, [{"type": "Notify"}])])
        outer_timeout = self.execute(contract, [tx(100, 100)])
        inner_timeout = self.execute(contract, [tx(99, 99, [{"type": "Notify"}]),
                                               tx(200, 200)])
        inner_straddle = self.execute(contract, [tx(99, 99, [{"type": "Notify"}]),
                                                tx(199, 200)])
        self.assertEqual(case_path["status"], "Success")
        self.assertEqual(outer_timeout["status"], "Success")
        self.assertEqual(inner_timeout["status"], "Success")
        self.assertEqual(inner_straddle["steps"][1]["error"]["type"],
                         "TEAmbiguousTimeIntervalError")

    def test_trimmed_interval_from_min_time(self) -> None:
        result = self.execute(pay({"if": {"value": "time_interval_start", "equal_to": 50},
                                   "then": 5, "else": 1}, {"party": BOB}),
                              [tx(0, 80)], state(10, min_time=50))
        self.assertEqual(result["steps"][0]["payments"][0]["amount"], 5)
        self.assertEqual(result["final_state"]["minTime"], 50)

    def test_counterexample_style_string_intervals_are_preserved(self) -> None:
        result = self.execute(when({"notify_if": True}),
                              [tx("99", "99", [{"type": "Notify"}])])
        self.assertEqual(result["status"], "Success")
        self.assertEqual(result["final_state"]["minTime"], 99)

    def test_interval_in_past_is_structured_error(self) -> None:
        result = self.execute("close", [tx(0, 1)], state(1, min_time=5))
        self.assertEqual(result["status"], "TransactionError")
        self.assertEqual(result["steps"][0]["error"]["detail"]["type"],
                         "IntervalInPastError")
        self.assertEqual(result["final_state"]["minTime"], 5)

    def test_multiple_inputs_and_split_transactions(self) -> None:
        inner = when(CHOICE, pay(10, {"party": BOB}), timeout=200)
        contract = when(deposit(10), inner)
        choice_input = {"type": "Choice", "choice_id": CHOICE_ID, "chosen": 1}
        batched = self.execute(contract, [tx(0, 0, [deposit_input(10), choice_input])])
        split = self.execute(contract, [tx(0, 0, [deposit_input(10)]), tx(1, 1, [choice_input])])
        self.assertEqual(batched["status"], "Success")
        self.assertEqual(split["status"], "Success")
        self.assertEqual(batched["final_contract"], split["final_contract"])
        self.assertEqual(batched["steps"][0]["payments"], split["steps"][1]["payments"])
        self.assertEqual(split["steps"][0]["contract"], inner)

    def test_transaction_error_stops_trace_without_state_commit(self) -> None:
        contract = when(deposit(10), when(CHOICE, timeout=200))
        result = self.execute(contract, [tx(0, 0, [deposit_input(10)]),
                                         tx(1, 1, [{"type": "Choice", "choice_id": CHOICE_ID,
                                                   "chosen": 99}]), tx(2, 2)])
        self.assertEqual(result["status"], "TransactionError")
        self.assertEqual(len(result["steps"]), 2)
        self.assertEqual(result["steps"][1]["index"], 1)
        self.assertEqual(result["final_state"], result["steps"][0]["state"])
        self.assertEqual(result["final_contract"], result["steps"][0]["contract"])

    def test_merkleized_is_distinctly_unsupported(self) -> None:
        contract = {"when": [{"case": {"notify_if": True}, "merkleized_then": "deadbeef"}],
                    "timeout": 100, "timeout_continuation": "close"}
        result = self.execute(contract, [tx(0, 0)])
        self.assertEqual(result["status"], "Unsupported")
        self.assertEqual(result["detail"]["reason"], "merkleized_continuation_not_supported")
        normal = when({"notify_if": True})
        merkleized_input = {"type": "Notify", "merkleized_continuation": "deadbeef"}
        input_result = self.execute(normal, [tx(0, 0, [merkleized_input])])
        self.assertEqual(input_result["status"], "Unsupported")

    def test_reference_identity_and_output_schema(self) -> None:
        result = self.execute("close", [tx(0, 0)], state(1))
        self.assertEqual(result["meta"]["upstream_commit"], reference.UPSTREAM_COMMIT)
        self.assertIn("reference_driver_version", result["meta"])
        self.assertIsInstance(result["steps"][0]["state"], dict)
        self.assertIsInstance(result["steps"][0]["contract"], str)


if __name__ == "__main__":
    unittest.main()
