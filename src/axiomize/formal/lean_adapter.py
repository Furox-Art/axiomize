"""Lean adapter skeleton for formal verification (GAP-2).

Bu iskelet :class:`axiomize.tools.base.ScientificTool` arayuzune uyar
ancak bilerek henuz hicbir Lean arac zincirine baglanmaz. ``availability``
her zaman ``available=False`` doner, ``execute`` ise her zaman
``TOOL_UNAVAILABLE`` durumlu bir dict doner; asla sahte ``PASS`` ya da
uydurma ispat uretilmez.
"""

from __future__ import annotations

from typing import Any, ClassVar

from axiomize.tools.base import ScientificTool, ToolMetadata
from axiomize.validation.status import ValidationStatus


class LeanAdapter(ScientificTool):
    """Lean teorem ispatlayicisi icin durust iskelet adapter."""

    name: ClassVar[str] = "lean"
    capabilities: ClassVar[list[str]] = ["formal_verification", "theorem_proving"]

    @classmethod
    def availability(cls) -> ToolMetadata:
        """Lean henuz bagli degil: her zaman kullanilamaz bildir."""
        return ToolMetadata(
            name=cls.name,
            capabilities=list(cls.capabilities),
            available=False,
            reason="lean toolchain not wired yet (GAP-2 skeleton); no fake proofs",
        )

    @classmethod
    def _probe_version(cls) -> str:
        raise RuntimeError("lean toolchain not wired yet (GAP-2 skeleton)")

    def validate_input(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            raise ValueError("lean: payload must be a dict")  # noqa: TRY004 - base.py sozlesmesi validate_input icin ValueError ister
        if "theorem" not in payload:
            raise ValueError("lean: payload needs a 'theorem' statement")
        if not isinstance(payload["theorem"], str) or not payload["theorem"].strip():
            raise ValueError("lean: 'theorem' must be a non-empty string")

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Dogrulama yapma; durustce TOOL_UNAVAILABLE don."""
        self.validate_input(payload)
        result = {
            "status": ValidationStatus.TOOL_UNAVAILABLE.value,
            "theorem": payload.get("theorem"),
            "proved": False,
            "proof": None,
            "reason": "lean toolchain not wired yet (GAP-2 skeleton); no fake proofs",
        }
        self.validate_output(result)
        return result
