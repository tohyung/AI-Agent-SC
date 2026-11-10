"""E5 runner: build candidate sets, label them, run the gate ladder, one JSON per candidate.

Run inside WSL so the pinned binaries are called directly (about 20x faster than the bridge):
    python -m research.experiments.gate_eval --set mutants --cases 1-56 --out runs/e5/dev-M
    python -m research.experiments.gate_eval --set real --cases 1-56 --out runs/e5/dev-R
Existing outputs are kept, so an interrupted run resumes.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from research.experiments.gate_labels import label
from research.experiments.gate_mutants import variants
from research.experiments.gate_policy import EMPTY_STATE, Expectation, evaluate
from research.experiments.run_bundles import iter_cases
from research.synthesis.reference import PinnedMarloweReference, ReferenceRequest

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "dataset/cases.jsonl"
EXCLUDED = {57}
E3_DIRS = (ROOT / "runs/roleplay-main-batch20", ROOT / "runs/roleplay-main-batch80",
           ROOT / "runs/E3-Roleplay-Holdout")
DATASET_REVIEWER = "E5-dataset-checks"
E3_REVIEWER = "E3-roleplay-simulated-user"


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    case_index: int
    source: str  # "mutant" or "E3"
    operator: str
    intent: str
    contract: Any
    is_final: bool | None = None
    accepted: tuple[dict[str, Any], list[dict[str, Any]]] | None = None  # (accepted spec, mapping)


def cases() -> list[dict[str, Any]]:
    return [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines()]


def parse_range(text: str) -> list[int]:
    found: list[int] = []
    for part in text.split(","):
        low, _, high = part.partition("-")
        found += range(int(low), int(high or low) + 1)
    return [index for index in found if index not in EXCLUDED]


def mutant_candidates(case: dict[str, Any], index: int) -> list[Candidate]:
    return [Candidate(f"case-{index:02d}-{v.operator}-{v.site}", index, "mutant", v.operator,
                      v.intent, v.contract) for v in variants(case["reference_contract"])]


def _candidates_in(value: Any, found: list[dict[str, Any]]) -> None:
    if isinstance(value, dict):
        if value.get("artifact_type") == "contract-candidate":
            found.append(value)
        for item in value.values():
            _candidates_in(item, found)
    elif isinstance(value, list):
        for item in value:
            _candidates_in(item, found)


@lru_cache(maxsize=None)
def e3_case_files(index: int) -> dict[str, str]:
    for directory in E3_DIRS:
        if not directory.exists():
            continue
        for name, files in iter_cases(directory):
            if name == f"case-{index:02d}":
                return files
    return {}


def e3_intent(index: int, content_hash: str) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    """The accepted IntentSpec and mapping evidence the E3 pipeline had for this contract."""
    found = None
    for name, text in sorted(e3_case_files(index).items()):
        if not name.startswith("attempt") or content_hash not in text:
            continue
        try:
            artifacts = json.loads(text).get("artifacts")
        except json.JSONDecodeError:
            continue
        if not isinstance(artifacts, dict):
            continue
        for key, artifact in artifacts.items():
            if key.startswith("contract-candidate:") and key.endswith(content_hash):
                payload = artifact.get("payload", {})
                accepted = artifacts.get(payload.get("source_intent_id"), {})
                spec = accepted.get("payload", {}).get("accepted_spec")
                if isinstance(spec, dict):
                    found = (spec, payload.get("mapping_evidence") or [])
    return found


def real_candidates(index: int) -> list[Candidate]:
    """Every distinct model-generated contract of a case, in attempt order; the last is final."""
    ordered: dict[str, Any] = {}
    files = e3_case_files(index)
    for name in sorted(files):
        text = files[name]
        if "contract-candidate" not in text:
            continue
        try:
            found: list[dict[str, Any]] = []
            _candidates_in(json.loads(text), found)
        except json.JSONDecodeError:
            continue
        for artifact in found:
            if artifact["payload"].get("generation_mode"):
                ordered.pop(artifact["content_hash"], None)
                ordered[artifact["content_hash"]] = artifact["payload"]["contract"]
    hashes = list(ordered)
    return [Candidate(f"case-{index:02d}-E3-{digest[:12]}", index, "E3", "model", "unknown",
                      ordered[digest], is_final=(position == len(hashes) - 1),
                      accepted=e3_intent(index, digest))
            for position, digest in enumerate(hashes)]


def _deposit_account(contract: Any, party: str, amount: int) -> dict[str, Any]:
    stack = [contract]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if (node.get("deposits") == amount and isinstance(node.get("party"), dict)
                    and node["party"].get("role_token") == party):
                return node["into_account"]
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return {"role_token": party}


DAY_MS = 86_400_000


def scenario_time(label: str, dates: list[int]) -> int:
    """When a reviewed step happens. E5-Round2: one day before or after a deadline, the same
    tolerance as the label oracle (prompts give dates, not times); Round 1 used one second,
    as `dataset/evaluator.py` does."""
    if not dates:
        raise ValueError("no_timeouts")
    if label == "before_t1":
        return dates[0] - DAY_MS
    if label == "after_t1_before_t2" and len(dates) >= 2:
        return (dates[0] + dates[1]) // 2
    if label == "after_t2_before_t3" and len(dates) >= 3:
        return (dates[1] + dates[2]) // 2
    if label == "after_all":
        return dates[-1] + DAY_MS
    raise ValueError(f"missing_timepoint:{label}")


def dataset_expectations(case: dict[str, Any], executor: Any) -> list[Expectation]:
    """The case's check scenarios, with expected behaviour taken from the reference contract."""
    from research.experiments.gate_labels import deadlines
    reference = case["reference_contract"]
    dates = deadlines(reference)
    found = []
    for scenario in case["checks"].get("scenarios", []):
        transactions = []
        try:
            for step in scenario["steps"]:
                at = scenario_time(step["at"], dates)
                if step["kind"] == "deposit":
                    token = {"currency_symbol": "", "token_name": step.get("token", "")}
                    inputs = [{"type": "Deposit", "party": {"role_token": step["party"]},
                               "account": _deposit_account(reference, step["party"], step["amount"]),
                               "token": token, "amount": step["amount"]}]
                elif step["kind"] == "choice":
                    inputs = [{"type": "Choice", "choice_id": {
                        "choice_name": step["name"], "choice_owner": {"role_token": step["party"]}},
                        "chosen": step["value"]}]
                else:
                    inputs = []
                transactions.append({"interval": {"from": at, "to": at}, "inputs": inputs})
        except ValueError:
            continue
        observed = executor.execute(ReferenceRequest(reference, dict(EMPTY_STATE),
                                                     tuple(transactions)))
        status = observed.get("status")
        if status not in {"Success", "TransactionError"}:
            continue
        payments = [item for step in observed.get("steps", []) if step.get("status") == "Success"
                    for item in step.get("payments", [])]
        payload = {"request": {"state": dict(EMPTY_STATE), "transactions": transactions},
                   "expected_status": status, "expected_payments": payments,
                   "expected_warnings": []}
        if observed.get("final_contract") == "close":
            payload["expected_final_contract"] = "close"
        found.append(Expectation(scenario["name"], DATASET_REVIEWER, payload))
    return found


def e3_expectations(index: int) -> list[Expectation]:
    files = e3_case_files(index)
    found = []
    for name in sorted(files):
        if name.startswith("behavior-expectation") and name.endswith(".json"):
            payload = json.loads(files[name])
            keep = {key: payload[key] for key in ("request", "expected_status",
                                                  "expected_final_contract", "expected_warnings",
                                                  "expected_payments", "expected_final_state")
                    if key in payload}
            found.append(Expectation(name, E3_REVIEWER, keep))
    return found


def run(selection: str, indices: list[int], out_dir: Path, *, expectations_from: str) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    executor = PinnedMarloweReference(binary=os.getenv("MARLOWE_REFERENCE_BINARY"))
    smt_binary = os.getenv("MARLOWE_SMT_BIN")
    data = cases()
    written = 0
    for index in indices:
        case = data[index - 1]
        pool = mutant_candidates(case, index) if selection == "mutants" else real_candidates(index)
        if not pool:
            continue
        expectations = (dataset_expectations(case, executor) if expectations_from == "dataset"
                        else e3_expectations(index))
        for candidate in pool:
            target = out_dir / f"{candidate.candidate_id}.json"
            if target.exists():
                continue
            truth = label(candidate.contract, case["reference_contract"])
            result = evaluate(candidate.contract, expectations, executor=executor,
                              smt_binary=smt_binary, intent=candidate.accepted)
            record = {"candidate_id": candidate.candidate_id, "case_index": index,
                      "case_type": case["type"], "info_mode": case["info_mode"],
                      "source": candidate.source, "operator": candidate.operator,
                      "operator_intent": candidate.intent, "is_final": candidate.is_final,
                      "contract_sha256": hashlib.sha256(json.dumps(
                          candidate.contract, sort_keys=True).encode()).hexdigest(),
                      "expectations_from": expectations_from,
                      "expectations": [item.name for item in expectations],
                      "label": truth, **result}
            target.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
            written += 1
        print(f"case {index}: {len(pool)} candidates", flush=True)
    print(f"wrote {written}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--set", choices=["mutants", "real"], required=True)
    parser.add_argument("--cases", default="1-56")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--expectations", choices=["dataset", "e3"],
                        help="reviewed scenarios: dataset checks (default for mutants) or the "
                             "E3 behaviour-expectation files (default for real)")
    args = parser.parse_args()
    source = args.expectations or ("dataset" if args.set == "mutants" else "e3")
    return run(args.set, parse_range(args.cases), args.out, expectations_from=source)


if __name__ == "__main__":
    raise SystemExit(main())
