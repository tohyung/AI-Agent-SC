import argparse
import json
import sys
from pathlib import Path

from .models import TraceEvent
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
        "node_3_logic_graph_verification": "Node 3 - Logic graph",
    }
    return labels.get(node, "")


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
    parser.add_argument(
        "--provider",
        choices=["openai"],
        default="openai",
        help="Engine suy luan LLM. Chuong trinh khong con dung che do offline/heuristic.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Ten model OpenAI, vi du gpt-4.1-mini hoac model ban dang co quyen dung.",
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
                        help="Giới hạn số lượt sinh draft (mặc định không giới hạn). --max-clarifications đã cũ.")
    parser.add_argument("--max-llm-calls", type=positive_int, default=None, metavar="N",
                        help="Giới hạn số lời gọi LLM, kể cả retry và repair (mặc định không giới hạn).")
    parser.add_argument("--stop-on-stall", type=positive_int, default=None, metavar="K",
                        help="Dừng khi cùng AST và lỗi xuất hiện K lần (mặc định chỉ cảnh báo).")
    parser.add_argument(
        "--allow-unverified",
        action="store_true",
        help="Cho phep chay logic graph du semantic verification chua pass. Chi nen dung de debug.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    prompt = args.prompt
    interactive = args.interactive

    if not prompt:
        interactive = True
        print("Marlowe AI Agent")
        print("Nhap prompt hop dong cua ban:")
        prompt = input("> ").strip()

    while not prompt:
        prompt = input("Prompt dang rong, nhap lai:\n> ").strip()

    def print_trace(event: TraceEvent) -> None:
        node_label = node_display_name(event.node)

        if event.status == "start" and node_label:
            print(f"Đang chạy: {node_label}")
        elif event.status in {"blocked", "skipped", "error"} and node_label:
            print(f"{node_label}: {event.message}")

        narrative = event.data.get("reasoning_narrative") if event.data else None
        if narrative:
            print(f"\nAudit {node_label or event.node}: {narrative}")

    try:
        reasoner = OpenAIReasoner(model=args.model)
    except RuntimeError as exc:
        print(f"Lỗi khởi tạo LLM: {' '.join(str(exc).split())}", file=sys.stderr)
        return 2
    pipeline = AgentPipeline(
        reasoner=reasoner,
        interactive=interactive,
        max_iterations=args.max_iterations,
        max_llm_calls=args.max_llm_calls,
        stop_on_stall=args.stop_on_stall,
        require_semantic_pass=not args.allow_unverified,
        trace_callback=print_trace,
    )
    result = pipeline.run(prompt)
    payload = result.to_dict()

    if args.trace_only:
        print("\nSummary")
        print(f"- semantic_passed: {result.semantic_verification.passed}")
        print(f"- logic_passed: {result.logic_verification.passed}")
        print(f"- intent: {result.draft.intent}")
        contract = result.draft.marlowe_contract
        print(f"- contract_root: {next(iter(contract), None) if isinstance(contract, dict) else contract}")
        print(f"- status: {result.status}")
        print(f"- stop_reason: {stop_reason_label(result.stop_reason)}")
        return 0 if result.status == "done" else 2

    text = json.dumps(payload, ensure_ascii=False, indent=2)
    print(text)

    if args.out:
        out_path = Path(args.out)
        out_path.write_text(text + "\n", encoding="utf-8")
        print(f"\nSaved: {out_path.resolve()}")
    print(f"\nSummary: {result.status}; {stop_reason_label(result.stop_reason)}")
    return 0 if result.status == "done" else 2


def stop_reason_label(reason: str) -> str:
    labels = {
        "ok": "Đã kiểm tra xong",
        "max_iterations": "Đã hết số lượt sinh draft",
        "stalled": "Bản draft không tiến triển",
        "no_user_input": "Cần thêm thông tin từ người dùng",
        "llm_error": "Lời gọi LLM thất bại hoặc vượt giới hạn",
        "semantic_not_passed": "Semantic chưa đạt",
        "logic_not_passed": "Logic graph chưa đạt",
    }
    return labels.get(reason, reason)
