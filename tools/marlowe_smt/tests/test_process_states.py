from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "bench"))

from generate_contracts import generate  # noqa: E402
from run_smt import analyze  # noqa: E402


class ProcessStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        result = subprocess.run(
            ["cabal", "list-bin", "exe:marlowe-smt"], cwd=ROOT,
            check=True, capture_output=True, text=True,
        )
        cls.binary = result.stdout.strip()
        cls.heavy = generate(20, 4, True)

    def test_solver_timeout_is_indeterminate(self) -> None:
        result = subprocess.run(
            [self.binary, "--solver-timeout-ms", "1"],
            input=json.dumps(self.heavy, separators=(",", ":")),
            text=True,
            capture_output=True,
            check=True,
            timeout=10,
        )
        output = json.loads(result.stdout)
        self.assertEqual(output["status"], "Indeterminate")
        self.assertIn("timeout", output["solver_result"].lower())

    def test_hard_timeout_is_never_valid(self) -> None:
        output = analyze(
            self.heavy,
            hard_timeout_seconds=0.000001,
            solver_timeout_ms=300_000,
            binary=self.binary,
        )
        self.assertEqual(output["status"], "Timeout")
        self.assertEqual(output["process_exit"], 124)
        self.assertNotEqual(output["status"], "Valid")


if __name__ == "__main__":
    unittest.main()
