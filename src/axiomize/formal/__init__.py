"""Formal/Lean verification adapters (GAP-2, real integration).

:mod:`axiomize.formal.lean_adapter` checks proofs with a real, pinned
Lean toolchain through ``elan run``. When the toolchain is missing the
adapter reports ``TOOL_UNAVAILABLE`` and never fakes a proof.
"""

from axiomize.formal.lean_adapter import LeanAdapter

__all__ = ["LeanAdapter"]
