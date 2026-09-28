#!/usr/bin/env python3
"""Hard-timeout subprocess wrapper for the standalone Marlowe SMT driver."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parent
UPSTREAM_COMMIT = "7b5b1e900ec53a8eb18747992bec73470704dfcb"
DRIVER_VERSION = "0.2.0"


def _binary() -> str:
    override = os.environ.get("MARLOWE_SMT_BIN")
    if override:
        return override
    result = subprocess.run(
        ["cabal", "list-bin", "exe:marlowe-smt"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _base(status: str) -> dict[str, Any]:
    return {
        "status": status,
        "warnings": [],
        "counterexample": None,
        "analysis_notes": [],
        "meta": {
            "solver": "z3 (subprocess did not complete)",
            "upstream_commit": UPSTREAM_COMMIT,
            "driver_version": DRIVER_VERSION,
        },
    }


def analyze(
    contract: dict[str, Any] | str,
    *,
    hard_timeout_seconds: float = 90.0,
    solver_timeout_ms: int | None = 60_000,
    binary: str | None = None,
) -> dict[str, Any]:
    payload = contract if isinstance(contract, str) else json.dumps(contract, ensure_ascii=False)
    command = [binary or _binary()]
    if solver_timeout_ms is not None:
        command.extend(["--solver-timeout-ms", str(solver_timeout_ms)])
    try:
        result = subprocess.run(
            command,
            input=payload,
            text=True,
            capture_output=True,
            timeout=hard_timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        output = _base("Timeout")
        output["error"] = f"hard timeout after {hard_timeout_seconds:g} seconds"
        output["process_exit"] = 124
        return output

    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        output = _base("Indeterminate")
        output["solver_result"] = f"driver emitted invalid JSON: {error}"
    output["process_exit"] = result.returncode
    if result.stderr:
        output["stderr"] = result.stderr.rstrip()
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hard-timeout", type=float, default=90.0)
    parser.add_argument("--solver-timeout-ms", type=int, default=60_000)
    parser.add_argument("--binary")
    args = parser.parse_args()
    output = analyze(
        sys.stdin.read(),
        hard_timeout_seconds=args.hard_timeout,
        solver_timeout_ms=args.solver_timeout_ms,
        binary=args.binary,
    )
    print(json.dumps(output, ensure_ascii=False, separators=(",", ":")))
    return 0 if output["status"] not in {"InvalidInput", "Timeout"} else int(output.get("process_exit", 1))


if __name__ == "__main__":
    raise SystemExit(main())
