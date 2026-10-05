"""Compatibility alias for archived pipeline consumers."""

import sys
from research.legacy import nodes

sys.modules[__name__] = nodes
