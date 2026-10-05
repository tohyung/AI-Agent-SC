"""Compatibility alias for archived pipeline consumers."""

import sys
from research.legacy import legacy_cli

sys.modules[__name__] = legacy_cli
