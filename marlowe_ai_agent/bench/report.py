from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .runner import read_runs
from .stats import percentile, spearman, wilson


def _mean(values: list[float]) -> float | None:
    return statistics.mean(values) if values else None


def _distribution(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        values = row.get(key, [])
        for value in values if isinstance(values, list) else [values]:
            groups[str(value)].append(row)
    return {label: {"n": len(items), "converged": sum(item.get("converged", False) for item in items),
                    "strict_correct": sum(bool(item.get("converged")) and bool((item.get("evaluation") or {}).get("strict_correct"))
                                          for item in items), "small_sample": len(items) < 10}
            for label, items in sorted(groups.items())}


def generate(directory: Path) -> dict[str, Any]:
    rows = read_runs(directory / "runs.jsonl")
    ordinary = [row for row in rows if row.get("type") != "infeasible" and row.get("attempt", 1) == 1]
    infeasible = [row for row in rows if row.get("type") == "infeasible" and row.get("attempt", 1) == 1]
    n = len(ordinary)
    counts = {
        "converged": sum(row.get("converged", False) for row in ordinary),
        "correct_90": sum(row.get("converged", False) and (row.get("evaluation") or {}).get("overall_accuracy", 0) >= 0.9
                          for row in ordinary),
        "strict_correct": sum(row.get("converged", False) and bool((row.get("evaluation") or {}).get("strict_correct"))
                              for row in ordinary),
        "false_convergence": sum(bool((row.get("evaluation") or {}).get("false_convergence")) for row in ordinary),
    }
    accuracy = [(row.get("evaluation") or {}).get("overall_accuracy") for row in ordinary]
    accuracy = [score for score in accuracy if score is not None]
    iterations = [row["iterations"] for row in ordinary if row.get("converged")]
    wall = [row["wall_seconds"] for row in ordinary if row.get("wall_seconds") is not None]
    costs = [row["cost_usd"] for row in rows if row.get("cost_usd") is not None]
    llm_latencies = [call["latency_seconds"] for row in rows for call in row.get("call_log", [])]
    paired = [(row["judge"]["score"], row["evaluation"]["overall_accuracy"] * 100)
              for row in ordinary if row.get("judge") and "score" in row["judge"]
              and row.get("evaluation") and row["evaluation"].get("overall_accuracy") is not None]
    summary = {
        "metadata": {key: rows[0].get(key) for key in ("model", "provider", "git_commit", "dataset_sha256", "workers", "limits", "started_at")}
        if rows else {},
        "n": n, "infeasible_n": len(infeasible), "counts": counts,
        "rates": {name: {"rate": count / n if n else None, "wilson_95": wilson(count, n)}
                  for name, count in counts.items()},
        "infeasible_correct": sum(row.get("status") != "done" for row in infeasible),
        "accuracy_mean": _mean(accuracy), "accuracy_median": statistics.median(accuracy) if accuracy else None,
        "iterations_median": statistics.median(iterations) if iterations else None,
        "iterations_p90": percentile(iterations, 90), "iterations_max": max(iterations, default=None),
        "cdf": {str(k): sum(row.get("converged", False) and row.get("iterations", 10**9) <= k
                            for row in ordinary) / n if n else None for k in (1, 2, 3, 5, 10, 20, 30)},
        "wall_mean": _mean(wall), "wall_p90": percentile(wall, 90),
        "llm_latency_p50": percentile(llm_latencies, 50), "llm_latency_p95": percentile(llm_latencies, 95),
        "total_cost_usd": sum(costs) if len(costs) == len(rows) else None,
        "cost_known_runs": len(costs), "cost_per_strict_contract": (sum(costs) / counts["strict_correct"]
                                  if len(costs) == len(rows) and counts["strict_correct"] else None),
        "stop_reasons": dict(Counter(row.get("stop_reason", "unknown") for row in ordinary if not row.get("converged"))),
        "strata": {key: _distribution(ordinary, key) for key in ("difficulty", "type", "language", "info_mode", "challenges")},
        "judge_evaluator_spearman": spearman([item[0] for item in paired], [item[1] for item in paired]) if paired else None,
        "self_judging_bias": bool(rows and rows[0].get("judge_model") in (None, rows[0].get("model"))),
    }
    primary = {row["case_id"]: row for row in rows if row.get("attempt", 1) == 1}
    repeats = [row for row in rows if row.get("attempt") == 2 and row["case_id"] in primary]
    extensions = [row for row in rows if row.get("attempt") == 3 and row["case_id"] in primary]
    summary["repeat_subset"] = {"n": len(repeats), "same_status": sum(
        row.get("status") == primary[row["case_id"]].get("status") for row in repeats)}
    summary["extend_nonconverged"] = {"n": len(extensions), "late_converged": sum(
        row.get("converged", False) for row in extensions)}
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with (directory / "runs.csv").open("w", encoding="utf-8", newline="") as handle:
        fields = ["case_id", "attempt", "type", "difficulty", "language", "info_mode", "status", "stop_reason",
                  "iterations", "wall_seconds", "agent_seconds", "llm_calls", "prompt_tokens", "completion_tokens",
                  "cost_usd", "cost_source", "overall_accuracy", "strict_correct", "false_convergence"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            evaluation = row.get("evaluation") or {}
            writer.writerow({key: evaluation.get(key) if key in evaluation else row.get(key) for key in fields})
    ordered = sorted(ordinary, key=lambda row: (row.get("evaluation") or {}).get("overall_accuracy") or -1)
    lines = ["# Bảng case", "", "| Case | Trạng thái | Vòng | Điểm | Đường hội tụ |", "|---|---|---:|---:|---|"]
    for row in ordered:
        score = (row.get("evaluation") or {}).get("overall_accuracy")
        lines.append(f"| {row['case_id']} | {row.get('stop_reason')} | {row.get('iterations')} | {score} | {row.get('convergence_path', '')} |")
    (directory / "cases_table.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    rng = random.Random(1234)
    disagreement = sorted((row for row in ordinary if row.get("judge") and "score" in row["judge"]
                           and (row.get("evaluation") or {}).get("overall_accuracy") is not None),
                          key=lambda row: abs(row["judge"]["score"] - row["evaluation"]["overall_accuracy"] * 100),
                          reverse=True)[:5]
    false = [row for row in ordinary if (row.get("evaluation") or {}).get("false_convergence")][:5]
    random_sample = rng.sample(ordinary, min(5, len(ordinary)))
    review = ["# Hàng đợi duyệt tay", ""]
    for row in disagreement + false + random_sample:
        review.extend([f"## {row['case_id']}", row.get("prompt", ""), "",
                       f"Điểm: {(row.get('evaluation') or {}).get('overall_accuracy')}; đường hội tụ: {row.get('convergence_path')}",
                       "", "Hội thoại:", ""])
        review.extend(f"- {qa['question']} / {qa['answer']}" for qa in row.get("qa_transcript", []))
        review.extend(["", "Mô tả:", "", row.get("contract_description") or "(không có)", "",
                       "Nhận xét người duyệt: ______", ""])
    (directory / "review_queue.md").write_text("\n".join(review), encoding="utf-8")
    md = ["# Benchmark Marlowe AI Agent", "", f"Dataset SHA-256: `{summary['metadata'].get('dataset_sha256')}`",
          f"Số case khả thi: {n}; không khả thi: {len(infeasible)}.", ""]
    if summary["self_judging_bias"]:
        md.extend(["**Cảnh báo: self-judging bias; judge không độc lập model với agent.**", ""])
    for name, item in summary["rates"].items():
        md.append(f"- {name}: {counts[name]}/{n}; Wilson 95%: {item['wilson_95']}")
    md.extend(["", f"Độ chính xác trung bình: {summary['accuracy_mean']}; trung vị: {summary['accuracy_median']}.",
               f"Vòng hội tụ trung vị/p90: {summary['iterations_median']}/{summary['iterations_p90']}.",
               f"Thời gian trung bình/p90: {summary['wall_mean']}/{summary['wall_p90']} giây.",
               f"Tổng chi phí: {summary['total_cost_usd']} USD; số run có giá: {len(costs)}/{len(rows)}.",
               "", "## Phân tầng", ""])
    for key, groups in summary["strata"].items():
        md.append(f"### {key}")
        for label, item in groups.items():
            note = " (mẫu nhỏ, chỉ mang tính gợi ý)" if item["small_sample"] else ""
            md.append(f"- {label}: n={item['n']}, hội tụ={item['converged']}, đúng tuyệt đối={item['strict_correct']}{note}")
    md.extend(["", "## CDF hội tụ", ""])
    md.extend(f"- ≤{k} vòng: {v}" for k, v in summary["cdf"].items())
    md.extend(["", f"Lặp lại phân tầng: {summary['repeat_subset']}",
               f"Hội tụ muộn: {summary['extend_nonconverged']}"])
    md.extend(["", "## Threats to validity", "",
               "- Prompt được sinh theo template nên thiên lệch phong cách; metadata độ khó không đảm bảo độ khó thực tế.",
               "- Simulator/evaluator là xấp xỉ Core V1, không thay thế analyzer hay runtime chính thức.",
               "- Mẫu theo tầng nhỏ; các khoảng tin cậy không điều chỉnh cho cách chọn mẫu.",
               "- Mỗi case thường chạy một lần; LLM có tính ngẫu nhiên.",
               "- Trần vòng, thời gian và chi phí có thể cắt cụt hội tụ muộn.",
               "- Judge có thể cùng họ model và bị thiên lệch.",
               "- Agent không có đồng hồ đáng tin cậy cho mốc tuyệt đối.", ""])
    (directory / "summary.md").write_text("\n".join(md), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(generate(args.run), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
