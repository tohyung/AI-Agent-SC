"""Compatibility alias for archived pipeline consumers."""

import sys
from research.legacy import node3_smt

sys.modules[__name__] = node3_smt
