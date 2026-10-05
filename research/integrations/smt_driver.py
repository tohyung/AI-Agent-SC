"""Load the checked-in SMT subprocess wrapper without the ambiguous `tools` namespace."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any


_PATH = Path(__file__).resolve().parents[2] / "tools" / "marlowe_smt" / "run_smt.py"
_SPEC = importlib.util.spec_from_file_location("research_pinned_smt_driver", _PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError("pinned SMT wrapper unavailable")
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

UPSTREAM_COMMIT: str = _MODULE.UPSTREAM_COMMIT
DRIVER_VERSION: str = _MODULE.DRIVER_VERSION


def analyze(contract: Any, *, binary: str | None = None) -> dict[str, Any]:
    if os.name == "nt":
        from research.integrations.wsl_driver import run_wrapper
        return run_wrapper("run_smt.py", contract, 90.0, binary)
    return _MODULE.analyze(contract, binary=binary)
