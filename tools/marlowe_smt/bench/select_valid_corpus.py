#!/usr/bin/env python3
"""Materialize the bounded, reproducible subset of the Valid-side benchmark."""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path
import statistics

from generate_valid_contracts import canonical_bytes, count_cases, generate


BENCH = Path(__file__).resolve().parent
SUMMARY = BENCH / "stress-valid-summary.csv"
CORPUS = BENCH / "valid-corpus"
LIMIT = 2 * 1024 * 1024
FIELDS = [
    "filename", "family", "n", "k", "nested_if", "branches", "contract_bytes",
    "sha256", "expected_status", "median_seconds", "reason",
]

# The complete candidate set (including the first timeout) exceeds 2 MiB. These
# entries retain every family's endpoints and every 1 s / 5 s knee that fits.
SELECTIONS = {
    ("F1", 1, 1, False): "smallest",
    ("F1", 128, 4, True): "heaviest-valid",
    ("F2", 1, 1, False): "smallest",
    ("F2", 128, 4, True): "heaviest-valid",
    ("F3", 1, 1, False): "smallest",
    ("F3", 12, 4, True): "knee-1s",
    ("F3", 48, 1, True): "knee-5s",
    ("F3", 128, 1, False): "heaviest-valid;knee-30s",
    ("F4", 1, 1, False): "smallest",
    ("F4", 32, 2, True): "knee-1s",
    ("F4", 64, 4, True): "heaviest-valid;knee-5s",
    ("F5", 1, 1, False): "smallest",
    ("F5", 64, 4, True): "heaviest-valid;knee-1s",
    ("C1", 1, 1, False): "smallest",
    ("C1", 64, 4, True): "heaviest-counterexample;knee-1s",
}


def main() -> None:
    with SUMMARY.open(encoding="utf-8", newline="") as source:
        measured = {
            (row["family"], int(row["n"]), int(row["k"]), row["nested_if"] == "true"): row
            for row in csv.DictReader(source)
        }
    CORPUS.mkdir(exist_ok=True)
    for old in CORPUS.glob("*.json"):
        old.unlink()

    manifest: list[dict[str, object]] = []
    for key, reason in SELECTIONS.items():
        family, n, k, nested_if = key
        source = measured[key]
        payload = canonical_bytes(generate(family, n, k, nested_if))
        suffix = "-if" if nested_if else ""
        filename = f"{family}-n{n}-k{k}{suffix}.json"
        (CORPUS / filename).write_bytes(payload)
        statuses = [source[f"status_{index}"] for index in range(1, 4)]
        expected = "Counterexample" if family == "C1" else "Valid"
        if any(status != expected for status in statuses):
            raise RuntimeError(f"selected endpoint has unexpected status: {key}: {statuses}")
        manifest.append({
            "filename": filename, "family": family, "n": n, "k": k,
            "nested_if": str(nested_if).lower(), "branches": count_cases(generate(*key)),
            "contract_bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(),
            "expected_status": expected,
            "median_seconds": f"{statistics.median(float(source[f'seconds_{i}']) for i in range(1, 4)):.3f}",
            "reason": reason,
        })

    manifest_path = CORPUS / "MANIFEST.csv"
    with manifest_path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(manifest)
    total = sum(path.stat().st_size for path in CORPUS.iterdir() if path.is_file())
    if total > LIMIT:
        raise RuntimeError(f"corpus is {total} bytes, over {LIMIT}-byte limit")
    print(f"wrote {len(manifest)} contracts; corpus size {total} bytes")


if __name__ == "__main__":
    main()
