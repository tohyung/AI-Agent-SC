#!/usr/bin/env python3
"""Verify the immutable Stage 2A v1 semantic corpus snapshot."""

from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from research.stage2a import foundation  # noqa: E402


VERSION = "stage2a-v1"
SOURCE_COMMIT = "a6ea94587783d45ffc68406dd856a636a59874ed"
UPSTREAM_COMMIT = "7b5b1e900ec53a8eb18747992bec73470704dfcb"
DRIVER_VERSION = "0.1.0"
ARTIFACT_PATHS = tuple(sorted((
    "research/stage2a/corpus/development.jsonl",
    "research/stage2a/corpus/validation.jsonl",
    "research/stage2a/foundation.py",
    "research/stage2a/protocol.md",
)))
EXPECTED_COUNTS = {
    "total_cases": 32,
    "canonical_cases": 20,
    "mutations": 12,
    "development": 16,
    "validation": 16,
    "resolutions": {
        "accepted_interpretation": 12,
        "clarification_required": 16,
        "conflict_requires_resolution": 3,
        "unsupported_for_current_study": 1,
    },
    "annotation_status": {"draft": 32},
}


class FreezeVerificationError(ValueError):
    """A manifest or frozen artifact differs from the Stage 2A v1 snapshot."""


def _check(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise FreezeVerificationError(f"{label}: expected {expected!r}, got {actual!r}")


def _corpus_counts(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_cases": len(records),
        "canonical_cases": sum(record["mutation"] is None for record in records),
        "mutations": sum(record["mutation"] is not None for record in records),
        "development": sum(record["split"] == "development" for record in records),
        "validation": sum(record["split"] == "validation" for record in records),
        "resolutions": dict(Counter(record["expected_resolution"] for record in records)),
        "annotation_status": dict(Counter(record["annotation"]["status"] for record in records)),
    }


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, stdin=subprocess.DEVNULL,
        check=False,
    )


def _require_git_success(root: Path, label: str, *args: str) -> bytes:
    result = _git(root, *args)
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise FreezeVerificationError(f"{label}: {detail or 'git command failed'}")
    return result.stdout


def verify_freeze(manifest_path: Path, *, root: Path = ROOT) -> str:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise FreezeVerificationError("manifest must be a JSON object")
    _check(manifest.get("corpus_version"), VERSION, "corpus_version")
    _check(manifest.get("freeze_type"), "public_research_corpus_semantic_freeze", "freeze_type")
    _check(manifest.get("source_commit"), SOURCE_COMMIT, "source_commit")
    _check(manifest.get("schema_version"), 1, "schema_version")
    _check(manifest.get("reference_semantics"), {
        "upstream_commit": UPSTREAM_COMMIT,
        "reference_driver_version": DRIVER_VERSION,
    }, "reference_semantics")
    repo_root = _require_git_success(root, "not a Git repository", "rev-parse", "--show-toplevel")
    _check(Path(repo_root.decode("utf-8").strip()).resolve(), root.resolve(), "repository root")
    _require_git_success(root, "source_commit missing", "cat-file", "-e", f"{SOURCE_COMMIT}^{{commit}}")
    _check(manifest.get("hash_basis"), {
        "type": "git_blob_content",
        "source_commit": SOURCE_COMMIT,
        "note": "Hashes and byte counts are computed from exact Git blob contents at source_commit, independent of checkout line-ending conversion.",
    }, "hash_basis")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or any(not isinstance(item, dict) for item in artifacts):
        raise FreezeVerificationError("artifacts must be a list of objects")
    paths = [item.get("path") for item in artifacts]
    _check(paths, list(ARTIFACT_PATHS), "artifact paths/order")

    aggregate_lines = []
    for item in artifacts:
        path = item["path"]
        _check(item.get("source"), "git_blob_at_source_commit", f"{path} source")
        data = _require_git_success(root, f"{path} Git blob", "show", f"{SOURCE_COMMIT}:{path}")
        digest = sha256(data).hexdigest()
        _check(item.get("sha256"), digest, f"{path} sha256")
        if type(item.get("bytes")) is not int:
            raise FreezeVerificationError(f"{path} bytes: expected integer byte count")
        _check(item["bytes"], len(data), f"{path} bytes")
        aggregate_lines.append(f"{path}\t{digest}\n")
    aggregate = sha256("".join(aggregate_lines).encode("utf-8")).hexdigest()
    _check(manifest.get("aggregate_sha256"), aggregate, "aggregate_sha256")

    diff = _git(root, "diff", "--quiet", SOURCE_COMMIT, "--", *ARTIFACT_PATHS)
    if diff.returncode != 0:
        raise FreezeVerificationError("semantic core differs from source_commit")

    records = foundation.load_corpus(root / "research/stage2a/corpus")
    errors = foundation.validate(records)
    if errors:
        raise FreezeVerificationError("corpus validation failed: " + "; ".join(errors))
    counts = _corpus_counts(records)
    _check(counts, EXPECTED_COUNTS, "corpus counts")
    _check(manifest.get("counts"), counts, "manifest counts")
    _check(manifest.get("claim_kinds"), sorted(foundation.CLAIM_KINDS), "claim_kinds")
    return aggregate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    try:
        aggregate = verify_freeze(args.manifest)
    except (FreezeVerificationError, OSError, json.JSONDecodeError) as exc:
        print(f"FREEZE VERIFICATION FAILED: {exc}", file=sys.stderr)
        return 2
    print(f"FREEZE VERIFIED: {VERSION}")
    print(f"aggregate_sha256={aggregate}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
