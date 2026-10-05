"""Windows-only bridge to checked-in Linux reference/SMT wrappers."""

from __future__ import annotations

import json
from pathlib import Path
import shlex
import subprocess
from typing import Any


def run_wrapper(name: str, payload: Any, timeout: float,
                binary: str | None = None) -> dict[str, Any]:
    if name not in {"run_smt.py", "run_reference.py"}:
        raise ValueError("unsupported pinned driver")
    wrapper = Path(__file__).resolve().parents[2] / "tools" / "marlowe_smt" / name
    drive = wrapper.drive
    if len(drive) != 2 or drive[1] != ":":
        raise ValueError("WSL bridge requires a Windows drive-backed checkout")
    linux_file = f"/mnt/{drive[0].lower()}{wrapper.as_posix()[2:]}"
    command = ["python3", linux_file, "--hard-timeout", str(timeout)]
    if binary is not None:
        if not binary.startswith("/") or "\n" in binary:
            raise ValueError("WSL driver binary must use an absolute Linux path")
        command.extend(["--binary", binary])
    shell_command = " ".join(shlex.quote(part) for part in command)
    process = subprocess.run(
        ["wsl", "bash", "-lc", shell_command],
        input=json.dumps(payload, ensure_ascii=False), text=True,
        capture_output=True, check=False, timeout=timeout + 10,
    )
    result = json.loads(process.stdout)
    if not isinstance(result, dict):
        raise ValueError("pinned driver returned non-object JSON")
    if process.returncode and result.get("status") not in {
            "Counterexample", "InvalidInput", "TransactionError", "Unsupported"}:
        raise RuntimeError("pinned driver exited unexpectedly")
    return result
