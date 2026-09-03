"""Shared validation status vocabulary (PHASE 1 core)."""

from enum import Enum


class ValidationStatus(str, Enum):
    """Outcome of any single validation or availability check."""

    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"
    CONFLICT = "CONFLICT"
    INCONCLUSIVE = "INCONCLUSIVE"
    TOOL_UNAVAILABLE = "TOOL_UNAVAILABLE"
    UNVERIFIED = "UNVERIFIED"
