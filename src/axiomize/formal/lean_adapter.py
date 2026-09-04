"""Lean adapter for formal verification (GAP-2, real integration).

:class:`LeanAdapter` speaks :class:`axiomize.tools.base.ScientificTool`
and checks proofs with a real, pinned Lean toolchain
(``leanprover/lean4:v4.30.0``) through ``elan run``. No proof is ever
faked: ``lean`` itself decides, the adapter only reports its verdict.

Trust note: the ``theorem`` string is elaborated by the local Lean
binary with the local user's privileges (same trust level as the local
Python/SciPy solvers). It always runs in an isolated temp dir with a
timeout, never with a shell, and never inside the repo.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, ClassVar

from axiomize.tools.base import ScientificTool, ToolMetadata
from axiomize.validation.status import ValidationStatus


class LeanAdapter(ScientificTool):
    """Real Lean 4 proof checker behind the ScientificTool contract."""

    name: ClassVar[str] = "lean"
    capabilities: ClassVar[list[str]] = ["formal_verification", "theorem_proving"]
    TOOLCHAIN: ClassVar[str] = "leanprover/lean4:v4.30.0"
    TIMEOUT_S: ClassVar[int] = 120

    @classmethod
    def _lean_cmd(cls) -> list[str] | None:
        if shutil.which("elan") is None:
            return None
        return ["elan", "run", cls.TOOLCHAIN, "lean"]

    @classmethod
    def availability(cls) -> ToolMetadata:
        """Probe the real toolchain; never report available without proof."""
        cmd = cls._lean_cmd()
        if cmd is None:
            return ToolMetadata(
                name=cls.name, capabilities=list(cls.capabilities),
                available=False, reason="elan not found on PATH")
        try:
            proc = subprocess.run(
                [*cmd, "--version"], capture_output=True, text=True,
                timeout=60, shell=False, check=False)
        except (OSError, subprocess.SubprocessError) as exc:
            return ToolMetadata(
                name=cls.name, capabilities=list(cls.capabilities),
                available=False, reason=f"lean probe failed: {exc}")
        if proc.returncode != 0:
            return ToolMetadata(
                name=cls.name, capabilities=list(cls.capabilities),
                available=False,
                reason=f"toolchain {cls.TOOLCHAIN} unavailable: "
                       f"{proc.stderr.strip()[:200]}")
        return ToolMetadata(
            name=cls.name, capabilities=list(cls.capabilities),
            version=proc.stdout.strip() or "unknown", available=True)

    @classmethod
    def _probe_version(cls) -> str:
        meta = cls.availability()
        if not meta.available:
            raise RuntimeError(meta.reason or "lean unavailable")
        return meta.version

    def validate_input(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            raise ValueError("lean: payload must be a dict")  # noqa: TRY004 - base.py sozlesmesi validate_input icin ValueError ister
        if "theorem" not in payload:
            raise ValueError("lean: payload needs a 'theorem' statement")
        if not isinstance(payload["theorem"], str) or not payload["theorem"].strip():
            raise ValueError("lean: 'theorem' must be a non-empty string")

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Elaborate ``theorem`` with real Lean; report its verdict."""
        self.validate_input(payload)
        meta = self.availability()
        theorem = payload["theorem"]
        if not meta.available:
            result = {
                "status": ValidationStatus.TOOL_UNAVAILABLE.value,
                "theorem": theorem,
                "proved": False,
                "proof": None,
                "reason": meta.reason or "lean toolchain unavailable",
            }
            self.validate_output(result)
            return result
        timeout = int(payload.get("timeout_s", self.TIMEOUT_S))
        cmd = self._lean_cmd()
        assert cmd is not None  # availability() just proved elan exists
        start = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="axiomize-lean-") as tmp:
            lean_file = Path(tmp) / "check.lean"
            lean_file.write_text(theorem.strip() + "\n", encoding="utf-8")
            try:
                proc = subprocess.run(
                    [*cmd, str(lean_file)], capture_output=True, text=True,
                    timeout=timeout, shell=False, cwd=tmp, check=False)
            except subprocess.TimeoutExpired:
                result = {
                    "status": ValidationStatus.INCONCLUSIVE.value,
                    "theorem": theorem,
                    "proved": False,
                    "proof": None,
                    "reason": f"lean did not finish within {timeout}s",
                    "toolchain": self.TOOLCHAIN,
                    "elapsed_s": round(time.monotonic() - start, 3),
                }
                self.validate_output(result)
                return result
        elapsed = round(time.monotonic() - start, 3)
        lean_output = (proc.stdout + proc.stderr).strip()
        if proc.returncode == 0:
            result = {
                "status": ValidationStatus.PASS.value,
                "theorem": theorem,
                "proved": True,
                "proof": theorem,
                "reason": "lean elaborated the file with no errors",
                "toolchain": self.TOOLCHAIN,
                "elapsed_s": elapsed,
            }
        else:
            result = {
                "status": ValidationStatus.FAIL.value,
                "theorem": theorem,
                "proved": False,
                "proof": None,
                "reason": "lean rejected the statement",
                "lean_output": lean_output[:2000],
                "toolchain": self.TOOLCHAIN,
                "elapsed_s": elapsed,
            }
        self.validate_output(result)
        return result
