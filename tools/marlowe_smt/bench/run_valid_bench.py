#!/usr/bin/env python3
"""Measure deterministic Valid-side contracts and the matched SAT control."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import signal
import statistics
import subprocess
import time
from typing import Any

from generate_valid_contracts import FAMILIES, canonical_bytes, count_cases, generate


ROOT = Path(__file__).resolve().parents[1]
BENCH = Path(__file__).resolve().parent
RESULTS = BENCH / "results"
DEFAULT_OUTPUT = BENCH / "stress-valid-summary.csv"
DEFAULT_BASELINE_OUTPUT = BENCH / "startup-valid-baseline.csv"
DEFAULT_GRID = (1, 2, 4, 8, 12, 16, 20, 32, 48, 64)
K_GRID = (1, 2, 4)
VALID_STATUSES = {"Valid", "Counterexample", "Indeterminate", "Timeout"}
FIELDS = [
    "family", "n", "k", "nested_if", "branches", "contract_bytes", "sha256",
    "status_1", "seconds_1", "tree_rss_kb_1", "driver_rss_kb_1", "z3_seen_1", "net_seconds_1",
    "status_2", "seconds_2", "tree_rss_kb_2", "driver_rss_kb_2", "z3_seen_2", "net_seconds_2",
    "status_3", "seconds_3", "tree_rss_kb_3", "driver_rss_kb_3", "z3_seen_3", "net_seconds_3",
]


def binary_path() -> str:
    result = subprocess.run(
        ["cabal", "list-bin", "exe:marlowe-smt"], cwd=ROOT,
        check=True, capture_output=True, text=True,
    )
    return result.stdout.strip()


def _proc_info(pid: int) -> tuple[int, int, str] | None:
    try:
        stat = (Path("/proc") / str(pid) / "stat").read_text(encoding="utf-8")
        close = stat.rfind(")")
        fields = stat[close + 2:].split()
        pgrp = int(fields[2])
        status = (Path("/proc") / str(pid) / "status").read_text(encoding="utf-8")
        rss = 0
        name = ""
        for line in status.splitlines():
            if line.startswith("VmRSS:"):
                rss = int(line.split()[1])
            elif line.startswith("Name:"):
                name = line.split(maxsplit=1)[1]
        return pgrp, rss, name
    except (FileNotFoundError, ProcessLookupError, PermissionError, ValueError, IndexError):
        return None


def process_group_rss(pgid: int) -> tuple[int, int, bool]:
    total = 0
    driver = 0
    z3_seen = False
    try:
        entries = os.scandir("/proc")
    except FileNotFoundError:
        return 0, 0, False
    with entries:
        for entry in entries:
            if not entry.name.isdigit():
                continue
            pid = int(entry.name)
            info = _proc_info(pid)
            if info is None or info[0] != pgid:
                continue
            total += info[1]
            if pid == pgid:
                driver = info[1]
            if info[2].lower().startswith("z3"):
                z3_seen = True
    return total, driver, z3_seen


def run_once(binary: str, payload: bytes, hard_timeout: float, solver_timeout_ms: int) -> dict[str, Any]:
    process = subprocess.Popen(
        [binary, "--solver-timeout-ms", str(solver_timeout_ms)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    assert process.stdin is not None
    process.stdin.write(payload)
    process.stdin.close()
    started = time.perf_counter()
    peak_total = 0
    peak_driver = 0
    saw_z3 = False
    timed_out = False
    while process.poll() is None:
        total, driver, z3_seen = process_group_rss(process.pid)
        peak_total = max(peak_total, total)
        peak_driver = max(peak_driver, driver)
        saw_z3 = saw_z3 or z3_seen
        if time.perf_counter() - started >= hard_timeout:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            break
        time.sleep(0.05)
    total, driver, z3_seen = process_group_rss(process.pid)
    peak_total = max(peak_total, total)
    peak_driver = max(peak_driver, driver)
    saw_z3 = saw_z3 or z3_seen
    process.wait()
    assert process.stdout is not None and process.stderr is not None
    stdout = process.stdout.read()
    stderr = process.stderr.read().decode("utf-8", errors="replace")
    elapsed = time.perf_counter() - started
    if timed_out:
        status = "Timeout"
    else:
        try:
            output = json.loads(stdout)
        except json.JSONDecodeError as error:
            raise RuntimeError(f"driver emitted invalid JSON: {error}; stderr={stderr!r}") from error
        status = output.get("status")
        if status not in VALID_STATUSES:
            raise RuntimeError(f"unexpected status {status!r}: {output}; stderr={stderr!r}")
    return {
        "status": status,
        "seconds": elapsed,
        "tree_rss_kb": peak_total,
        "driver_rss_kb": peak_driver,
        "z3_seen": saw_z3,
    }


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def row_key(row: dict[str, Any]) -> tuple[str, int, int, bool]:
    return (
        row["family"], int(row["n"]), int(row["k"]),
        row["nested_if"] if isinstance(row["nested_if"], bool) else row["nested_if"] == "true",
    )


def make_row(family: str, n: int, k: int, nested_if: bool, payload: bytes, branches: int) -> dict[str, Any]:
    return {
        "family": family,
        "n": n,
        "k": k,
        "nested_if": str(nested_if).lower(),
        "branches": branches,
        "contract_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def add_runs(row: dict[str, Any], runs: list[dict[str, Any]], baseline: float) -> None:
    for index, result in enumerate(runs, start=1):
        row[f"status_{index}"] = result["status"]
        row[f"seconds_{index}"] = f"{result['seconds']:.3f}"
        row[f"tree_rss_kb_{index}"] = result["tree_rss_kb"]
        row[f"driver_rss_kb_{index}"] = result["driver_rss_kb"]
        row[f"z3_seen_{index}"] = str(result["z3_seen"]).lower()
        row[f"net_seconds_{index}"] = f"{max(0.0, result['seconds'] - baseline):.3f}"


def parse_grid(raw: str) -> tuple[int, ...]:
    values = tuple(int(value) for value in raw.split(",") if value)
    if not values or any(value < 1 for value in values):
        raise argparse.ArgumentTypeError("grid must contain positive comma-separated integers")
    return values


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hard-timeout", type=float, default=120.0)
    parser.add_argument("--solver-timeout-ms", type=int, default=115_000)
    parser.add_argument("--max-minutes", type=float, default=90.0)
    parser.add_argument("--grid", type=parse_grid, default=DEFAULT_GRID)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--baseline-output", type=Path, default=DEFAULT_BASELINE_OUTPUT)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)
    binary = binary_path()
    overall_start = time.perf_counter()
    close_payload = canonical_bytes("close")
    if args.resume and args.output.exists() and args.baseline_output.exists():
        with args.output.open(encoding="utf-8", newline="") as source:
            rows = list(csv.DictReader(source))
        with args.baseline_output.open(encoding="utf-8", newline="") as source:
            saved_baseline = list(csv.DictReader(source))
        baseline = statistics.median(float(row["seconds"]) for row in saved_baseline)
        baseline_runs = saved_baseline
        print(json.dumps({"resume": True, "existing_rows": len(rows), "median_seconds": baseline}), flush=True)
    else:
        baseline_runs = [run_once(binary, close_payload, args.hard_timeout, args.solver_timeout_ms) for _ in range(10)]
        if any(run["status"] != "Valid" for run in baseline_runs):
            raise RuntimeError(f"baseline did not stay Valid: {baseline_runs}")
        baseline = statistics.median(run["seconds"] for run in baseline_runs)
        with args.baseline_output.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=("run", "status", "seconds", "tree_rss_kb", "driver_rss_kb", "z3_seen"))
            writer.writeheader()
            for index, run in enumerate(baseline_runs, start=1):
                writer.writerow({"run": index, **run})
        rows = []
        baseline_row = make_row("BASE", 0, 0, False, close_payload, 0)
        add_runs(baseline_row, baseline_runs[:3], baseline)
        rows.append(baseline_row)
        print(json.dumps({"baseline_runs": baseline_runs, "median_seconds": baseline}, separators=(",", ":")), flush=True)
        write_rows(args.output, rows)
    completed = {row_key(row): row for row in rows}

    exhausted = False
    for family in FAMILIES:
        expected = "Counterexample" if family == "C1" else "Valid"
        for nested_if in (False, True):
            for k in K_GRID:
                consecutive_failures = 0
                for n in args.grid:
                    if time.perf_counter() - overall_start >= args.max_minutes * 60:
                        exhausted = True
                        break
                    key = (family, n, k, nested_if)
                    if key in completed:
                        old = completed[key]
                        old_statuses = [old[f"status_{index}"] for index in range(1, 4)]
                        consecutive_failures = consecutive_failures + 1 if all(status != expected for status in old_statuses) else 0
                        if consecutive_failures >= 2:
                            break
                        continue
                    contract = generate(family, n, k, nested_if)
                    payload = canonical_bytes(contract)
                    contract_path = RESULTS / f"{family}-n{n}-k{k}{'-if' if nested_if else ''}.json"
                    contract_path.write_bytes(payload)
                    runs = [run_once(binary, payload, args.hard_timeout, args.solver_timeout_ms) for _ in range(3)]
                    row = make_row(family, n, k, nested_if, payload, count_cases(contract))
                    add_runs(row, runs, baseline)
                    rows.append(row)
                    completed[key] = row
                    write_rows(args.output, rows)
                    print(json.dumps(row, separators=(",", ":")), flush=True)
                    if all(run["status"] != expected for run in runs):
                        consecutive_failures += 1
                        if consecutive_failures >= 2:
                            break
                    else:
                        consecutive_failures = 0
                if exhausted:
                    break
            if exhausted:
                break
        if exhausted:
            break
    print(json.dumps({"complete": not exhausted, "rows": len(rows), "elapsed_seconds": time.perf_counter() - overall_start}), flush=True)


if __name__ == "__main__":
    main()
