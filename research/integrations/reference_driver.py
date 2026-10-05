"""Load the pinned reference wrapper without the ambiguous `tools` namespace."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
from typing import Any


_PATH = Path(__file__).resolve().parents[2] / "tools" / "marlowe_smt" / "run_reference.py"
_SPEC = importlib.util.spec_from_file_location("research_pinned_reference_driver", _PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError("pinned reference wrapper unavailable")
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def execute(request: dict[str, Any], *, binary: str | None = None,
            hard_timeout_seconds: float = 30.0) -> dict[str, Any]:
    if os.name == "nt":
        from research.integrations.wsl_driver import run_wrapper
        try:
            return run_wrapper("run_reference.py", request, hard_timeout_seconds, binary)
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
            return {"status": "Unavailable", "meta": {}, "steps": [],
                    "detail": {"reason": f"reference bridge unavailable: {type(exc).__name__}"}}
    return _MODULE.execute(request, binary=binary,
                           hard_timeout_seconds=hard_timeout_seconds)
