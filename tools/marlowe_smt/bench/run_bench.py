#!/usr/bin/env python3
"""Run the pinned stress grid three times with GNU time and a hard timeout."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any

from generate_contracts import generate


ROOT = Path(__file__).resolve().parents[1]
RESULTS = Path(__file__).resolve().parent / "results"
DEFAULT_GRID = (1, 2, 3, 5, 8, 12, 16, 20)
K_GRID = (1, 2, 4)
TIME_RE = re.compile(r"Elapsed \(wall clock\) time .*: (?:(\d+):)?(\d+):(\d+(?:\.\d+)?)")
RSS_RE = re.compile(r"Maximum resident set size \(kbytes\): (\d+)")


def binary_path() -> str:
    result = subprocess.run(
        ["cabal", "list-bin", "exe:marlowe-smt"], cwd=ROOT,
        check=True, capture_output=True, text=True,
    )
    return result.stdout.strip()


def elapsed_seconds(metrics: str) -> float:
    match = TIME_RE.search(metrics)
    if not match:
        raise ValueError(f"elapsed time missing from metrics: {metrics}")
    hours = int(match.group(1) or 0)
    return hours * 3600 + int(match.group(2)) * 60 + float(match.group(3))


def run_once(binary: str, contract: Any, hard_timeout: int) -> dict[str, Any]:
    RESULTS.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=RESULTS, suffix=".json", delete=False) as contract_file:
        json.dump(contract, contract_file, separators=(",", ":"))
        contract_path = Path(contract_file.name)
    metrics_path = contract_path.with_suffix(".time")
    with contract_path.open("r", encoding="utf-8") as stdin:
        process = subprocess.run(
            ["/usr/bin/time", "-v", "-o", str(metrics_path), "timeout", str(hard_timeout), binary],
            stdin=stdin, capture_output=True, text=True, check=False,
        )
    metrics = metrics_path.read_text(encoding="utf-8")
    if process.returncode == 124:
        status = "Timeout"
    elif process.returncode != 0:
        status = f"ProcessError({process.returncode})"
    else:
        status = json.loads(process.stdout)["status"]
    return {
        "status": status,
        "seconds": elapsed_seconds(metrics),
        "rss_kb": int(RSS_RE.search(metrics).group(1)),
        "exit": process.returncode,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hard-timeout", type=int, default=300)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "stress-summary.csv")
    args = parser.parse_args()
    binary = binary_path()
    rows: list[dict[str, Any]] = []
    for nested_if in (False, True):
        for k in K_GRID:
            consecutive_timeouts = 0
            for n in DEFAULT_GRID:
                contract = generate(n, k, nested_if)
                runs = [run_once(binary, contract, args.hard_timeout) for _ in range(3)]
                row: dict[str, Any] = {
                    "n": n,
                    "k": k,
                    "nested_if": str(nested_if).lower(),
                    "branches": n * k,
                }
                for index, result in enumerate(runs, start=1):
                    row[f"status_{index}"] = result["status"]
                    row[f"seconds_{index}"] = f"{result['seconds']:.2f}"
                    row[f"rss_kb_{index}"] = result["rss_kb"]
                rows.append(row)
                print(json.dumps(row, separators=(",", ":")), flush=True)
                if all(run["status"] == "Timeout" for run in runs):
                    consecutive_timeouts += 1
                    if consecutive_timeouts >= 2:
                        break
                else:
                    consecutive_timeouts = 0
    fieldnames = [
        "n", "k", "nested_if", "branches",
        "status_1", "seconds_1", "rss_kb_1",
        "status_2", "seconds_2", "rss_kb_2",
        "status_3", "seconds_3", "rss_kb_3",
    ]
    with args.output.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
