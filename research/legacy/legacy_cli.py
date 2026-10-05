import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .models import (
    ContractDraft,
    LogicGraphResult,
    PipelineResult,
    TraceEvent,
    VerificationResult,
)
from .nodes import AgentPipeline
from .openai_reasoner import OpenAIReasoner


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("N phải >= 1")
    return parsed


def node_display_name(node: str) -> str:
    labels = {
        "node_1_prompt_to_draft": "Node 1 - Draft",
        "node_2_semantic_verification": "Node 2 - Semantic",
        "node_3_logic_graph_verification": "Node 3 - Verification",
    }
    return labels.get(node, "")


def interrupted_result(prompt: str, trace: list[TraceEvent] | None = None) -> PipelineResult:
    return PipelineResult(ContractDraft(prompt, "", [], None),
                          VerificationResult(False, 0.0, []),
                          LogicGraphResult(False, [], {"nodes": [], "edges": []}),
                          0, trace or [], "blocked", "interrupted")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="marlowe-ai-agent",
        description="AI agent CLI sinh va kiem chung smart contract Marlowe tu prompt tu nhien.",
    )
    parser.add_argument("--prompt", help="Mo ta hop dong bang ngon ngu tu nhien.")
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Hoi dap bo sung thong tin neu prompt bi thieu. Tu bat neu ban khong truyen --prompt.",
    )
    parser.add_argument("--out", help="Duong dan file JSON de luu ket qua.")
    parser.add_argument("--research-mode", choices=["pipeline", "legacy", "shadow", "candidate", "authorized"],
                        default="pipeline", help="Pipeline mới là mặc định; legacy chỉ để chẩn đoán.")
    parser.add_argument("--research-live", action="store_true",
                        help="Allow a live model call in the opt-in research route.")
    parser.add_argument("--reference-binary", default=None,
                        help="Binary Marlowe reference đã pin để kiểm hành vi.")
    parser.add_argument("--expectation", type=Path,
                        help="JSON kịch bản hành vi do người dùng chuẩn bị và xác nhận.")
    parser.add_argument("--run-log-dir", default="runs", metavar="PATH",
                        help="Thư mục lưu summary từng lượt dưới dạng JSONL (mặc định runs).")
    parser.add_argument("--no-run-log", action="store_true", help="Tắt ghi JSONL run log.")
    parser.add_argument(
        "--provider",
        choices=["openai"],
        default="openai",
        help="OpenAI-compatible LLM transport; khong co offline heuristic.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Ten model tai endpoint da cau hinh trong .env.",
    )
    parser.add_argument(
        "--trace",
        action="store_true",
        help="Tuong thich nguoc: tracking node dang chay nay da bat mac dinh.",
    )
    parser.add_argument(
        "--trace-only",
        action="store_true",
        help="Chi in tracking va tom tat, khong in JSON day du.",
    )
    parser.add_argument(
        "--narrative-trace",
        action="store_true",
        help="Tuong thich nguoc: audit dien giai da bat mac dinh.",
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Tuong thich nguoc: audit dien giai da bat mac dinh.",
    )
    parser.add_argument("--max-iterations", "--max-clarifications", dest="max_iterations",
                        type=positive_int, default=None, metavar="N",
                        help="Giới hạn số lượt trích xuất (pipeline mặc định 8). --max-clarifications đã cũ.")
    parser.add_argument("--max-llm-calls", type=positive_int, default=None, metavar="N",
                        help="Giới hạn số lời gọi LLM, kể cả retry và repair (pipeline mặc định 40).")
    parser.add_argument("--stop-on-stall", type=positive_int, default=None, metavar="K",
                        help="Dừng khi candidate lặp K lần (pipeline mặc định 2).")
    parser.add_argument(
        "--allow-unverified",
        action="store_true",
        help="Cho phep chay Node 3 verification du semantic verification chua pass. Chi nen dung de debug.",
    )
    return parser


def main() -> int:
    if os.name == "nt":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
    parser = build_parser()
    args = parser.parse_args()

    prompt = args.prompt
    interactive = args.interactive
    initial_interrupt = False

    try:
        if not prompt:
            interactive = True
            print("Marlowe AI Agent")
            print("Nhap prompt hop dong cua ban:")
            prompt = input("> ").strip()
        while not prompt:
            prompt = input("Prompt dang rong, nhap lai:\n> ").strip()
    except KeyboardInterrupt:
        initial_interrupt = True
        prompt = prompt or ""

    if args.research_mode in {"candidate", "authorized"}:
        return _run_research_route(prompt, args)
    if args.research_mode == "pipeline":
        return _run_pipeline_route(prompt, args, initial_interrupt, interactive)

    log_handle = None
    log_failed = False

    def print_trace(event: TraceEvent) -> None:
        nonlocal log_handle, log_failed
        node_label = node_display_name(event.node)

        if event.status == "start" and node_label:
            print(f"Đang chạy: {node_label}")
        elif event.status in {"blocked", "skipped", "error"} and node_label:
            print(f"{node_label}: {event.message}")

        narrative = event.data.get("reasoning_narrative") if event.data else None
        if narrative:
            print(f"\nAudit {node_label or event.node}: {narrative}")

        if event.node == "pipeline" and event.status == "iteration":
            data = event.data
            print(f"Lượt {data['iteration']} | structural={data['structural'].upper()} | "
                  f"semantic={data['semantic'].upper()} | logic={data['logic'].upper()} "
                  f"({data['logic_errors']}E/{data['logic_warnings']}W) | "
                  f"llm_calls={data['llm_calls']} | {data['elapsed_seconds']}s")
            if not args.no_run_log and not log_failed:
                try:
                    if log_handle is None:
                        log_dir = Path(args.run_log_dir)
                        log_dir.mkdir(parents=True, exist_ok=True)
                        name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".jsonl"
                        log_handle = (log_dir / name).open("w", encoding="utf-8")
                    log_handle.write(json.dumps(data, ensure_ascii=False) + "\n")
                    log_handle.flush()
                except OSError as exc:
                    log_failed = True
                    print(f"Cảnh báo: không ghi được run log: {exc}", file=sys.stderr)
                    if log_handle is not None:
                        log_handle.close()
                        log_handle = None

    if initial_interrupt:
        result = interrupted_result(prompt)
    else:
        try:
            reasoner = OpenAIReasoner(model=args.model)
        except RuntimeError as exc:
            print(f"Lỗi khởi tạo LLM: {' '.join(str(exc).split())}", file=sys.stderr)
            return 2
        except KeyboardInterrupt:
            result = interrupted_result(prompt)
        else:
            pipeline = AgentPipeline(
                reasoner=reasoner,
                interactive=interactive,
                max_iterations=args.max_iterations,
                max_llm_calls=args.max_llm_calls,
                stop_on_stall=args.stop_on_stall,
                require_semantic_pass=not args.allow_unverified,
                trace_callback=print_trace,
            )
            try:
                result = pipeline.run(prompt)
            except KeyboardInterrupt:
                result = interrupted_result(prompt, pipeline.trace)
            finally:
                if log_handle is not None:
                    log_handle.close()
    payload = result.to_dict()
    if args.research_mode == "shadow" and not initial_interrupt:
        payload["research_sidecar"] = _research_snapshot(prompt, args)

    if args.out:
        out_path = Path(args.out)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\nSaved: {out_path.resolve()}")

    if args.trace_only:
        print("\nSummary")
        print(f"- semantic_passed: {result.semantic_verification.passed}")
        print(f"- logic_passed: {result.logic_verification.passed}")
        print(f"- intent: {result.draft.intent}")
        contract = result.draft.marlowe_contract
        print(f"- contract_root: {next(iter(contract), None) if isinstance(contract, dict) else contract}")
        print(f"- status: {result.status}")
        print(f"- stop_reason: {stop_reason_label(result.stop_reason)}")
        return 130 if result.stop_reason == "interrupted" else (0 if result.status == "done" else 2)

    text = json.dumps(payload, ensure_ascii=False, indent=2)
    print(text)

    print(f"\nSummary: {result.status}; {stop_reason_label(result.stop_reason)}")
    return 130 if result.stop_reason == "interrupted" else (0 if result.status == "done" else 2)


def stop_reason_label(reason: str) -> str:
    labels = {
        "ok": "Đã kiểm tra xong",
        "max_iterations": "Đã hết số lượt sinh draft",
        "stalled": "Bản draft không tiến triển",
        "no_user_input": "Cần thêm thông tin từ người dùng",
        "llm_error": "Lời gọi LLM thất bại hoặc vượt giới hạn",
        "semantic_not_passed": "Semantic chưa đạt",
        "logic_not_passed": "Logic graph chưa đạt",
        "logic_inconclusive": "Node 3/SMT chưa thể kết luận",
        "interrupted": "Đã dừng bằng Ctrl+C",
    }
    return labels.get(reason, reason)


def _research_snapshot(prompt: str, args: argparse.Namespace) -> dict:
    root = Path(__file__).resolve().parents[2]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from research.architecture.bootstrap import build_research_pipeline

    try:
        pipeline = build_research_pipeline(live_model=args.research_live, model_name=args.model)
        run = pipeline.run([{"version": 1, "messages": [prompt]}], stop_after="compiler_authority")
    except RuntimeError as exc:
        return {"status": "UNAVAILABLE", "diagnostics": [f"research model unavailable: {exc}"]}
    snapshot = run.to_dict()
    visible_types = {"intent-candidate", "intent-review", "accepted-intent-manifest",
                     "compile-result", "contract-candidate", "reference-comparison",
                     "compiler-authority-decision"}
    snapshot["artifacts"] = {
        artifact_id: artifact.to_dict()
        for stage in run.stages.values()
        for artifact_id in stage.output_artifacts
        if (artifact := pipeline.store.get(artifact_id)).artifact_type in visible_types
    }
    return snapshot


def _run_research_route(prompt: str, args: argparse.Namespace) -> int:
    if args.research_mode == "authorized":
        print(json.dumps({"status": "BLOCKED", "reason": "profile authority is not promoted"},
                         ensure_ascii=False))
        return 2
    result = _research_snapshot(prompt, args)
    if args.out:
        Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                                  encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    stages = result.get("stages", {})
    return 0 if stages.get("compile", {}).get("run_status") == "SUCCEEDED" else 2


def _run_pipeline_route(prompt: str, args: argparse.Namespace,
                        initial_interrupt: bool = False, interactive: bool = False) -> int:
    root = Path(__file__).resolve().parents[2]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from research.architecture.cli_runner import SessionOptions, run_session
    from research.final_validation.marlowe_cli import config_from_environment
    from research.integrations.model_transport import ModelTransport

    if initial_interrupt:
        payload = {"status": "BLOCKED", "stop_reason": "interrupted",
                   "requirement_history": [{"version": 1, "messages": [prompt]}]}
        exit_code = 130
    else:
        if args.allow_unverified:
            print("--allow-unverified chỉ dùng với --research-mode legacy.", file=sys.stderr)
            return 2
        try:
            expectation = (json.loads(args.expectation.read_text(encoding="utf-8"))
                           if args.expectation else None)
            reference_binary = args.reference_binary or os.getenv("MARLOWE_REFERENCE_BINARY")
            ledger_config = config_from_environment()
            model = ModelTransport(args.model)
            options = SessionOptions(
                interactive=interactive,
                max_iterations=args.max_iterations or 8,
                max_llm_calls=args.max_llm_calls or 40,
                stop_on_stall=args.stop_on_stall or 2,
                reference_binary=reference_binary,
                ledger_config=ledger_config,
                expectation=expectation,
                smt_binary=os.getenv("MARLOWE_SMT_BIN"))
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
        Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                                  encoding="utf-8")
    if not args.no_run_log:
        try:
            log_dir = Path(args.run_log_dir)
            log_dir.mkdir(parents=True, exist_ok=True)
            name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".jsonl"
            record = {"record_type": "pipeline_run_v1",
                      "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
                      **payload}
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
