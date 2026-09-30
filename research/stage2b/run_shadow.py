#!/usr/bin/env python3
"""Run research-only IntentSpec extraction against frozen candidate cases."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from research.stage2a import verify_freeze  # noqa: E402
from research.stage2b.intent_spec import SCHEMA_VERSION  # noqa: E402
from research.stage2b.scoring import FrozenCandidateAdapter, MANIFEST  # noqa: E402
from research.stage2b.shadow_extractor import (  # noqa: E402
    IntentShadowExtractor, LegacyReasonerTransport, build_prompt,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id")
    parser.add_argument("--split", choices=("development", "validation"), default="development")
    parser.add_argument("--all-canonical", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--live", action="store_true")
    parser.add_argument("--model")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.live and args.output is None:
        parser.error("--live requires an explicit --output path")
    if args.all_canonical and (args.case_id or args.split != "development"):
        parser.error("--all-canonical cannot be combined with --case-id or --split")
    try:
        aggregate = verify_freeze.verify_freeze(MANIFEST)
        candidates = FrozenCandidateAdapter().load(
            split=args.split, all_canonical=args.all_canonical, case_id=args.case_id)
        model = LegacyReasonerTransport(args.model) if args.live else None
        extractor = IntentShadowExtractor(model) if model is not None else None
        records = []
        for candidate in candidates:
            history = candidate["requirement_history"]
            record = {
                "case_id": candidate["case_id"],
                "split": candidate["split"],
                "model": model.reasoner.model if model is not None else None,
                "schema_version": SCHEMA_VERSION,
                "source_corpus_version": "stage2a-v1",
                "source_corpus_aggregate_sha256": aggregate,
                "prediction": None,
                "validation_errors": [],
                "usage": None,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            if extractor is None:
                system, user = build_prompt(history)
                record["prompt"] = {"system": system, "user": user}
            else:
                prediction = extractor.extract(history)
                record["prediction"] = prediction.to_dict()
                record["validation_errors"] = prediction.validation_errors(
                    expected_history=history)
                record["usage"] = model.usage()
            records.append(record)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Shadow run failed: {exc}", file=sys.stderr)
        return 2
    lines = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
    if args.output:
        args.output.write_text(lines, encoding="utf-8")
        print(f"Wrote {len(records)} shadow records to {args.output}")
    else:
        sys.stdout.write(lines)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
