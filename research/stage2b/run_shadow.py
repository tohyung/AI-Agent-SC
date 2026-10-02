#!/usr/bin/env python3
"""Run research-only IntentSpec extraction against frozen candidate cases."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from marlowe_ai_agent.marlowe_agent.models import LLMError, LLMBudgetError  # noqa: E402
from research.stage2a import verify_freeze  # noqa: E402
from research.stage2b.intent_spec import CORE_SCHEMA_VERSION, validate_intent_spec  # noqa: E402
from research.stage2b.live_safety import (  # noqa: E402
    EXPERIMENT_VERSION, STAGE2A_AGGREGATE_SHA256, LivePreflightError,
    make_live_budget, require_clean_worktree, safe_transport_metadata,
    validate_live_outputs, write_execution_summary,
)
from research.stage2b.model_errors import sanitized_model_error  # noqa: E402
from research.stage2b.projector import classify_projection, project_intent_spec  # noqa: E402
from research.stage2b.scoring import FrozenCandidateAdapter, MANIFEST  # noqa: E402
from research.stage2b.shadow_extractor import (  # noqa: E402
    IntentShadowExtractor, InvalidModelOutput, LegacyReasonerTransport, build_prompt,
)


_sanitized_model_error = sanitized_model_error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id")
    parser.add_argument("--split", choices=("development", "validation"), default="development")
    parser.add_argument("--all-canonical", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--live", action="store_true")
    parser.add_argument("--model")
    parser.add_argument("--max-physical-calls", type=int)
    parser.add_argument("--max-spend-usd")
    parser.add_argument("--per-request-cost-ceiling-usd")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.live and args.output is None:
        parser.error("--live requires an explicit --output path")
    if args.live:
        for name in ("model", "max_physical_calls", "max_spend_usd",
                     "per_request_cost_ceiling_usd"):
            if not getattr(args, name):
                parser.error(f"--live requires --{name.replace('_', '-')}")
        try:
            budget = make_live_budget(args.max_physical_calls, 60, args.max_spend_usd,
                                      args.per_request_cost_ceiling_usd)
        except ValueError as exc:
            parser.error(str(exc))
        try:
            validate_live_outputs(args.output, ROOT)
        except LivePreflightError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    if args.all_canonical and (args.case_id or args.split != "development"):
        parser.error("--all-canonical cannot be combined with --case-id or --split")
    try:
        aggregate = verify_freeze.verify_freeze(MANIFEST)
        if args.live and aggregate != STAGE2A_AGGREGATE_SHA256:
            raise ValueError("frozen corpus aggregate does not match experiment baseline")
        candidates = FrozenCandidateAdapter().load(
            split=args.split, all_canonical=args.all_canonical, case_id=args.case_id)
        code_sha = require_clean_worktree(ROOT) if args.live else None
        model = LegacyReasonerTransport(args.model) if args.live else None
        if model is not None:
            model.reasoner.set_call_budget(budget.effective_calls)
        extractor = IntentShadowExtractor(model) if model is not None else None
    except (OSError, ValueError, LLMError, LivePreflightError) as exc:
        print(str(exc) if isinstance(exc, LivePreflightError)
              else f"Shadow precheck failed: {type(exc).__name__}", file=sys.stderr)
        return 2

    try:
        writer = args.output.open("x", encoding="utf-8") if args.output else sys.stdout
    except OSError:
        print("Shadow precheck failed: output cannot be created exclusively", file=sys.stderr)
        return 2
    transport = safe_transport_metadata(model.reasoner) if model is not None else None
    if args.live:
        print(json.dumps({"experiment_version": EXPERIMENT_VERSION, "code_sha": code_sha,
                          "model": args.model, "cases": len(candidates), "budget": budget.to_dict(),
                          "transport": transport}))
    count = 0
    model_error_cases = 0
    core_invalid_cases = 0
    projection_bug_cases = 0
    budget_exhausted = False
    status = "COMPLETED"
    exit_code = 0
    try:
        for candidate in candidates:
            if model is not None and model.reasoner.llm_calls >= budget.effective_calls:
                budget_exhausted = True
                break
            history = candidate["requirement_history"]
            record = {
                "case_id": candidate["case_id"],
                "split": candidate["split"],
                "model": model.reasoner.model if model is not None else None,
                "schema_version": CORE_SCHEMA_VERSION,
                "source_corpus_version": "stage2a-v1",
                "source_corpus_aggregate_sha256": aggregate,
                "semantic_core": None,
                "core_validation_errors": [],
                "projection_diagnostics": None,
                "projection_classification": None,
                "prediction": None,
                "validation_errors": [],
                "usage": None,
                "run_status": "dry_run" if extractor is None else "ok",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            if args.live:
                record.update(experiment_version=EXPERIMENT_VERSION, code_sha=code_sha,
                              budget=budget.to_dict())
            if extractor is None:
                system, user = build_prompt(history)
                record["prompt"] = {"system": system, "user": user}
            else:
                usage_before = model.request_count()
                try:
                    core = extractor.extract(history)
                except LLMBudgetError:
                    budget_exhausted = True
                    break
                except (LLMError, TimeoutError, json.JSONDecodeError, InvalidModelOutput) as exc:
                    record["run_status"] = "model_error"
                    record["model_error"] = sanitized_model_error(exc)
                else:
                    record["semantic_core"] = core.to_dict()
                    record["core_validation_errors"] = core.validation_errors(
                        expected_history=history)
                    projection = project_intent_spec(core, expected_history=history)
                    record["prediction"] = projection.intent_spec.to_dict()
                    record["projection_diagnostics"] = projection.projection_diagnostics
                    record["validation_errors"] = validate_intent_spec(
                        record["prediction"], expected_history=history,
                        projected_core=record["semantic_core"])
                    record["projection_classification"] = classify_projection(
                        record["core_validation_errors"], record["validation_errors"],
                        record["projection_diagnostics"])
                    if record["projection_classification"] == "CORE_INVALID":
                        record["run_status"] = "core_invalid"
                    elif record["projection_classification"] == "PROJECTOR_BUG":
                        record["run_status"] = "projection_invalid"
                finally:
                    record["usage"] = model.usage_window(usage_before)
            writer.write(json.dumps(record, ensure_ascii=False) + "\n")
            writer.flush()
            if args.output and args.live:
                os.fsync(writer.fileno())
            count += 1
            model_error_cases += record["run_status"] == "model_error"
            core_invalid_cases += record["run_status"] == "core_invalid"
            projection_bug_cases += record["run_status"] == "projection_invalid"
        if budget_exhausted:
            status, exit_code = "BUDGET_EXHAUSTED", 2
    except Exception:
        if not args.live:
            raise
        status, exit_code = "INFRASTRUCTURE_FAILED", 3
    finally:
        if args.output:
            writer.close()
    if args.output:
        print(f"Wrote {count} shadow records to {args.output.name}")
        if model is not None:
            summary = {"experiment_version": EXPERIMENT_VERSION, "experiment_status": status,
                       "code_sha": code_sha, "model": args.model,
                       "requested_cases": len(candidates), "completed_cases": count,
                       "model_error_cases": model_error_cases,
                       "core_invalid_cases": core_invalid_cases,
                       "projection_bug_cases": projection_bug_cases,
                       "budget_exhausted": budget_exhausted,
                       "budget": budget.to_dict(), "transport": transport,
                       "usage": model.usage()}
            try:
                write_execution_summary(args.output, summary)
            except OSError:
                print("Shadow summary could not be persisted", file=sys.stderr)
                return 3
            print(json.dumps(summary))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
