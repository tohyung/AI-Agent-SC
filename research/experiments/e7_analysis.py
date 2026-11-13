"""E7 analysis: join machine scoring with blind adjudication and compute RQ3/RQ4 (E7 protocol 3-4).

Written after the freeze (protocol 5) and committed before the overall results are opened.

Inputs
- Run directories `runs/E7-Eval-Pipeline` and `runs/E7-Eval-Baseline` (one `case-NNN` per case).
- Machine scoring from `e7_score --dataset v5`, one file per arm and time tolerance, in one folder:
  `pipeline-1m.json`, `pipeline-1h.json`, `pipeline-1d.json`, `pipeline-3d.json`, and the same for
  `baseline-*`. The 1-minute files are the frozen rule (Q-GIỜ 1); the others feed only the
  sensitivity table (Q-GIỜ 6).

Rules (fixed here, before the results are seen)
- Delivery. Pipeline: `final.json` says `delivered`; the contract is the one the last attempt
  delivered. Baseline: `session.json` has `delivered_contract`. A pipeline case that did not deliver
  has no contract, whatever the last attempt holds.
- Contract verdict (Q-CHẤM 1-2): RIGHT when the machine says RIGHT; when it says REVIEW, the
  adjudicator's verdict (RIGHT, WRONG or UNDETERMINED); no contract when nothing was delivered.
- The adjudicator also judges, for `converge_and_decline_extra` and `reject_unsupported` only,
  whether the arm clearly said which part it could not do (`told_unsupported`), since Q-CHẤM 5 needs
  it. Those packets ask only that question when the machine already said RIGHT or nothing was
  delivered.
- Outcome per arm and case (Q-CHẤM 5): SUCCESS, WRONG_DELIVERY, NO_DELIVERY, RIGHT_NO_NOTICE or
  UNDETERMINED, by `e6_score.classify`.
- RQ3 main: paired success rate, exact two-sided McNemar, alpha 0.05, paired bootstrap 10 000 rounds,
  seed 20261111 (`e6_score.paired_comparison`); cases with an UNDETERMINED outcome on either arm are
  left out of the pairing and counted.
- Sensitivity at tolerance T: the contract verdict is RIGHT when the machine at T says RIGHT; else the
  1-minute verdict stands. Scenario checks do not depend on T, so RIGHT at 1 minute stays RIGHT.
- RQ4: totals and medians per case of requests, prompt and completion tokens, model seconds, user
  messages and scenarios; requests per success. Requests and tokens count only calls with a model
  response (E6 rule), and the pipeline's include its example conversions.
- Sim-user report: turns, replies the checker rejected, fallback replies, objections to a shown
  result, and invalid subagent turns (from `subagent-audit.jsonl`).

  python -m research.experiments.e7_analysis packets --machine DIR --out DIR
  python -m research.experiments.e7_analysis score --machine DIR --out DIR --verdicts FILE
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import random
import re
import secrets
import statistics
import sys
from typing import Any

from research.experiments.baseline_llm import is_counted, pipeline_requests
from research.experiments.e6_score import (ARMS, baseline_outcome, classify, conclusion,
                                           paired_comparison, pipeline_outcome)

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "dataset" / "v5" / "cases.jsonl"
PIPELINE_DIR = ROOT / "runs" / "E7-Eval-Pipeline"
BASELINE_DIR = ROOT / "runs" / "E7-Eval-Baseline"
TOLERANCES = ("1m", "1h", "1d", "3d")
TOLD_BEHAVIORS = {"converge_and_decline_extra", "reject_unsupported"}
OUTCOMES = ("SUCCESS", "WRONG_DELIVERY", "NO_DELIVERY", "RIGHT_NO_NOTICE", "UNDETERMINED")
STATUS_LINE = re.compile(r"^(?:status|stop_reason):", re.IGNORECASE)
RESULT_LABEL = re.compile(r"^\[RESULT[^\]]*\]\s*")
COST_FIELDS = ("requests", "prompt_tokens", "completion_tokens", "model_seconds", "user_messages",
               "scenarios")


# -- loading ----------------------------------------------------------------------------------

def load_cases(path: Path = DATASET) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _simuser(case_dir: Path) -> dict[str, Any]:
    path = case_dir / "simuser.json"
    return _json(path) if path.exists() else {"history": [], "turns": [], "user_messages": 0}


def _example_logs(case_dir: Path) -> list[dict[str, Any]]:
    return [entry for path in sorted(case_dir.glob("examples-*.json"))
            for entry in _json(path).get("model_call_log") or []]


def _usage(log: list[dict[str, Any]]) -> dict[str, Any]:
    counted = [entry for entry in log if is_counted(entry)]
    return {"prompt_tokens": sum(entry.get("prompt_tokens") or 0 for entry in counted),
            "completion_tokens": sum(entry.get("completion_tokens") or 0 for entry in counted),
            "model_seconds": round(sum(entry.get("seconds") or 0 for entry in log), 1)}


def pipeline_result(case_dir: Path) -> dict[str, Any]:
    final = _json(case_dir / "final.json")
    outcome = pipeline_outcome(case_dir)
    contract = outcome["contract"] if final.get("delivered") else None
    if final.get("delivered") and contract is None:
        raise ValueError(f"{case_dir.name}: final.json says delivered but no contract was found")
    log = [entry for path in sorted(case_dir.glob("attempt-*.json"))
           for entry in _json(path).get("model_call_log_this_attempt") or []] + _example_logs(case_dir)
    simuser = _simuser(case_dir)
    return {"contract": contract, "end": final.get("end"),
            "final_message": outcome["final_message"], "history": simuser["history"],
            "cost": {"requests": pipeline_requests(case_dir), **_usage(log),
                     "user_messages": simuser["user_messages"],
                     "scenarios": len(final.get("scenarios") or {})}}


def baseline_result(case_dir: Path) -> dict[str, Any]:
    outcome = baseline_outcome(case_dir)
    session = _json(case_dir / "session.json")
    simuser = _simuser(case_dir)
    return {"contract": outcome["contract"], "end": session["status"],
            "final_message": outcome["final_message"], "history": simuser["history"],
            "cost": {"requests": outcome["cost"]["requests"], **_usage(session["call_log"]),
                     "user_messages": simuser["user_messages"], "scenarios": 0,
                     "cap": session.get("cap"), "cap_reached": session["status"] == "cap_reached"}}


def collect(cases: list[dict[str, Any]], pipeline_dir: Path = PIPELINE_DIR,
            baseline_dir: Path = BASELINE_DIR) -> dict[int, dict[str, dict[str, Any]]]:
    """Every case of the dataset; a case missing on either arm is an error (all 100 must run)."""
    results = {}
    for index in range(1, len(cases) + 1):
        name = f"case-{index:03d}"
        if not (pipeline_dir / name / "final.json").exists():
            raise ValueError(f"pipeline {name} has not ended")
        if not (baseline_dir / name / "session.json").exists():
            raise ValueError(f"baseline {name} has not run")
        results[index] = {"pipeline": pipeline_result(pipeline_dir / name),
                          "baseline": baseline_result(baseline_dir / name)}
    return results


def load_machine(machine_dir: Path) -> dict[str, dict[str, dict[int, dict[str, Any]]]]:
    machine: dict[str, dict[str, dict[int, dict[str, Any]]]] = {}
    for arm in ARMS:
        machine[arm] = {}
        for tolerance in TOLERANCES:
            path = machine_dir / f"{arm}-{tolerance}.json"
            if path.exists():
                machine[arm][tolerance] = {int(key): value for key, value in _json(path).items()}
        if "1m" not in machine[arm]:
            raise ValueError(f"{machine_dir}: {arm}-1m.json is required")
    return machine


def _machine_verdict(machine: dict[int, dict[str, Any]], index: int, contract: Any) -> str:
    """RIGHT, REVIEW or NONE, checked against what the arm actually delivered."""
    verdict = (machine.get(index) or {}).get("verdict")
    if contract is None:
        return "NONE"
    if verdict not in {"RIGHT", "REVIEW"}:
        raise ValueError(f"case {index}: a contract was delivered but the machine verdict is "
                         f"{verdict!r}")
    return verdict


# -- blind packets ----------------------------------------------------------------------------

def _conversation(history: list[list[str]]) -> list[dict[str, str]]:
    return [{"role": "user" if who == "you" else "assistant",
             "text": RESULT_LABEL.sub("", text)} for who, text in history]


def _final_message(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not STATUS_LINE.match(line.strip()))


def packet_questions(expected: str, machine_verdict: str) -> list[str]:
    questions = ["contract"] if machine_verdict == "REVIEW" else []
    if expected in TOLD_BEHAVIORS:
        questions.append("told_unsupported")
    return questions


def write_packets(results: dict[int, dict[str, dict[str, Any]]], cases: list[dict[str, Any]],
                  machine: dict[str, dict[str, dict[int, dict[str, Any]]]], out: Path, *,
                  rng: random.Random | None = None) -> int:
    """Shuffled packets with random codes for what the adjudicator must judge; the arm key and
    the machine problems go to their own files, so the packet itself carries no arm name."""
    rng = rng or random.SystemRandom()
    out.mkdir(parents=True, exist_ok=True)
    packets, key = [], {}
    for index, arms in results.items():
        case = cases[index - 1]
        for arm in ARMS:
            outcome = arms[arm]
            verdict = _machine_verdict(machine[arm]["1m"], index, outcome["contract"])
            questions = packet_questions(case["expected_behavior"], verdict)
            if not questions:
                continue
            code = (f"{rng.getrandbits(48):012x}" if not isinstance(rng, random.SystemRandom)
                    else secrets.token_hex(6))
            key[code] = {"case_index": index, "arm": arm,
                         "machine_problems": machine[arm]["1m"].get(index, {}).get("problems", [])}
            packets.append({"code": code, "case_index": index, "case_id": case["id"],
                            "questions": questions, "prompt": case["prompt"],
                            "fact_sheet": case["fact_sheet"],
                            "conversation": _conversation(outcome["history"]),
                            "final_message": _final_message(outcome["final_message"]),
                            "machine_problems": key[code]["machine_problems"],
                            "contract": outcome["contract"]})
    rng.shuffle(packets)
    with (out / "packets.jsonl").open("x", encoding="utf-8") as writer:
        for packet in packets:
            writer.write(json.dumps(packet, ensure_ascii=False) + "\n")
    with (out / "blind-key.json").open("x", encoding="utf-8") as writer:
        json.dump(key, writer, indent=1)
    return len(packets)


# -- scoring ----------------------------------------------------------------------------------

def arm_verdict(expected: str, machine_verdict: str, judged: dict[str, Any] | None) -> dict[str, Any]:
    """The input of `classify`: the contract verdict and, where it matters, `told_unsupported`."""
    judged = judged or {}
    if machine_verdict == "NONE":
        contract = None
    elif machine_verdict == "RIGHT":
        contract = "RIGHT"
    else:
        contract = judged.get("contract")
        if contract not in {"RIGHT", "WRONG", "UNDETERMINED"}:
            raise ValueError(f"REVIEW contract needs an adjudicated verdict, got {contract!r}")
    told = judged.get("told_unsupported")
    if expected in TOLD_BEHAVIORS and told not in {True, False}:
        raise ValueError("told_unsupported must be judged for this expected behavior")
    return {"contract": contract, "told_unsupported": told is True}


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def simuser_report(arm_dir: Path, indexes: list[int]) -> dict[str, int]:
    report = {"turns": 0, "rejected_by_checker": 0, "fallbacks": 0, "objections": 0,
              "invalid_subagent_turns": 0}
    for index in indexes:
        case_dir = arm_dir / f"case-{index:03d}"
        log = _simuser(case_dir)
        turns = log["turns"]
        report["turns"] += sum(1 for turn in turns if not turn.get("problems"))
        report["rejected_by_checker"] += sum(1 for turn in turns if turn.get("problems"))
        report["fallbacks"] += sum(1 for turn in turns if turn.get("problems")
                                   and int(turn.get("retry", 0)) >= 2)
        history = log["history"]
        report["objections"] += sum(
            1 for (who, text), (next_who, next_text) in zip(history, history[1:])
            if who == "assistant" and text.startswith("[RESULT") and next_who == "you"
            and next_text not in {"(you accepted)", "(you gave up)"})
        audit = case_dir / "subagent-audit.jsonl"
        if audit.exists():
            report["invalid_subagent_turns"] += sum(
                1 for line in audit.read_text(encoding="utf-8").splitlines()
                if line and json.loads(line).get("problems"))
    return report


def _group_rates(rows: list[dict[str, Any]], field: str, outcome_key: str = "") -> dict[str, Any]:
    groups: dict[str, dict[str, int]] = {}
    for row in rows:
        group = groups.setdefault(str(row[field]), {"n": 0, "pipeline": 0, "baseline": 0})
        group["n"] += 1
        for arm in ARMS:
            group[arm] += row[arm + outcome_key] == "SUCCESS"
    return groups


def score(results: dict[int, dict[str, dict[str, Any]]], cases: list[dict[str, Any]],
          machine: dict[str, dict[str, dict[int, dict[str, Any]]]],
          verdicts: dict[str, dict[str, Any]], key: dict[str, dict[str, Any]],
          pipeline_dir: Path = PIPELINE_DIR, baseline_dir: Path = BASELINE_DIR) -> dict[str, Any]:
    judged: dict[tuple[int, str], dict[str, Any]] = {}
    for code, entry in key.items():
        if code not in verdicts:
            raise ValueError(f"verdict missing for packet {code}")
        judged[(entry["case_index"], entry["arm"])] = verdicts[code]
    rows = []
    for index in sorted(results):
        case = cases[index - 1]
        expected = case["expected_behavior"]
        row: dict[str, Any] = {"case_index": index, "case_id": case["id"], "family": case["family"],
                               "language": case["language"], "info_mode": case["info_mode"],
                               "expected_behavior": expected}
        for arm in ARMS:
            outcome = results[index][arm]
            base = _machine_verdict(machine[arm]["1m"], index, outcome["contract"])
            verdict = arm_verdict(expected, base, judged.get((index, arm)))
            row[arm] = classify(expected, verdict)
            row[arm + "_machine"] = base
            row[arm + "_end"] = outcome["end"]
            for tolerance in TOLERANCES:
                if tolerance not in machine[arm]:
                    continue
                at = _machine_verdict(machine[arm][tolerance], index, outcome["contract"])
                loosened = dict(verdict, contract="RIGHT") if at == "RIGHT" else verdict
                row[f"{arm}_{tolerance}"] = classify(expected, loosened)
        row["cost"] = {arm: results[index][arm]["cost"] for arm in ARMS}
        rows.append(row)
    paired = [row for row in rows if "UNDETERMINED" not in (row["pipeline"], row["baseline"])]
    report: dict[str, Any] = {"cases_scored": len(rows), "cases_paired": len(paired),
                              "undetermined": len(rows) - len(paired)}
    if paired:
        success = paired_comparison([row["pipeline"] == "SUCCESS" for row in paired],
                                    [row["baseline"] == "SUCCESS" for row in paired])
        wrong = paired_comparison([row["pipeline"] == "WRONG_DELIVERY" for row in paired],
                                  [row["baseline"] == "WRONG_DELIVERY" for row in paired])
        report["rq3_success"] = {**success, "conclusion": conclusion(success)}
        # Lower is better here: a positive delta means the pipeline delivers wrong contracts more.
        report["rq3_wrong_delivery"] = wrong
    report["outcomes"] = {arm: {kind: sum(1 for row in rows if row[arm] == kind) for kind in OUTCOMES}
                          for arm in ARMS}
    report["time_sensitivity"] = {
        tolerance: {arm: sum(1 for row in rows if row.get(f"{arm}_{tolerance}") == "SUCCESS")
                    for arm in ARMS}
        for tolerance in TOLERANCES if all(tolerance in machine[arm] for arm in ARMS)}
    report["rq4"] = {}
    for arm in ARMS:
        per_case = {field: [row["cost"][arm][field] for row in rows] for field in COST_FIELDS}
        wins = report["outcomes"][arm]["SUCCESS"]
        report["rq4"][arm] = {
            "total": {field: round(sum(values), 1) for field, values in per_case.items()},
            "median": {field: _median(values) for field, values in per_case.items()},
            "requests_per_success": (sum(per_case["requests"]) / wins) if wins else None}
    report["rq4"]["baseline"]["cap_reached"] = sum(1 for row in rows
                                                   if row["cost"]["baseline"].get("cap_reached"))
    for field in ("expected_behavior", "family", "language", "info_mode"):
        report[f"success_by_{field}"] = _group_rates(paired, field)
    report["simuser"] = {"pipeline": simuser_report(pipeline_dir, sorted(results)),
                         "baseline": simuser_report(baseline_dir, sorted(results))}
    report["rows"] = rows
    return report


def main() -> int:
    if os.name == "nt":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="E7 blind adjudication packets and RQ3/RQ4 report")
    parser.add_argument("command", choices=["packets", "score"])
    parser.add_argument("--machine", type=Path, required=True, help="folder of e7_score outputs")
    parser.add_argument("--out", type=Path, required=True, help="folder for packets and the report")
    parser.add_argument("--verdicts", type=Path)
    parser.add_argument("--pipeline-dir", type=Path, default=PIPELINE_DIR)
    parser.add_argument("--baseline-dir", type=Path, default=BASELINE_DIR)
    args = parser.parse_args()
    cases = load_cases()
    results = collect(cases, args.pipeline_dir, args.baseline_dir)
    machine = load_machine(args.machine)
    if args.command == "packets":
        count = write_packets(results, cases, machine, args.out)
        print(f"{count} packets for the adjudicator in {args.out}")
        return 0
    if args.verdicts is None:
        parser.error("score needs --verdicts")
    report = score(results, cases, machine, _json(args.verdicts), _json(args.out / "blind-key.json"),
                   args.pipeline_dir, args.baseline_dir)
    (args.out / "e7-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n",
                                             encoding="utf-8")
    print(json.dumps({field: report[field] for field in
                      ("cases_paired", "outcomes", "rq3_success", "time_sensitivity")
                      if field in report}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
