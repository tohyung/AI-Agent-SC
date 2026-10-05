# Archived Node 1/2/3 pipeline

This directory preserves the historical draft/semantic/logic pipeline,
reasoner, SMT wrapper, and CLI for benchmark reproducibility. It is not an
entrypoint of `marlowe_ai_agent/main.py` and is not a fallback for the current
assurance pipeline. `marlowe_ai_agent/marlowe_agent/` contains compatibility
module aliases so older tests and research scripts continue to resolve imports.

Reusable AST validation, graph lint, warning rendering and counterexample
mapping were moved to `research/marlowe_core/`; both historical and current
code use those implementations. New runtime behavior belongs in the current
stage modules, not here.
