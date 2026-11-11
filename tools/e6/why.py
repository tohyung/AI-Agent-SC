"""Harness diagnosis of a pipeline case that stopped at the Scenario gate (not shown to the user):
the comparison diagnostics and the choice actions (owner, bounds) of the generated contract."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.synthesis.scenario_binding import _choice_actions  # noqa: E402
case_dir = ROOT / "runs" / "E6-Pipeline" / f"case-{int(sys.argv[1]):03d}"
record = json.loads(sorted(case_dir.glob("attempt-*.json"))[-1].read_text(encoding="utf-8"))
print(record["steps"].get("semantic_comparison", {}).get("diagnostics", [])[:4])
ids = record["steps"]["compile"]["output_artifacts"]
contract = record["artifacts"][ids[0]]["payload"]["contract"]
for action in _choice_actions(contract):
    print(json.dumps(action, ensure_ascii=False))
