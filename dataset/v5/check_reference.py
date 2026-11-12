"""Check dataset v5 references on the pinned binaries (C-8; run inside WSL):

    E5_FULL=dataset.v5.check_reference bash runs/e5/run_wsl.sh

The same check as dataset.v3.check_reference: SMT Valid, and every scenario runs on the pinned
Haskell reference executor with the expected payouts, no warnings, and Close where expected.
"""

from __future__ import annotations

from pathlib import Path
import sys

import dataset.v3.check_reference as v3_check

v3_check.CASES = Path(__file__).resolve().parent / "cases.jsonl"

if __name__ == "__main__":
    sys.exit(v3_check.main())
