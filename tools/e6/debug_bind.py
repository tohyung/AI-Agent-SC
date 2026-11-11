"""Harness debug: run the scenario prefix on the reference executor and show the continuation."""
import json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research.synthesis.reference import PinnedMarloweReference, ReferenceRequest
case = int(sys.argv[1]); name = sys.argv[2]
d = Path(__file__).resolve().parents[2] / "runs" / "E6-Pipeline" / f"case-{case:03d}"
rec = json.loads(sorted(d.glob("attempt-*.json"))[-1].read_text(encoding="utf-8"))
contract = rec["artifacts"][rec["steps"]["compile"]["output_artifacts"][0]]["payload"]["contract"]
exp = json.loads((d / f"scenario-{name}.json").read_text(encoding="utf-8"))
ref = PinnedMarloweReference(binary=os.environ["MARLOWE_REFERENCE_BINARY"], hard_timeout_seconds=15)
txs = exp["request"]["transactions"]
for k in range(1, len(txs)):
    out = ref.execute(ReferenceRequest(contract, exp["request"]["state"], tuple(txs[:k])))
    fc = out.get("final_contract")
    print(k, out.get("status"), list(fc)[:4] if isinstance(fc, dict) else fc)
