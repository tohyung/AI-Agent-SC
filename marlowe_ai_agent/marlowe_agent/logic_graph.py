from __future__ import annotations

from typing import Any

from .marlowe_ast import walk_contract
from .marlowe_validator import validate_contract
from .models import LogicGraphResult


class LogicGraphVerifier:
    def verify(self, contract: dict[str, Any]) -> LogicGraphResult:
        validation_errors = validate_contract(contract)
        if validation_errors:
            return LogicGraphResult(
                passed=False,
                findings=_unique_findings(["AST Marlowe khong hop le ve cau truc.", *validation_errors]),
                graph={"nodes": [], "edges": []},
            )

        graph = self._build_graph(contract)
        findings = _unique_findings(self._find_logic_issues(contract, graph))
        return LogicGraphResult(passed=not findings, findings=findings or ["Logic graph pass."], graph=graph)

    def _build_graph(self, contract: dict[str, Any]) -> dict[str, Any]:
        nodes = []
        edges = []

        def visit(node: dict[str, Any], node_id: str) -> None:
            nodes.append({"id": node_id, "type": self._node_type(node)})
            if "when" in node:
                for index, item in enumerate(node["when"]):
                    child_id = f"{node_id}.case[{index}]"
                    edges.append({"from": node_id, "to": child_id, "label": self._action_label(item["case"])})
                    visit(item["then"], child_id)
                timeout_id = f"{node_id}.timeout"
                edges.append({"from": node_id, "to": timeout_id, "label": f"timeout@{node['timeout']}"})
                visit(node["timeout_continuation"], timeout_id)
            elif "if" in node:
                then_id = f"{node_id}.then"
                else_id = f"{node_id}.else"
                edges.append({"from": node_id, "to": then_id, "label": "if true"})
                edges.append({"from": node_id, "to": else_id, "label": "if false"})
                visit(node["then"], then_id)
                visit(node["else"], else_id)
            elif "then" in node:
                child_id = f"{node_id}.then"
                edges.append({"from": node_id, "to": child_id, "label": "then"})
                visit(node["then"], child_id)

        visit(contract, "root")
        return {"nodes": nodes, "edges": edges}

    def _find_logic_issues(self, contract: dict[str, Any], graph: dict[str, Any]) -> list[str]:
        findings: list[str] = []
        visited_paths = walk_contract(contract)

        if not any(node.get("close") == "close" for _, node in visited_paths):
            findings.append("Hop dong khong co nhanh ket thuc Close.")

        when_nodes = [(path, node) for path, node in visited_paths if "when" in node]
        for path, node in when_nodes:
            labels = [self._action_label(item["case"]) for item in node["when"]]
            duplicates = sorted({label for label in labels if labels.count(label) > 1})
            if duplicates:
                findings.append(f"{path} co case trung lap: {', '.join(duplicates)}.")

            if len(node["when"]) == 0:
                findings.append(f"{path} la When rong, chi co timeout.")

            if node["timeout_continuation"] == node:
                findings.append(f"{path} timeout tao vong lap truc tiep.")

        pay_edges = [edge for edge in graph["edges"] if "Choice" in edge["label"]]
        choice_labels = [edge["label"] for edge in pay_edges]
        if len(choice_labels) != len(set(choice_labels)):
            findings.append("Cac nhanh choice co nhan trung nhau.")

        for path, node in visited_paths:
            if "pay" in node and node["pay"].get("constant", 0) <= 0:
                findings.append(f"{path} co Pay voi so tien <= 0.")

        return findings

    def _node_type(self, node: dict[str, Any]) -> str:
        if "when" in node:
            return "When"
        if "pay" in node:
            return "Pay"
        if "close" in node:
            return "Close"
        if "if" in node:
            return "If"
        if "let" in node:
            return "Let"
        if "assert" in node:
            return "Assert"
        return "Unknown"

    def _action_label(self, action: dict[str, Any]) -> str:
        if "deposits" in action:
            party = action["party"].get("role_token", "?")
            amount = action["deposits"].get("constant", "?")
            return f"Deposit({party},{amount})"
        if "choice" in action:
            choice = action["choice"]
            owner = choice["choice_owner"].get("role_token", "?")
            bounds = action.get("bounds", [])
            bound_text = ",".join(f"{item['from']}..{item['to']}" for item in bounds)
            return f"Choice({choice['choice_name']},{owner},{bound_text})"
        if "notify_if" in action:
            return "Notify"
        return "Action"


def _unique_findings(findings: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for finding in findings:
        text = finding.strip()
        key = " ".join(text.split()).casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result
