"""Single user-facing entrypoint for the research assurance pipeline."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time

from research.orchestration.cli_runner import SessionOptions, run_session
from research.ledger.marlowe_cli import config_from_environment
from research.adapters.model_transport import ModelTransport
from research.formalization.intent_spec import (
    CORE_SCHEMA_VERSION_V2, CORE_SCHEMA_VERSION_V3, CORE_SCHEMA_VERSION_V4,
)


CORE_SCHEMA_VERSIONS = {"v2": CORE_SCHEMA_VERSION_V2, "v3": CORE_SCHEMA_VERSION_V3,
                        "v4": CORE_SCHEMA_VERSION_V4}


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("N phải >= 1")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="marlowe-ai-agent",
                                     description="Sinh và kiểm chứng Marlowe từ yêu cầu tự nhiên.")
    parser.add_argument("--prompt", help="Yêu cầu hợp đồng bằng ngôn ngữ tự nhiên.")
    parser.add_argument("--interactive", action="store_true",
                        help="Xác nhận intent và trả lời câu hỏi làm rõ.")
    parser.add_argument("--out", help="Ghi kết quả JSON vào file.")
    parser.add_argument("--provider", choices=("gemini", "default"), default="gemini",
                        help="gemini (mặc định): GEMINI_API_KEY/GEMINI_MODEL trong .env, "
                             "cấu hình như E7; default: endpoint LLM_* trong .env.")
    parser.add_argument("--model", help="Ghi đè tên model của provider đã chọn.")
    parser.add_argument("--json", action="store_true",
                        help="In toàn bộ kết quả JSON thay cho bản tóm tắt.")
    parser.add_argument("--reference-binary", help="Binary Marlowe reference đã pin.")
    parser.add_argument("--expectation", type=Path,
                        help="Biến thể chuyên gia: một kịch bản hành vi viết sẵn dạng JSON. "
                             "Mặc định CLI hỏi tình huống bằng lời và tự đổi thành kịch bản.")
    parser.add_argument("--run-log-dir", default="runs", metavar="PATH")
    parser.add_argument("--property-dataset", default="runs/property-dataset.sqlite3",
                        metavar="PATH", help="Kho evidence/property local (SQLite).")
    parser.add_argument("--no-property-dataset", action="store_true",
                        help="Khong ghi observation vao kho property.")
    parser.add_argument("--no-run-log", action="store_true")
    parser.add_argument("--trace-only", action="store_true")
    parser.add_argument("--max-iterations", type=positive_int, default=8, metavar="N")
    parser.add_argument("--max-llm-calls", type=positive_int, default=40, metavar="N")
    parser.add_argument("--stop-on-stall", type=positive_int, default=2, metavar="K")
    parser.add_argument("--core-schema-version", choices=("v2", "v3", "v4"), default="v4")
    return parser


def _is_valid_text(text: str) -> bool:
    """False when the text holds lone surrogates (bytes that were not valid UTF-8)."""
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _enable_line_editing() -> None:
    """Use GNU readline when it exists so Backspace erases a whole multi-byte character.

    Without it the Linux terminal may erase one byte of a Vietnamese letter (an input
    method retypes letters with Backspace), leaving invalid UTF-8 in the line."""
    try:
        import readline  # noqa: F401
    except ImportError:
        pass


def safe_input(prompt_text: str = "") -> str:
    """input() that asks again instead of passing a line with broken bytes on."""
    while True:
        line = input(prompt_text)
        if _is_valid_text(line):
            return line
        print("Dòng vừa nhập có ký tự bị hỏng (thường do bộ gõ tiếng Việt xoá dở một chữ). "
              "Hãy nhập lại hoặc dán câu đã soạn sẵn.", file=sys.stderr)


# Free-tier Gemini allows about 15 requests per minute (same pacing as the E7 runs).
GEMINI_MIN_INTERVAL_SECONDS = 5.0


def build_model(provider: str, model: str | None) -> ModelTransport:
    """The model transport the CLI uses; Gemini is set up as in the E7 pipeline arm."""
    if provider == "default":
        return ModelTransport(model)
    last: list[float] = []

    def pace(_phase: str) -> None:
        if last:
            wait = GEMINI_MIN_INTERVAL_SECONDS - (time.monotonic() - last[0])
            if wait > 0:
                time.sleep(wait)
        last[:] = [time.monotonic()]

    return ModelTransport(model, provider="gemini", before_request=pace, api_style="chat",
                          max_tokens=16000, disable_reasoning=True, retry_empty=False,
                          request_json_object=False)


STOP_REASONS = {
    "clarification_required": "cần bạn trả lời câu hỏi làm rõ (chạy lại với --interactive)",
    "explicit_acceptance_required": "cần bạn xác nhận diễn giải hợp đồng",
    "no_user_input": "bạn chưa trả lời câu hỏi",
    "reviewer_missing": "chưa có tên người xác nhận",
    "expectation_review_required": "kịch bản hành vi chưa được xác nhận",
    "interrupted": "phiên bị dừng giữa chừng (Ctrl+C)",
    "llm_error": "không gọi được model hoặc model trả lời lỗi",
    "extraction_failed": "chưa đọc được yêu cầu thành dữ kiện hợp đồng",
    "invalid_candidate": "diễn giải yêu cầu không hợp lệ",
    "stalled": "diễn giải yêu cầu lặp lại mà không tiến triển",
    "intent_not_acceptable": "diễn giải yêu cầu chưa đủ để sinh hợp đồng",
    "unsupported_intent": "yêu cầu có phần hệ thống chưa hỗ trợ",
    "unsupported_kept": "yêu cầu giữ lại phần hệ thống chưa hỗ trợ",
    "generation_stalled": "model sinh lại hợp đồng nhưng lặp lại đúng lỗi cũ",
    "max_generation_attempts": "đã hết số lần sinh lại hợp đồng",
    "max_iterations": "đã hết số lượt cho phép",
    "compile_not_supported": "chưa sinh được hợp đồng hợp lệ",
    "smt_unavailable_or_inconclusive": "kiểm tra SMT không chạy được hoặc không kết luận được",
    "reference_mismatch": "hợp đồng chạy khác kịch bản bạn đã xác nhận",
    "scenarios_not_confirmed": "các tình huống kiểm thử chưa được bạn xác nhận",
    "ledger_size_failed": "giao dịch vượt giới hạn kích thước trên testnet",
}
STEP_NAMES = {
    "intent_extraction": "đọc yêu cầu", "intent_acceptance": "xác nhận diễn giải",
    "compile": "sinh hợp đồng Marlowe", "smt_verification": "kiểm tra SMT",
    "semantic_comparison": "chạy thử trên bản tham chiếu", "exploration": "thử các cách chạy",
    "oracle_evaluation": "kiểm tra cảnh báo", "ledger_validation": "đo kích thước trên testnet",
}


def describe_result(payload: dict, *, log_path: Path | None = None,
                    contract_path: Path | None = None) -> str:
    """The end of a session in plain Vietnamese; the full record stays in the run log."""
    status = payload.get("status")
    reason = payload.get("stop_reason")
    lines = ["", "=== Kết quả ==="]
    if status == "LEDGER_SIZE_CHECKED":
        lines.append("Đã sinh hợp đồng Marlowe; nó qua các bước kiểm tra và đã đo kích thước "
                     "giao dịch trên testnet riêng.")
    elif status == "CANDIDATE_ONLY":
        lines.append("Đã sinh hợp đồng Marlowe; nó qua kiểm tra cấu trúc và SMT.")
        if payload.get("blocking_step") == "semantic_comparison":
            lines.append("Chưa chạy thử được vì chưa có tình huống kiểm thử nào (bạn đã bỏ qua "
                         "bước mô tả tình huống), nên các bước sau, kể cả đo kích thước trên "
                         "testnet, chưa chạy.")
        elif payload.get("blocking_step"):
            step = payload["blocking_step"]
            lines.append(f"Các bước từ '{STEP_NAMES.get(step, step)}' trở đi chưa chạy.")
    elif status == "UNSUPPORTED":
        lines.append("Dừng: " + STOP_REASONS.get(reason, str(reason)) + ".")
    elif status == "WAITING_USER":
        lines.append("Đang chờ bạn: " + STOP_REASONS.get(reason, str(reason)) + ".")
    else:
        lines.append("Chưa sinh được hợp đồng: " + STOP_REASONS.get(reason, str(reason)) + ".")
    check = payload.get("scenario_check") or {}
    if check.get("total"):
        if check.get("passed") == check["total"]:
            lines.append(f"Hợp đồng chạy đúng cả {check['total']} tình huống bạn đã xác nhận.")
        else:
            lines.append(f"Tình huống {check.get('current')}/{check['total']} không qua "
                         f"(đã qua {check.get('passed', 0)}).")
    step = payload.get("blocking_step")
    if status not in {"LEDGER_SIZE_CHECKED", "CANDIDATE_ONLY"} and step:
        lines.append(f"Dừng ở bước: {STEP_NAMES.get(step, step)}.")
        details = payload.get("blocking_diagnostics") or []
        if details:
            lines.append("Chi tiết kỹ thuật:")
            lines.extend(f"  - {item}" for item in details[:5])
            if len(details) > 5:
                lines.append(f"  … và {len(details) - 5} dòng nữa (xem run log)")
    for question in payload.get("questions") or []:
        lines.append(f"Câu hỏi còn chờ: {question}")
    if contract_path is not None:
        lines.append(f"Hợp đồng (Marlowe Core JSON): {contract_path}")
    if status in {"LEDGER_SIZE_CHECKED", "CANDIDATE_ONLY"}:
        lines.append("Đây vẫn chỉ là hợp đồng ứng viên: chưa được triển khai, chưa ký hay gửi "
                     "giao dịch nào.")
    usage = payload.get("model_usage") or {}
    if usage.get("api_calls"):
        lines.append(f"Số lần gọi model: {usage['api_calls']}.")
    if log_path is not None:
        lines.append(f"Toàn bộ chi tiết: {log_path}")
    return "\n".join(lines)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def main() -> int:
    if os.name == "nt":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args()
    prompt = args.prompt
    if prompt and not _is_valid_text(prompt):
        print("--prompt có ký tự không phải UTF-8 hợp lệ; hãy kiểm tra bảng mã của terminal.",
              file=sys.stderr)
        return 2
    interactive = args.interactive or not prompt
    if interactive:
        _enable_line_editing()
    try:
        if not prompt:
            prompt = safe_input("Mô tả hợp đồng:\n> ").strip()
        while not prompt:
            prompt = safe_input("Prompt đang rỗng, nhập lại:\n> ").strip()
    except KeyboardInterrupt:
        prompt = prompt or ""
        payload = {"status": "BLOCKED", "stop_reason": "interrupted",
                   "requirement_history": [{"version": 1, "messages": [prompt]}]}
        exit_code = 130
    else:
        try:
            expectation = (json.loads(args.expectation.read_text(encoding="utf-8"))
                           if args.expectation else None)
            options = SessionOptions(
                interactive=interactive,
                max_iterations=args.max_iterations,
                max_llm_calls=args.max_llm_calls,
                stop_on_stall=args.stop_on_stall,
                reference_binary=args.reference_binary or os.getenv("MARLOWE_REFERENCE_BINARY"),
                ledger_config=config_from_environment(),
                expectation=expectation,
                smt_binary=os.getenv("MARLOWE_SMT_BIN"),
                core_schema_version=CORE_SCHEMA_VERSIONS[args.core_schema_version],
                property_dataset_path=(None if args.no_property_dataset
                                       else args.property_dataset),
            )
            model = build_model(args.provider, args.model)
        except (RuntimeError, ValueError, OSError, json.JSONDecodeError) as exc:
            print(f"Không thể khởi tạo pipeline: {' '.join(str(exc).split())}", file=sys.stderr)
            return 2
        try:
            payload = run_session(prompt, model, options=options,
                                  ask=safe_input if interactive else None,
                                  emit=print if interactive or args.trace_only else None)
            exit_code = 0 if payload["status"] == "LEDGER_SIZE_CHECKED" else 2
        except KeyboardInterrupt:
            payload = {"status": "BLOCKED", "stop_reason": "interrupted",
                       "requirement_history": [{"version": 1, "messages": [prompt]}]}
            exit_code = 130
    if args.out:
        _write_json(Path(args.out), payload)
    log_path = contract_path = None
    if not args.no_run_log:
        try:
            log_dir = Path(args.run_log_dir)
            log_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            record = {"record_type": "Orchestration-PipelineRun-v1",
                      "recorded_at_utc": datetime.now(timezone.utc).isoformat(), **payload}
            log_path = log_dir / f"{stamp}.jsonl"
            log_path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
            contract = ((payload.get("contract_candidate") or {}).get("payload") or {}).get(
                "contract")
            if contract is not None:
                contract_path = log_dir / f"{stamp}-contract.json"
                _write_json(contract_path, contract)
        except OSError as exc:
            print(f"Cảnh báo: không ghi được run log: {exc}", file=sys.stderr)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif args.trace_only:
        print(f"status: {payload['status']}; stop_reason: {payload['stop_reason']}")
        for question in payload.get("questions", []):
            print(f"Cần làm rõ: {question}")
    else:
        print(describe_result(payload, log_path=log_path, contract_path=contract_path))
    return exit_code
