"""Compatibility alias for archived pipeline consumers."""

import sys
from research.legacy import openai_reasoner

sys.modules[__name__] = openai_reasoner
