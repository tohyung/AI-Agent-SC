from __future__ import annotations

from conftest import FakeSMTBackend, make_draft

from marlowe_agent.nodes import AgentPipeline, Node3VerificationNode
from tools.fake_reasoner import FakeReasoner


def test_live_pipeline_uses_lint_and_smt_not_full_legacy_verifier(monkeypatch) -> None:
    backend = FakeSMTBackend(["valid"])
    pipeline = AgentPipeline(FakeReasoner([make_draft()]), node3_backend=backend)
    assert isinstance(pipeline.node_3, Node3VerificationNode)

    def legacy_is_not_live(*_args, **_kwargs):
        raise AssertionError("full LogicGraphVerifier.verify must not run in live Node 3")

    monkeypatch.setattr(pipeline.node_3.verifier, "verify", legacy_is_not_live)
    result = pipeline.run("escrow")
    assert result.status == "done"
    assert backend.call_count == 1
    assert any(event.node == "node_3_logic_graph_verification" and event.status == "pass"
               for event in result.trace)
