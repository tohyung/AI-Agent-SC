"""E6 scoring: collect both arms, write blind adjudication packets, score RQ3 and RQ4.

  python -m research.experiments.e6_score packets --out runs/E6-Adjudication
  python -m research.experiments.e6_score score --out runs/E6-Adjudication --verdicts <file>

`packets` hides which arm made each contract behind a random code; the code-to-arm key goes to a
separate file that the adjudicator opens only after every verdict is written (docs/E6-Protocol.md).
A verdict per code is {"contract": "RIGHT" | "WRONG" | "UNDETERMINED" | null, "told_unsupported":
bool, "reason": str}; `contract` is null when the arm delivered no contract.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import random
import secrets
import sys
from typing import Any

from research.experiments.baseline_llm import ROOT, is_counted

DATASET_V3 = ROOT / "dataset" / "v3" / "cases.jsonl"
PIPELINE_DIR = ROOT / "runs" / "E6-Pipeline"
BASELINE_DIR = ROOT / "runs" / "E6-Baseline"
ARMS = ("pipeline", "baseline")
BOOTSTRAP_SEED = 20261111
BOOTSTRAP_ROUNDS = 10_000
LEDGER_DELIVERED = {"SUCCEEDED", "INCONCLUSIVE"}


def _attempts(case_dir: Path) -> list[dict[str, Any]]:
    return [json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(case_dir.glob("attempt-*.json"))]


def _usage(log: list[dict[str, Any]]) -> dict[str, Any]:
    counted = [entry for entry in log if is_counted(entry)]
    return {"requests": len(counted),
            "prompt_tokens": sum(entry.get("prompt_tokens") or 0 for entry in counted),
            "completion_tokens": sum(entry.get("completion_tokens") or 0 for entry in counted),
            "model_seconds": round(sum(entry.get("seconds") or 0 for entry in log), 1)}


def pipeline_outcome(case_dir: Path) -> dict[str, Any]:
    """The pipeline arm's result on one case: the last attempt decides what was delivered."""
    attempts = _attempts(case_dir)
    if not attempts:
        raise ValueError(f"no pipeline attempts in {case_dir}")
    last = attempts[-1]
    contract = None
    ledger = last.get("steps", {}).get("ledger_validation", {})
    if ledger.get("run_status") in LEDGER_DELIVERED:
        ids = last["steps"]["compile"]["output_artifacts"]
        contract = last["artifacts"][ids[0]]["payload"]["contract"]
    log = [entry for record in attempts for entry in record.get("model_call_log_this_attempt", [])]
    history = last.get("requirement_history") or []
    expectations = {json.dumps(record["simulated_expectation"], sort_keys=True)
                    for record in attempts if record.get("simulated_expectation")}
    final = [f"status: {last.get('status')}", f"stop_reason: {last.get('stop_reason')}",
             *[f"question: {item}" for item in last.get("questions") or []],
             *[f"diagnostic: {item}" for item in last.get("blocking_diagnostics") or []]]
    return {"arm": "pipeline", "contract": contract, "final_message": "\n".join(final),
            "user_messages": [message for revision in history[1:] for message in revision["messages"]],
            "cost": {**_usage(log),
                     "user_messages": max(len(history) - 1, 0),
                     "intent_reviews": len({record["reviewed_candidate_id"] for record in attempts
                                            if record.get("reviewed_candidate_id")}),
                     "scenarios": len(expectations), "forwarded_errors": 0,
                     "cap_reached": False}}


def baseline_outcome(case_dir: Path) -> dict[str, Any]:
    session = json.loads((case_dir / "session.json").read_text(encoding="utf-8"))
    if session["status"] not in {"accepted", "gave_up", "cap_reached"}:
        raise ValueError(f"baseline session in {case_dir} has not ended ({session['status']})")
    last = next((turn["reply"] for turn in reversed(session["transcript"])
                 if turn["role"] == "assistant" and isinstance(turn.get("reply"), dict)), {})
    return {"arm": "baseline", "contract": session["delivered_contract"],
            "final_message": str(last.get("message", "")),
            "user_messages": [turn["content"] for turn in session["transcript"]
                              if turn.get("source") == "simulated_user"],
            "cost": {**_usage(session["call_log"]), "user_messages": session["user_turns"],
                     "intent_reviews": 0, "scenarios": 0,
                     "forwarded_errors": session["forwarded_errors"],
                     "cap_reached": session["status"] == "cap_reached"}}


def load_cases() -> list[dict[str, Any]]:
    with DATASET_V3.open(encoding="utf-8") as source:
        return [json.loads(line) for line in source]


def collect(pipeline_dir: Path = PIPELINE_DIR, baseline_dir: Path = BASELINE_DIR
            ) -> dict[int, dict[str, dict[str, Any]]]:
    """Cases where both arms have finished, keyed by case index."""
    results: dict[int, dict[str, dict[str, Any]]] = {}
    for index in range(1, 101):
        name = f"case-{index:03d}"
        if not (pipeline_dir / name).is_dir() or not (baseline_dir / name / "session.json").is_file():
            continue
        results[index] = {"pipeline": pipeline_outcome(pipeline_dir / name),
                          "baseline": baseline_outcome(baseline_dir / name)}
    return results


def write_packets(results: dict[int, dict[str, dict[str, Any]]], cases: list[dict[str, Any]],
                  out: Path, *, rng: random.Random | None = None) -> None:
    """Shuffled packets with random codes; the arm key goes to its own file."""
    rng = rng or random.SystemRandom()
    out.mkdir(parents=True, exist_ok=True)
    packets, key = [], {}
    for index, arms in results.items():
        case = cases[index - 1]
        for arm in ARMS:
            code = f"{rng.getrandbits(48):012x}" if not isinstance(rng, random.SystemRandom) \
                else secrets.token_hex(6)
            key[code] = {"case_index": index, "arm": arm}
            outcome = arms[arm]
            packets.append({"code": code, "case_index": index, "case_id": case["id"],
                            "prompt": case["prompt"], "fact_sheet": case["fact_sheet"],
                            "user_messages": outcome["user_messages"],
                            "final_message": outcome["final_message"],
                            "contract": outcome["contract"]})
    rng.shuffle(packets)
    with (out / "packets.jsonl").open("x", encoding="utf-8") as writer:
        for packet in packets:
            writer.write(json.dumps(packet, ensure_ascii=False) + "\n")
    with (out / "blind-key.json").open("x", encoding="utf-8") as writer:
        json.dump(key, writer, indent=1)


def classify(expected: str, verdict: dict[str, Any]) -> str:
    """SUCCESS, WRONG_DELIVERY, NO_DELIVERY, RIGHT_NO_NOTICE or UNDETERMINED (protocol, section 4)."""
    contract = verdict.get("contract")
    told = verdict.get("told_unsupported") is True
    if contract not in {None, "RIGHT", "WRONG", "UNDETERMINED"}:
        raise ValueError(f"invalid contract verdict {contract!r}")
    if expected == "reject_unsupported":
        if contract is None:
            return "SUCCESS" if told else "NO_DELIVERY"
        return "WRONG_DELIVERY"
    if contract == "UNDETERMINED":
        return "UNDETERMINED"
    if contract is None:
        return "NO_DELIVERY"
    if contract == "WRONG":
        return "WRONG_DELIVERY"
    if expected == "converge_and_decline_extra" and not told:
        return "RIGHT_NO_NOTICE"
    return "SUCCESS"


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value from the discordant counts b and c."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def paired_comparison(pipeline: list[bool], baseline: list[bool], *,
                      rounds: int = BOOTSTRAP_ROUNDS, seed: int = BOOTSTRAP_SEED) -> dict[str, Any]:
    n = len(pipeline)
    if n == 0 or n != len(baseline):
        raise ValueError("paired outcomes must be nonempty and of equal length")
    rate_p, rate_b = sum(pipeline) / n, sum(baseline) / n
    b = sum(1 for x, y in zip(pipeline, baseline) if x and not y)
    c = sum(1 for x, y in zip(pipeline, baseline) if y and not x)
    rng = random.Random(seed)
    deltas = []
    for _ in range(rounds):
        sample = [rng.randrange(n) for _ in range(n)]
        deltas.append(sum(pipeline[i] - baseline[i] for i in sample) / n)
    deltas.sort()
    delta = rate_p - rate_b
    return {"n": n, "pipeline_rate": rate_p, "baseline_rate": rate_b, "delta": delta,
            "delta_ci95": [deltas[int(0.025 * rounds)], deltas[int(0.975 * rounds) - 1]],
            "relative": delta / rate_b if rate_b else None,
            "pipeline_only": b, "baseline_only": c, "mcnemar_p": mcnemar_exact(b, c)}


def conclusion(comparison: dict[str, Any], alpha: float = 0.05) -> str:
    if comparison["mcnemar_p"] < alpha and comparison["delta"] > 0:
        return "pipeline stronger"
    if comparison["mcnemar_p"] < alpha and comparison["delta"] < 0:
        return "baseline stronger"
    return "not distinguished"


def score(results: dict[int, dict[str, dict[str, Any]]], cases: list[dict[str, Any]],
          verdicts: dict[str, dict[str, Any]], key: dict[str, dict[str, Any]]) -> dict[str, Any]:
    by_case: dict[int, dict[str, str]] = {}
    for code, entry in key.items():
        if code not in verdicts:
            raise ValueError(f"verdict missing for packet {code}")
        expected = cases[entry["case_index"] - 1]["expected_behavior"]
        by_case.setdefault(entry["case_index"], {})[entry["arm"]] = classify(expected, verdicts[code])
    rows = []
    for index in sorted(by_case):
        case = cases[index - 1]
        rows.append({"case_index": index, "case_id": case["id"], "family": case["family"],
                     "language": case["language"], "expected_behavior": case["expected_behavior"],
                     **{arm: by_case[index][arm] for arm in ARMS},
                     "cost": {arm: results[index][arm]["cost"] for arm in ARMS}})
    paired = [row for row in rows if "UNDETERMINED" not in (row["pipeline"], row["baseline"])]
    report: dict[str, Any] = {"cases_scored": len(rows), "cases_paired": len(paired),
                              "undetermined": len(rows) - len(paired), "rows": rows}
    if paired:
        success = paired_comparison([row["pipeline"] == "SUCCESS" for row in paired],
                                    [row["baseline"] == "SUCCESS" for row in paired])
        wrong = paired_comparison([row["pipeline"] == "WRONG_DELIVERY" for row in paired],
                                  [row["baseline"] == "WRONG_DELIVERY" for row in paired])
        report["rq3_success"] = {**success, "conclusion": conclusion(success)}
        # For wrong deliveries lower is better: a positive delta means the pipeline delivers more.
        report["rq3_wrong_delivery"] = wrong
    report["outcomes"] = {arm: {kind: sum(1 for row in rows if row[arm] == kind)
                                for kind in ("SUCCESS", "WRONG_DELIVERY", "NO_DELIVERY",
                                             "RIGHT_NO_NOTICE", "UNDETERMINED")} for arm in ARMS}
    report["rq4_totals"] = {arm: {field: sum(row["cost"][arm][field] for row in rows)
                                  for field in ("requests", "prompt_tokens", "completion_tokens",
                                                "model_seconds", "user_messages", "intent_reviews",
                                                "scenarios", "forwarded_errors", "cap_reached")}
                            for arm in ARMS}
    for arm in ARMS:
        wins = report["outcomes"][arm]["SUCCESS"]
        report["rq4_totals"][arm]["requests_per_success"] = (
            report["rq4_totals"][arm]["requests"] / wins if wins else None)
    for field in ("expected_behavior", "family", "language"):
        groups: dict[str, dict[str, int]] = {}
        for row in paired:
            group = groups.setdefault(row[field], {"n": 0, "pipeline": 0, "baseline": 0})
            group["n"] += 1
            for arm in ARMS:
                group[arm] += row[arm] == "SUCCESS"
        report[f"success_by_{field}"] = groups
    return report


def main() -> int:
    if os.name == "nt":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="E6 blind adjudication packets and scoring")
    parser.add_argument("command", choices=["packets", "score"])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--pipeline-dir", type=Path, default=PIPELINE_DIR)
    parser.add_argument("--baseline-dir", type=Path, default=BASELINE_DIR)
    parser.add_argument("--verdicts", type=Path)
    args = parser.parse_args()
    cases = load_cases()
    results = collect(args.pipeline_dir, args.baseline_dir)
    if args.command == "packets":
        write_packets(results, cases, args.out)
        print(f"{len(results)} cases, {2 * len(results)} packets in {args.out}")
        return 0
    if args.verdicts is None:
        parser.error("score needs --verdicts")
    verdicts = json.loads(args.verdicts.read_text(encoding="utf-8"))
    key = json.loads((args.out / "blind-key.json").read_text(encoding="utf-8"))
    report = score(results, cases, verdicts, key)
    (args.out / "score.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n",
                                         encoding="utf-8")
    print(json.dumps({key_: report[key_] for key_ in ("cases_paired", "outcomes", "rq3_success")
                      if key_ in report}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
