from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BENCH = ROOT / "bench"
CORPUS = BENCH / "valid-corpus"
sys.path.insert(0, str(BENCH))

from generate_valid_contracts import canonical_bytes, generate  # noqa: E402


class ValidCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        result = subprocess.run(
            ["cabal", "list-bin", "exe:marlowe-smt"], cwd=ROOT,
            check=True, capture_output=True, text=True,
        )
        cls.binary = result.stdout.strip()
        with (CORPUS / "MANIFEST.csv").open(encoding="utf-8", newline="") as source:
            cls.rows = list(csv.DictReader(source))

    def test_manifest_files_hashes_and_reproduction(self) -> None:
        self.assertLessEqual(sum(path.stat().st_size for path in CORPUS.iterdir()), 2 * 1024 * 1024)
        self.assertEqual({row["family"] for row in self.rows}, {"F1", "F2", "F3", "F4", "F5", "C1"})
        for row in self.rows:
            with self.subTest(filename=row["filename"]):
                path = CORPUS / row["filename"]
                payload = path.read_bytes()
                self.assertEqual(len(payload), int(row["contract_bytes"]))
                self.assertEqual(hashlib.sha256(payload).hexdigest(), row["sha256"])
                regenerated = canonical_bytes(generate(
                    row["family"], int(row["n"]), int(row["k"]), row["nested_if"] == "true",
                ))
                self.assertEqual(payload, regenerated)

    def test_smallest_contracts_retain_expected_status(self) -> None:
        for row in self.rows:
            if "smallest" not in row["reason"]:
                continue
            with self.subTest(filename=row["filename"]):
                process = subprocess.run(
                    [self.binary, "--solver-timeout-ms", "30000"],
                    input=(CORPUS / row["filename"]).read_bytes(),
                    capture_output=True, check=False, timeout=40,
                )
                self.assertEqual(process.returncode, 0, process.stderr.decode())
                self.assertEqual(json.loads(process.stdout)["status"], row["expected_status"])


if __name__ == "__main__":
    unittest.main()
