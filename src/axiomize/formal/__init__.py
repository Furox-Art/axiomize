"""Formal/Lean verification adapters (GAP-2 skeleton).

GAP-2 henuz gercek bir Lean kurulumuna baglanmaz; bu paket yalnizca
:mod:`axiomize.tools.base.ScientificTool` sozlesmesine uyan durust bir
iskelet sunar. Gercek Lean baglantisi eklenene kadar adapter her zaman
``TOOL_UNAVAILABLE`` bildirir ve asla sahte ispat uretmez.
"""

from axiomize.formal.lean_adapter import LeanAdapter

__all__ = ["LeanAdapter"]
