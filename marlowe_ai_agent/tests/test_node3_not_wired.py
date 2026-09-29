from __future__ import annotations

import ast
from pathlib import Path


PACKAGE = Path(__file__).resolve().parents[1] / "marlowe_agent"
PRODUCTION_FILES = ("nodes.py", "openai_reasoner.py", "models.py", "cli.py")
FORBIDDEN = {"node3_policy", "node3_renderer", "marlowe_agent.node3_policy", "marlowe_agent.node3_renderer"}


def test_node3_prototype_is_not_imported_by_existing_pipeline() -> None:
    violations: list[str] = []
    for filename in PRODUCTION_FILES:
        path = PACKAGE / filename
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                modules = {base, *(f"{base}.{alias.name}" for alias in node.names)}
            else:
                continue
            if any(module in FORBIDDEN or module.endswith((".node3_policy", ".node3_renderer"))
                   for module in modules):
                violations.append(f"{filename}:{node.lineno}")
    assert violations == []
