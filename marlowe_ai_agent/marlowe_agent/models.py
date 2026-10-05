"""Compatibility alias for archived pipeline consumers."""

import sys
from research.legacy import models

sys.modules[__name__] = models
