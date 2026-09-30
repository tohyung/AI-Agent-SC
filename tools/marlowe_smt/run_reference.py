#!/usr/bin/env python3
"""Run explicit traces through the pinned Marlowe reference semantics."""

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
DRIVER_VERSION = "0.1.0"


def _failure(status: str, reason: str) -> dict[str, Any]:
    return {
        "status": status,
        "meta": {
            "upstream_commit": UPSTREAM_COMMIT,
            "reference_driver_version": DRIVER_VERSION,
        },
        "steps": [],
        "detail": {"reason": reason},
    }


def _binary() -> str:
    override = os.environ.get("MARLOWE_REFERENCE_BIN")
    if override:
        return override
    result = subprocess.run(
        ["cabal", "list-bin", "exe:marlowe-reference"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def execute(
    request: dict[str, Any] | str,
    *,
    hard_timeout_seconds: float = 30.0,
    binary: str | None = None,
) -> dict[str, Any]:
    payload = request if isinstance(request, str) else json.dumps(request, ensure_ascii=False)
    try:
        command = [binary or _binary()]
        result = subprocess.run(
            command,
            input=payload,
            text=True,
            capture_output=True,
            timeout=hard_timeout_seconds,
            check=False,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        return _failure("Unavailable", f"reference binary unavailable: {type(exc).__name__}")
    except subprocess.TimeoutExpired:
        return _failure("Timeout", f"hard timeout after {hard_timeout_seconds:g} seconds")

    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError:
        return _failure("InternalError", "reference driver emitted invalid JSON")
    if not isinstance(output, dict):
        return _failure("InternalError", "reference driver did not return a JSON object")
    meta = output.get("meta")
    if not isinstance(meta, dict) or meta.get("upstream_commit") != UPSTREAM_COMMIT:
        return _failure("InternalError", "reference driver upstream commit mismatch")
    if meta.get("reference_driver_version") != DRIVER_VERSION:
        return _failure("InternalError", "reference driver version mismatch")
    if result.returncode and output.get("status") not in {"InvalidInput"}:
        return _failure("InternalError", f"reference driver exited with code {result.returncode}")
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hard-timeout", type=float, default=30.0)
    parser.add_argument("--binary")
    args = parser.parse_args()
    output = execute(
        sys.stdin.read(),
        hard_timeout_seconds=args.hard_timeout,
        binary=args.binary,
    )
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if output["status"] in {"Success", "TransactionError", "Unsupported"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
