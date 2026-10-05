"""Compatibility alias for archived pipeline consumers."""

import sys
from research.marlowe_core import logic_graph

sys.modules[__name__] = logic_graph
