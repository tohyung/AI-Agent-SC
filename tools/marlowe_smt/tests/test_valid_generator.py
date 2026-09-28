from __future__ import annotations

import hashlib
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
sys.path.insert(0, str(ROOT / "bench"))

from generate_valid_contracts import FAMILIES, canonical_bytes, generate  # noqa: E402
from marlowe_agent.marlowe_validator import validate_contract  # noqa: E402


class ValidGeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        result = subprocess.run(
            ["cabal", "list-bin", "exe:marlowe-smt"], cwd=ROOT,
            check=True, capture_output=True, text=True,
        )
        cls.binary = result.stdout.strip()

    def test_small_grid_is_deterministic_validated_and_has_expected_status(self) -> None:
        for family in FAMILIES:
            expected = "Counterexample" if family == "C1" else "Valid"
            for n in (1, 2, 3):
                for k in (1, 2):
                    for nested_if in (False, True):
                        with self.subTest(family=family, n=n, k=k, nested_if=nested_if):
                            first = generate(family, n, k, nested_if)
                            first_bytes = canonical_bytes(first)
                            second_bytes = canonical_bytes(generate(family, n, k, nested_if))
                            self.assertEqual(first_bytes, second_bytes)
                            self.assertEqual(
                                hashlib.sha256(first_bytes).hexdigest(),
                                hashlib.sha256(second_bytes).hexdigest(),
                            )
                            self.assertEqual(validate_contract(first), [])
                            process = subprocess.run(
                                [self.binary, "--solver-timeout-ms", "30000"],
                                input=first_bytes,
                                capture_output=True,
                                check=False,
                                timeout=40,
                            )
                            self.assertEqual(process.returncode, 0, process.stderr.decode())
                            output = json.loads(process.stdout)
                            self.assertEqual(output["status"], expected, output)


if __name__ == "__main__":
    unittest.main()
