"""Single user-facing entrypoint for the research assurance pipeline."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

from research.architecture.cli_runner import SessionOptions, run_session
from research.final_validation.marlowe_cli import config_from_environment
from research.integrations.model_transport import ModelTransport
from research.stage2b.intent_spec import CORE_SCHEMA_VERSION_V2, CORE_SCHEMA_VERSION_V3


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
    parser.add_argument("--model", help="Model tại endpoint trong .env.")
    parser.add_argument("--reference-binary", help="Binary Marlowe reference đã pin.")
    parser.add_argument("--expectation", type=Path,
                        help="JSON kịch bản hành vi độc lập do người dùng xác nhận.")
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
    parser.add_argument("--core-schema-version", choices=("v2", "v3"), default="v3")
    return parser


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
    interactive = args.interactive or not prompt
    try:
        if not prompt:
            prompt = input("Mô tả hợp đồng:\n> ").strip()
        while not prompt:
            prompt = input("Prompt đang rỗng, nhập lại:\n> ").strip()
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
                core_schema_version=(CORE_SCHEMA_VERSION_V3 if args.core_schema_version == "v3"
                                     else CORE_SCHEMA_VERSION_V2),
                property_dataset_path=(None if args.no_property_dataset
                                       else args.property_dataset),
            )
            model = ModelTransport(args.model)
        except (RuntimeError, ValueError, OSError, json.JSONDecodeError) as exc:
            print(f"Không thể khởi tạo pipeline: {' '.join(str(exc).split())}", file=sys.stderr)
            return 2
        try:
            payload = run_session(prompt, model, options=options,
                                  ask=input if interactive else None,
                                  emit=print if interactive or args.trace_only else None)
            exit_code = 0 if payload["status"] == "LEDGER_SIZE_CHECKED" else 2
        except KeyboardInterrupt:
            payload = {"status": "BLOCKED", "stop_reason": "interrupted",
                       "requirement_history": [{"version": 1, "messages": [prompt]}]}
            exit_code = 130
    if args.out:
        _write_json(Path(args.out), payload)
    if not args.no_run_log:
        try:
            log_dir = Path(args.run_log_dir)
            log_dir.mkdir(parents=True, exist_ok=True)
            name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".jsonl"
            record = {"record_type": "pipeline_run_v1",
                      "recorded_at_utc": datetime.now(timezone.utc).isoformat(), **payload}
            (log_dir / name).write_text(json.dumps(record, ensure_ascii=False) + "\n",
                                        encoding="utf-8")
        except OSError as exc:
            print(f"Cảnh báo: không ghi được run log: {exc}", file=sys.stderr)
    if args.trace_only:
        print(f"status: {payload['status']}; stop_reason: {payload['stop_reason']}")
        for question in payload.get("questions", []):
            print(f"Cần làm rõ: {question}")
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return exit_code
