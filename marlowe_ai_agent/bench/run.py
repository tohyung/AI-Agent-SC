from __future__ import annotations

import argparse
import json
import os
import random
import re
from datetime import datetime
from pathlib import Path

from marlowe_agent.models import LLMConfigError
from marlowe_agent.openai_reasoner import OpenAIReasoner

from .cases import load_cases
from .config import (DATASET, DEFAULT_ITERATIONS, DEFAULT_LLM_CALLS, DEFAULT_SEED,
                     DEFAULT_WALL_SECONDS, DEFAULT_WORKERS, RESULTS)
from .report import generate
from .runner import dataset_hash, run_many
from .validate_dataset import validate


def _price(name: str) -> float | None:
    value = os.getenv(name)
    return float(value) if value else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Marlowe offline-first convergence benchmark")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--smoke", type=int, metavar="N")
    mode.add_argument("--all", action="store_true")
    parser.add_argument("--fake", action="store_true")
    parser.add_argument("--fake-wrong", action="store_true")
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--max-iterations", type=int, default=DEFAULT_ITERATIONS)
    parser.add_argument("--max-llm-calls", type=int, default=DEFAULT_LLM_CALLS)
    parser.add_argument("--wall-clock", type=float, default=DEFAULT_WALL_SECONDS)
    parser.add_argument("--max-usd", type=float, default=_price("BENCH_MAX_USD"))
    parser.add_argument("--repeat-subset", type=int, default=0)
    parser.add_argument("--extend-nonconverged", type=int, default=0)
    parser.add_argument("--dataset", type=Path, default=DATASET)
    args = parser.parse_args()
    if args.workers < 1 or args.max_iterations < 1 or args.max_llm_calls < 1 or args.wall_clock <= 0:
        parser.error("Limits and workers must be positive")
    cases = load_cases(args.dataset)
    issues = validate(cases)
    if issues:
        parser.error("Dataset validation failed: " + ", ".join(issues[:5]))
    digest = dataset_hash(args.dataset)
    model = os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL")
    judge_model = os.getenv("BENCH_JUDGE_MODEL") or model
    user_model = os.getenv("BENCH_USER_MODEL") or judge_model
    if not args.fake:
        try:
            # Only the existing reasoner reads .env; no key or file content is logged.
            probe = OpenAIReasoner(model=model)
            model = probe.model
            judge_model = os.getenv("BENCH_JUDGE_MODEL") or model
            user_model = os.getenv("BENCH_USER_MODEL") or judge_model
        except (LLMConfigError, RuntimeError) as exc:
            print("Không thể khởi tạo LLM benchmark: " + re.sub(r"\b(?:sk|or)-[A-Za-z0-9_-]{8,}\b", "[REDACTED]", str(exc)))
            raise SystemExit(2) from None
        if args.max_usd is None:
            parser.error("Real benchmark requires --max-usd or BENCH_MAX_USD")
    slug = re.sub(r"[^a-z0-9]+", "-", (model or "fake").lower()).strip("-")[:40]
    directory = args.resume or RESULTS / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + slug)
    if args.all and not args.fake:
        smoke_path = directory / "smoke.json"
        if not smoke_path.exists():
            parser.error("Run --smoke 5 first, then --all --resume <smoke-dir>")
        smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
        if smoke["dataset_sha256"] != digest or smoke["estimated_100_usd"] is None:
            parser.error("Smoke data cannot establish safe cost estimate")
        if smoke["estimated_100_usd"] > args.max_usd:
            parser.error("Projected 100-case cost exceeds budget")
        if smoke["anomaly"]:
            parser.error("Smoke anomaly; inspect report before full run")
    if args.smoke:
        rng = random.Random(args.seed)
        selected = []
        seen_types = set()
        candidates = cases.copy()
        rng.shuffle(candidates)
        for case in candidates:
            if case.type not in seen_types:
                selected.append(case)
                seen_types.add(case.type)
                if len(selected) >= args.smoke:
                    break
        if len(selected) < args.smoke:
            selected.extend(case for case in candidates if case not in selected)
        selected = selected[:args.smoke]
    else:
        selected = cases
    rows = run_many(selected, directory, workers=args.workers, seed=args.seed, max_usd=args.max_usd,
                    model=model, judge_model=judge_model, user_model=user_model,
                    max_iterations=args.max_iterations, max_llm_calls=args.max_llm_calls,
                    wall_clock=args.wall_clock, fake=args.fake, fake_wrong=args.fake_wrong,
                    dataset_sha256=digest,
                    prices=(_price("BENCH_PRICE_IN_PER_M"), _price("BENCH_PRICE_OUT_PER_M")))
    extra = {"workers": args.workers, "seed": args.seed, "max_usd": args.max_usd,
             "model": model, "judge_model": judge_model, "user_model": user_model,
             "max_iterations": args.max_iterations, "max_llm_calls": args.max_llm_calls,
             "wall_clock": args.wall_clock, "fake": args.fake, "fake_wrong": args.fake_wrong,
             "dataset_sha256": digest,
             "prices": (_price("BENCH_PRICE_IN_PER_M"), _price("BENCH_PRICE_OUT_PER_M"))}
    if args.all and args.repeat_subset:
        rng = random.Random(args.seed)
        by_level = {level: [case for case in cases if case.difficulty == level] for level in (1, 2, 3, 4)}
        repeated = []
        while len(repeated) < args.repeat_subset and any(by_level.values()):
            for level in (1, 2, 3, 4):
                if by_level[level] and len(repeated) < args.repeat_subset:
                    repeated.append(by_level[level].pop(rng.randrange(len(by_level[level]))))
        rows = run_many(repeated, directory, attempt=2, **extra)
    if args.all and args.extend_nonconverged:
        nonconverged = {row["case_id"] for row in rows if row.get("attempt") == 1
                        and not row.get("converged")}
        extended = [case for case in cases if case.id in nonconverged][:args.extend_nonconverged]
        extended_options = extra | {"max_iterations": args.max_iterations * 3,
                                    "max_llm_calls": args.max_llm_calls * 3,
                                    "wall_clock": args.wall_clock * 3}
        rows = run_many(extended, directory, attempt=3, **extended_options)
    if args.smoke and not args.fake:
        smoke_rows = [row for row in rows if row["case_id"] in {case.id for case in selected}]
        costs = [row.get("cost_usd") for row in smoke_rows]
        estimate = (sum(costs) / len(costs) * 100) if costs and all(c is not None for c in costs) else None
        anomaly = (len(smoke_rows) != len(selected) or all(row.get("stop_reason") in {"llm_error", "harness_error", "wallclock_timeout"}
                                                             for row in smoke_rows)
                   or any(row.get("judge") is None or "error" in row.get("judge", {}) for row in smoke_rows)
                   or estimate is None
                   or (estimate == 0 and model is not None and not model.endswith(":free")))
        (directory / "smoke.json").write_text(json.dumps({"dataset_sha256": digest,
                                                           "estimated_100_usd": estimate,
                                                           "anomaly": anomaly}, indent=2), encoding="utf-8")
        print(f"Smoke estimate for 100 cases: {estimate} USD; anomaly={anomaly}")
    summary = generate(directory)
    print(f"Result directory: {directory.resolve()}")
    print(f"Runs: {len(rows)}; feasible converged: {summary['counts']['converged']}/{summary['n']}; "
          f"cost: {summary['total_cost_usd']} USD")


if __name__ == "__main__":
    main()
