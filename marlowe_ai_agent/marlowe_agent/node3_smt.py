"""Production subprocess boundary for the standalone Marlowe SMT driver."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from threading import BoundedSemaphore
from time import perf_counter
from typing import Any

from .node3_policy import StructuredWarning


WRAPPER = Path(__file__).resolve().parents[2] / "tools" / "marlowe_smt" / "run_smt.py"
_SMT_SLOTS = BoundedSemaphore(2)
_STATUSES = {"valid", "counterexample", "indeterminate", "timeout", "invalid_input"}


@dataclass
class SMTAnalysis:
    status: str
    warnings: list[StructuredWarning]
    counterexample: dict[str, Any] | None
    analysis_notes: list[str]
    elapsed_seconds: float | None


class MarloweSMTBackend:
    def __init__(self, solver_timeout_ms: int = 60_000, hard_timeout: float = 90.0) -> None:
        self.solver_timeout_ms = solver_timeout_ms
        self.hard_timeout = hard_timeout

    def analyze(self, contract: Any) -> SMTAnalysis:
        if not WRAPPER.is_file():
            return SMTAnalysis("unavailable", [], None, ["SMT wrapper không tồn tại."], None)
        command = [sys.executable, str(WRAPPER), "--hard-timeout", str(self.hard_timeout),
                   "--solver-timeout-ms", str(self.solver_timeout_ms)]
        with _SMT_SLOTS:
            started = perf_counter()
            try:
                process = subprocess.run(
                    command, input=json.dumps(contract, ensure_ascii=False, separators=(",", ":")),
                    text=True, capture_output=True, check=False,
                    timeout=self.hard_timeout + 5, cwd=WRAPPER.parents[2],
                )
            except subprocess.TimeoutExpired:
                return SMTAnalysis("timeout", [], None, ["SMT subprocess vượt thời hạn ngoài."],
                                   perf_counter() - started)
            except OSError:
                return SMTAnalysis("unavailable", [], None, ["Không khởi chạy được SMT wrapper."],
                                   perf_counter() - started)
            elapsed = perf_counter() - started

        if not process.stdout.strip():
            return SMTAnalysis("unavailable", [], None, ["SMT wrapper không trả JSON."], elapsed)
        try:
            output = json.loads(process.stdout)
        except json.JSONDecodeError:
            return SMTAnalysis("unavailable", [], None, ["SMT wrapper trả JSON không hợp lệ."], elapsed)
        if not isinstance(output, dict):
            return SMTAnalysis("unavailable", [], None, ["SMT wrapper không trả JSON object."], elapsed)

        raw_status = output.get("status")
        status = {
            "InvalidInput": "invalid_input",
        }.get(raw_status, raw_status.lower() if isinstance(raw_status, str) else "")
        if status not in _STATUSES:
            return SMTAnalysis("unavailable", [], None, ["SMT wrapper trả status không hỗ trợ."], elapsed)
        raw_warnings = output.get("warnings")
        if not isinstance(raw_warnings, list) or any(
            not isinstance(item, dict) or not isinstance(item.get("type"), str)
            or not item["type"] for item in raw_warnings
        ):
            return SMTAnalysis("unavailable", [], None, ["SMT wrapper trả warnings sai schema."], elapsed)
        counterexample = output.get("counterexample")
        if counterexample is not None and not isinstance(counterexample, dict):
            return SMTAnalysis("unavailable", [], None, ["SMT wrapper trả counterexample sai schema."], elapsed)
        notes = output.get("analysis_notes")
        if not isinstance(notes, list) or any(not isinstance(note, str) for note in notes):
            return SMTAnalysis("unavailable", [], None, ["SMT wrapper trả analysis_notes sai schema."], elapsed)
        if process.returncode != 0 and status not in {"timeout", "invalid_input"}:
            return SMTAnalysis("unavailable", [], None, ["SMT wrapper kết thúc với mã lỗi bất thường."], elapsed)
        if process.stderr:
            notes = [*notes, "SMT wrapper wrote stderr; raw stderr omitted."]
        warnings = [StructuredWarning(item["type"],
                                      {key: value for key, value in item.items() if key != "type"})
                    for item in raw_warnings]
        return SMTAnalysis(status, warnings, counterexample, notes, elapsed)
