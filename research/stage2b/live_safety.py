"""Preflight controls shared by research-only live experiments."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
import hashlib
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import urlsplit

EXPERIMENT_VERSION = "live-stage2b-corridor-v1"
STAGE2A_AGGREGATE_SHA256 = "897249e3d355121e7cf8304e8b336dc0a4118515b4bf847f7fb8b8efad587a46"


class LivePreflightError(RuntimeError):
    """A safe local preflight failure code, never a provider exception string."""


def _git(root: Path, *args: str) -> str:
    try:
        result = subprocess.run(["git", *args], cwd=root, stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, check=False)
    except OSError as exc:
        raise LivePreflightError("LIVE_EXECUTION_BLOCKED_GIT_UNAVAILABLE") from exc
    if result.returncode != 0:
        raise LivePreflightError("LIVE_EXECUTION_BLOCKED_GIT_UNAVAILABLE")
    return result.stdout.strip()


def current_git_sha(root: Path) -> str:
    sha = _git(root, "rev-parse", "--verify", "HEAD")
    if len(sha) != 40 or any(character not in "0123456789abcdef" for character in sha):
        raise LivePreflightError("LIVE_EXECUTION_BLOCKED_GIT_UNAVAILABLE")
    return sha


def working_tree_status(root: Path) -> str:
    return _git(root, "status", "--porcelain=v1", "--untracked-files=all")


def require_clean_worktree(root: Path) -> str:
    sha = current_git_sha(root)
    if working_tree_status(root):
        raise LivePreflightError("LIVE_EXECUTION_BLOCKED_DIRTY_WORKTREE")
    return sha


def summary_path(raw_output: Path) -> Path:
    return Path(str(raw_output) + ".summary.json")


def validate_live_outputs(raw_output: Path, root: Path) -> Path:
    repository = root.resolve()
    raw = raw_output.resolve()
    summary = summary_path(raw_output).resolve()
    if not raw.parent.is_dir():
        raise LivePreflightError("LIVE_EXECUTION_BLOCKED_OUTPUT_DIRECTORY_MISSING")
    for path in (raw, summary):
        if path == repository or repository in path.parents:
            raise LivePreflightError("LIVE_EXECUTION_BLOCKED_OUTPUT_INSIDE_REPOSITORY")
        if path.exists():
            raise LivePreflightError("LIVE_EXECUTION_BLOCKED_OUTPUT_EXISTS")
    return summary_path(raw_output)


def raw_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_execution_summary(raw_output: Path, summary: dict) -> Path:
    sidecar = summary_path(raw_output)
    payload = {**summary, "raw_output_basename": raw_output.name,
               "raw_output_sha256": raw_sha256(raw_output)}
    with sidecar.open("x", encoding="utf-8") as writer:
        json.dump(payload, writer, ensure_ascii=False, indent=2)
        writer.write("\n")
        writer.flush()
        os.fsync(writer.fileno())
    return sidecar


def require_same_experiment_identity(first: dict, second: dict) -> None:
    for field in ("experiment_version", "code_sha", "model"):
        if not first.get(field) or first[field] != second.get(field):
            raise ValueError(f"experiment identity mismatch: {field}")


@dataclass(frozen=True)
class LiveBudget:
    requested_calls: int
    hard_cap: int
    max_spend_usd: Decimal
    per_request_cost_ceiling_usd: Decimal
    money_limited_calls: int
    effective_calls: int

    def to_dict(self) -> dict:
        return {
            "requested_physical_calls": self.requested_calls,
            "hard_physical_call_cap": self.hard_cap,
            "max_spend_usd": str(self.max_spend_usd),
            "per_request_cost_ceiling_usd": str(self.per_request_cost_ceiling_usd),
            "money_limited_calls": self.money_limited_calls,
            "effective_physical_calls": self.effective_calls,
            "maximum_declared_spend_usd": str(
                self.effective_calls * self.per_request_cost_ceiling_usd),
        }


def make_live_budget(requested: int, hard_cap: int, maximum: str, ceiling: str) -> LiveBudget:
    if requested < 1 or requested > hard_cap:
        raise ValueError(f"physical-call limit must be between 1 and {hard_cap}")
    try:
        max_spend = Decimal(maximum)
        per_request = Decimal(ceiling)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("USD limits must be Decimal-compatible") from exc
    if not max_spend.is_finite() or not per_request.is_finite() or max_spend <= 0 or per_request <= 0:
        raise ValueError("USD limits must be finite and positive")
    money_calls = int((max_spend / per_request).to_integral_value(rounding=ROUND_FLOOR))
    effective = min(requested, hard_cap, money_calls)
    if effective < 1:
        raise ValueError("monetary budget allows zero physical calls")
    return LiveBudget(requested, hard_cap, max_spend, per_request, money_calls, effective)


def safe_transport_metadata(reasoner) -> dict:
    base_url = getattr(reasoner, "base_url", None)
    return {"api_style": getattr(reasoner, "api_style", None),
            "provider_host": urlsplit(base_url).hostname if isinstance(base_url, str) else None,
            "timeout_seconds": getattr(reasoner, "timeout_seconds", None),
            "max_tokens": getattr(reasoner, "max_tokens", None),
            "retry_attempts": getattr(reasoner, "retry_attempts", None)}
