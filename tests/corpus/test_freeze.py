"""Regression tests for the Corpus v1 freeze verifier."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import shutil
import subprocess

import pytest

from research.corpus import verify_freeze


MANIFEST = (verify_freeze.ROOT / "research/corpus/freeze/Corpus-v1.manifest.json")


def _modified_manifest(tmp_path, change):
    data = deepcopy(json.loads(MANIFEST.read_text(encoding="utf-8")))
    change(data)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_real_corpus_v1_manifest_verifies():
    assert verify_freeze.verify_freeze(MANIFEST) == (
        "897249e3d355121e7cf8304e8b336dc0a4118515b4bf847f7fb8b8efad587a46"
    )


@pytest.fixture
def crlf_checkout(tmp_path):
    checkout = tmp_path / "checkout"
    subprocess.run([
        "git", "clone", "--quiet", "--no-hardlinks", "--no-checkout",
        str(verify_freeze.ROOT), str(checkout),
    ], check=True)
    subprocess.run(["git", "-C", str(checkout), "config", "core.autocrlf", "true"], check=True)
    subprocess.run([
        "git", "-C", str(checkout), "checkout", "--quiet", "--detach",
        verify_freeze.SOURCE_COMMIT,
    ], check=True)
    # The source commit has the pre-renaming layout; lay the CRLF files out where the
    # current code reads them, as a checkout of today's tree would.
    for source, current in verify_freeze.CURRENT_PATHS.items():
        (checkout / current).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(checkout / source, checkout / current)
    return checkout


def test_crlf_checkout_does_not_change_canonical_hash(crlf_checkout):
    path = crlf_checkout / "research/corpus/corpus/development.jsonl"
    worktree_bytes = path.read_bytes()
    assert b"\r\n" in worktree_bytes
    assert sha256(worktree_bytes).hexdigest() != json.loads(
        MANIFEST.read_text(encoding="utf-8"))["artifacts"][0]["sha256"]
    assert verify_freeze.verify_freeze(MANIFEST, root=crlf_checkout) == (
        "897249e3d355121e7cf8304e8b336dc0a4118515b4bf847f7fb8b8efad587a46"
    )


def test_semantic_tracked_change_fails_even_with_correct_blob_hash(crlf_checkout):
    path = crlf_checkout / "research/corpus/corpus/development.jsonl"
    with path.open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(verify_freeze.FreezeVerificationError,
                       match="semantic core differs from source_commit"):
        verify_freeze.verify_freeze(MANIFEST, root=crlf_checkout)


@pytest.mark.parametrize("index, name", [(0, "development"), (1, "validation")])
def test_wrong_corpus_artifact_hash_fails(tmp_path, index, name):
    path = _modified_manifest(
        tmp_path, lambda data: data["artifacts"][index].update(sha256="0" * 64))
    with pytest.raises(verify_freeze.FreezeVerificationError, match=f"{name}.*sha256"):
        verify_freeze.verify_freeze(path)


def test_wrong_byte_count_fails(tmp_path):
    path = _modified_manifest(
        tmp_path, lambda data: data["artifacts"][0].update(bytes=1))
    with pytest.raises(verify_freeze.FreezeVerificationError, match="development.*bytes"):
        verify_freeze.verify_freeze(path)


def test_wrong_aggregate_hash_fails(tmp_path):
    path = _modified_manifest(
        tmp_path, lambda data: data.update(aggregate_sha256="0" * 64))
    with pytest.raises(verify_freeze.FreezeVerificationError, match="aggregate_sha256"):
        verify_freeze.verify_freeze(path)


def test_missing_artifact_fails(tmp_path):
    path = _modified_manifest(tmp_path, lambda data: data["artifacts"].pop())
    with pytest.raises(verify_freeze.FreezeVerificationError, match="artifact paths/order"):
        verify_freeze.verify_freeze(path)


def test_wrong_case_count_fails(tmp_path):
    path = _modified_manifest(
        tmp_path, lambda data: data["counts"].update(total_cases=31))
    with pytest.raises(verify_freeze.FreezeVerificationError, match="manifest counts"):
        verify_freeze.verify_freeze(path)


def test_wrong_claim_taxonomy_fails(tmp_path):
    path = _modified_manifest(
        tmp_path, lambda data: data["claim_kinds"].append("notify_success_recipient"))
    with pytest.raises(verify_freeze.FreezeVerificationError, match="claim_kinds"):
        verify_freeze.verify_freeze(path)
