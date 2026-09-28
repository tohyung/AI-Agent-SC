#!/usr/bin/env python3
"""Measure concurrent independent SMT jobs, including aggregate process-tree RSS."""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import signal
import statistics
import subprocess
import time

from generate_valid_contracts import canonical_bytes, generate
from run_valid_bench import binary_path, process_group_rss


BENCH = Path(__file__).resolve().parent
DEFAULT_OUTPUT = BENCH / "parallel-valid-summary.csv"
FIELDS = [
    "concurrency", "batch", "family", "n", "k", "nested_if",
    "statuses", "job_seconds", "median_job_seconds", "group_seconds",
    "group_peak_rss_kb", "slowdown_vs_n1",
]


def run_batch(binary: str, payload: bytes, concurrency: int, hard_timeout: float,
              solver_timeout_ms: int) -> dict[str, object]:
    processes: list[subprocess.Popen[bytes]] = []
    started = time.perf_counter()
    for _ in range(concurrency):
        process = subprocess.Popen(
            [binary, "--solver-timeout-ms", str(solver_timeout_ms)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=True,
        )
        assert process.stdin is not None
        process.stdin.write(payload)
        process.stdin.close()
        processes.append(process)

    peak = 0
    ended: dict[int, float] = {}
    timed_out: set[int] = set()
    while len(ended) != len(processes):
        now = time.perf_counter()
        aggregate = 0
        for process in processes:
            if process.pid in ended:
                continue
            total, _, _ = process_group_rss(process.pid)
            aggregate += total
            if process.poll() is not None:
                ended[process.pid] = now
            elif now - started >= hard_timeout:
                timed_out.add(process.pid)
                os.killpg(process.pid, signal.SIGKILL)
                ended[process.pid] = now
        peak = max(peak, aggregate)
        if len(ended) != len(processes):
            time.sleep(0.05)

    statuses: list[str] = []
    durations: list[float] = []
    for process in processes:
        process.wait()
        durations.append(ended[process.pid] - started)
        assert process.stdout is not None and process.stderr is not None
        stdout = process.stdout.read()
        stderr = process.stderr.read().decode("utf-8", errors="replace")
        if process.pid in timed_out:
            statuses.append("Timeout")
            continue
        try:
            statuses.append(json.loads(stdout)["status"])
        except (json.JSONDecodeError, KeyError) as error:
            statuses.append(f"ProcessError:{process.returncode}:{error}:{stderr.strip()}")
    return {
        "statuses": "|".join(statuses),
        "job_seconds": "|".join(f"{value:.3f}" for value in durations),
        "median_job_seconds": statistics.median(durations),
        "group_seconds": max(durations),
        "group_peak_rss_kb": peak,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--family", default="F3")
    parser.add_argument("--n", type=int, default=64)
    parser.add_argument("--k", type=int, default=4)
    parser.add_argument("--nested-if", action="store_true")
    parser.add_argument("--hard-timeout", type=float, default=120.0)
    parser.add_argument("--solver-timeout-ms", type=int, default=115_000)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    binary = binary_path()
    payload = canonical_bytes(generate(args.family, args.n, args.k, args.nested_if))
    rows: list[dict[str, object]] = []
    baseline_median: float | None = None
    for concurrency in (1, 2, 4):
        for batch in range(1, 4):
            result = run_batch(binary, payload, concurrency, args.hard_timeout, args.solver_timeout_ms)
            if concurrency == 1 and batch == 3:
                baseline_median = statistics.median(float(row["median_job_seconds"]) for row in rows + [result])
            slowdown = "" if baseline_median is None else float(result["median_job_seconds"]) / baseline_median
            row = {
                "concurrency": concurrency, "batch": batch, "family": args.family,
                "n": args.n, "k": args.k, "nested_if": str(args.nested_if).lower(),
                **result, "slowdown_vs_n1": "" if slowdown == "" else f"{slowdown:.3f}",
            }
            rows.append(row)
            with args.output.open("w", encoding="utf-8", newline="") as output:
                writer = csv.DictWriter(output, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerows(rows)
            print(json.dumps(row, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    main()
