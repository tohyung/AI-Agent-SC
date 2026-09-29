"""Unwired Node 3 decision-policy prototype.

No production pipeline module imports this file in Stage 0.9.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any


SEMANTIC_STATUSES = {"valid", "counterexample", "indeterminate", "timeout", "unavailable"}
INCONCLUSIVE_STATUSES = {"indeterminate", "timeout", "unavailable"}


@dataclass
class StructuredWarning:
    type: str
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class Node3Result:
    lint_errors: list[str]
    lint_warnings: list[str]
    semantic_status: str
    semantic_warnings: list[StructuredWarning]
    counterexample: dict[str, Any] | None
    analysis_notes: list[str]
    smt_elapsed_seconds: float | None
    contract: Any = None

    def __post_init__(self) -> None:
        self.semantic_status = self.semantic_status.lower()
        if self.semantic_status not in SEMANTIC_STATUSES:
            raise ValueError(f"unsupported semantic status: {self.semantic_status}")
        if self.semantic_status in INCONCLUSIVE_STATUSES and not self.analysis_notes:
            self.analysis_notes.append(
                f"SMT chưa kết luận: semantic_status={self.semantic_status}."
            )

    @property
    def decision(self) -> str:
        if self.lint_errors:
            return "fail"
        if self.semantic_status == "counterexample":
            return "fail"
        if self.semantic_status == "valid" and not self.analysis_notes:
            return "pass"
        return "inconclusive"

    @property
    def passed(self) -> bool:
        return self.decision == "pass"

    @property
    def errors(self) -> list[str]:
        errors = list(self.lint_errors)
        if self.semantic_status == "counterexample":
            try:
                from .node3_renderer import render_warning
            except ImportError:  # The policy commit intentionally precedes the renderer commit.
                rendered = [f"SMT phát hiện {warning.type}." for warning in self.semantic_warnings]
            else:
                rendered = [render_warning(warning) for warning in self.semantic_warnings]
            errors.extend(rendered or ["SMT tìm thấy phản ví dụ nhưng không trả cảnh báo có cấu trúc."])
        return errors

    @property
    def warnings(self) -> list[str]:
        return list(self.lint_warnings) + list(self.analysis_notes)

    @property
    def findings(self) -> list[str]:
        return self.errors + self.warnings


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def semantic_fingerprint(result: Node3Result) -> str:
    """Fingerprint a semantic failure, excluding timing and raw solver text.

    This is intended only for Counterexample/fail repetition detection. An
    inconclusive result uses ``next_inconclusive_state`` instead of StallTracker.
    """
    if result.semantic_status != "counterexample" or result.decision != "fail":
        raise ValueError("semantic_fingerprint is only defined for Counterexample failures")
    warnings = sorted(
        ({"type": warning.type, "fields": warning.fields} for warning in result.semantic_warnings),
        key=_canonical,
    )
    payload = {"contract": result.contract, "warnings": warnings}
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def next_inconclusive_state(current_count: int, decision: str) -> tuple[int, str]:
    """Advance the separate infrastructure-inconclusive counter.

    Two consecutive inconclusive results stop with ``logic_inconclusive``.
    Pass/fail resets this counter. It is deliberately distinct from the
    ``stalled`` stop reason and ``StallTracker`` used for repeated draft errors.
    """
    if current_count < 0:
        raise ValueError("current_count must be non-negative")
    if decision == "inconclusive":
        updated = current_count + 1
        return updated, "logic_inconclusive" if updated >= 2 else ""
    if decision not in {"pass", "fail"}:
        raise ValueError(f"unsupported decision: {decision}")
    return 0, ""
