from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPO = HERE.parents[2]
APP = REPO / "marlowe_ai_agent"
sys.path.insert(0, str(APP))

from marlowe_agent.marlowe_validator import validate_contract  # noqa: E402


class MarloweSMTGoldenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        result = subprocess.run(
            ["cabal", "list-bin", "exe:marlowe-smt"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        cls.binary = result.stdout.strip()
        cls.expectations = json.loads((HERE / "expectations.json").read_text(encoding="utf-8"))

    def run_payload(self, payload: str, *, solver_timeout_ms: int = 30_000) -> tuple[subprocess.CompletedProcess[str], dict]:
        process = subprocess.run(
            [self.binary, "--solver-timeout-ms", str(solver_timeout_ms)],
            input=payload,
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
        )
        lines = process.stdout.splitlines()
        self.assertEqual(len(lines), 1, f"stdout must contain one JSON object: {process.stdout!r}")
        return process, json.loads(lines[0])

    def run_file(self, name: str) -> tuple[subprocess.CompletedProcess[str], dict]:
        return self.run_payload((HERE / name).read_text(encoding="utf-8"))

    def assert_expected(self, name: str) -> dict:
        process, output = self.run_file(name)
        expected = self.expectations[name]
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(output["status"], expected["status"])
        self.assertEqual([item["type"] for item in output["warnings"]], expected["warnings"])
        self.assertEqual(output["meta"]["upstream_commit"], "7b5b1e900ec53a8eb18747992bec73470704dfcb")
        return output

    def test_agent_escrow_fixture_is_valid(self) -> None:
        fixture = APP / "tests" / "fixtures" / "escrow_golden.json"
        process, output = self.run_payload(fixture.read_text(encoding="utf-8"))
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(output["status"], "Valid")
        self.assertEqual(output["warnings"], [])

    def test_all_five_warning_types(self) -> None:
        for name in (
            "partial_pay.json",
            "nonpositive_pay.json",
            "nonpositive_deposit.json",
            "shadowing.json",
            "assertion_failed.json",
        ):
            with self.subTest(name=name):
                output = self.assert_expected(name)
                self.assertIsNotNone(output["counterexample"])

    def test_initial_state_changes_result(self) -> None:
        empty = self.assert_expected("state_empty.json")
        funded = self.assert_expected("state_funded.json")
        self.assertNotEqual(empty["status"], funded["status"])

    def test_merkleized_case_is_disclosed(self) -> None:
        output = self.assert_expected("merkleized.json")
        self.assertEqual(len(output["analysis_notes"]), 1)
        self.assertIn("1 MerkleizedCase", output["analysis_notes"][0])
        self.assertIn("not analyzed", output["analysis_notes"][0])

    def test_constructor_address_and_native_token_coverage(self) -> None:
        valid = self.assert_expected("coverage_valid.json")
        warning = self.assert_expected("coverage_warning.json")
        self.assertEqual(valid["analysis_notes"], [])
        self.assertEqual(warning["warnings"][0]["type"], "TransactionAssertionFailed")

    def test_invalid_inputs_are_structured_and_nonzero(self) -> None:
        for name in (
            "invalid_extra.json",
            "invalid_missing.json",
            "invalid_unknown.json",
            "invalid_type.json",
            "invalid_malformed.json",
        ):
            with self.subTest(name=name):
                process, output = self.run_file(name)
                self.assertNotEqual(process.returncode, 0)
                self.assertEqual(output["status"], "InvalidInput")
                self.assertEqual(output["warnings"], [])
                self.assertIsNone(output["counterexample"])
                self.assertTrue(output["error"])
                self.assertTrue(process.stderr)

    def test_completed_audit_contracts_match_validator_acceptance(self) -> None:
        audit_dir = APP / "bench" / "audit"
        checked = 0
        disagreements: list[str] = []
        for path in sorted(audit_dir.glob("*-full.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            contract = record.get("contract")
            if record.get("status") != "done" or contract in (None, {}):
                continue
            checked += 1
            validator_errors = validate_contract(contract)
            process, output = self.run_payload(json.dumps(contract, ensure_ascii=False))
            validator_accepts = not validator_errors
            bridge_accepts = output["status"] != "InvalidInput"
            if validator_accepts != bridge_accepts:
                disagreements.append(path.name)
            print(
                f"AUDIT {path.name}: validator={'pass' if validator_accepts else 'fail'} "
                f"smt={output['status']} warnings={[item['type'] for item in output['warnings']]}",
                flush=True,
            )
            self.assertEqual(process.returncode, 0 if bridge_accepts else 1)
        self.assertGreater(checked, 0)
        self.assertEqual(disagreements, [], f"validator/bridge disagreements: {disagreements}")


if __name__ == "__main__":
    unittest.main()
