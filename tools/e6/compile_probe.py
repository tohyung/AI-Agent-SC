"""Harness probe: one compile call for a case's accepted intent, to tell an outage from a case."""
import glob, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from research.adapters.model_transport import ModelTransport
from research.orchestration.artifacts import ArtifactEnvelope
from research.orchestration.ports import StepContext
from research.orchestration.status import AuthorityLevel, ImplementationStatus
from research.synthesis.llm_generator import LLMContractGeneratorPort
case = int(sys.argv[1])
for path in sorted(glob.glob(f"runs/E6-*/**/case-{case:03d}/attempt-*.json", recursive=True) + glob.glob(f"runs/E6-Discarded/**/pipeline-case-{case:03d}/attempt-*.json", recursive=True), reverse=True):
    record = json.load(open(path, encoding="utf-8"))
    art = next((a for a in record.get("artifacts", {}).values()
                if a.get("artifact_type") == "accepted-intent"), None)
    if art:
        break
env = ArtifactEnvelope("accepted-intent", art["schema_version"], "intent_acceptance",
                       ImplementationStatus.IMPLEMENTED_UNVALIDATED,
                       AuthorityLevel(art["authority_level"]), art["payload"])
model = ModelTransport(api_style="chat", max_tokens=16000, disable_reasoning=True,
                       retry_empty=False, request_json_object=False, provider="gemini")
out = LLMContractGeneratorPort(model).execute([env], StepContext("probe", {"allow_simulated_intent": True}))
print(out.result.run_status.value, out.result.semantic_status,
      [(e.get("exception_type"), e.get("seconds")) for e in model.call_log])
