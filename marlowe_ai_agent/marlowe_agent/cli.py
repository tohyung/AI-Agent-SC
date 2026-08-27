import argparse
import json
from pathlib import Path

from .models import TraceEvent
from .nodes import AgentPipeline
from .openai_reasoner import OpenAIReasoner


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
    parser.add_argument(
        "--max-clarifications",
        type=int,
        default=None,
        metavar="N",
        help="Gioi han so vong hoi bo sung. Mac dinh khong gioi han.",
    )
    parser.add_argument(
        "--allow-unverified",
        action="store_true",
        help="Cho phep chay logic graph du semantic verification chua pass. Chi nen dung de debug.",
    )
    return parser


def main() -> None:
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
        elif event.status in {"blocked", "skipped"} and node_label:
            print(f"{node_label}: {event.message}")

        narrative = event.data.get("reasoning_narrative") if event.data else None
        if narrative:
            print(f"\nAudit {node_label or event.node}: {narrative}")

    reasoner = OpenAIReasoner(model=args.model)
    pipeline = AgentPipeline(
        reasoner=reasoner,
        interactive=interactive,
        max_iterations=args.max_clarifications,
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
        print(f"- contract_root: {next(iter(result.draft.marlowe_contract.keys()), None) if result.draft.marlowe_contract else None}")
        return

    text = json.dumps(payload, ensure_ascii=False, indent=2)
    print(text)

    if args.out:
        out_path = Path(args.out)
        out_path.write_text(text + "\n", encoding="utf-8")
        print(f"\nSaved: {out_path.resolve()}")
