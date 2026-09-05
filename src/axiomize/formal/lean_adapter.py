"""Lean adapter for formal verification.

Lean elaboration executes a local compiler/runtime and is therefore **not** a
security sandbox for hostile theorem text. The adapter refuses elaboration
unless the caller explicitly opts into trusted local execution. It additionally
uses a temporary HOME, a minimal environment, bounded input/output and a timeout.
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, ClassVar

from axiomize.tools.base import ScientificTool, ToolMetadata
from axiomize.validation.status import ValidationStatus

_MAX_THEOREM_BYTES = 2 * 1024 * 1024
_MAX_LEAN_OUTPUT_BYTES = 64 * 1024


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
        cmd = cls._lean_cmd()
        if cmd is None:
            return ToolMetadata(name=cls.name, capabilities=list(cls.capabilities), available=False, reason="elan not found on PATH")
        try:
            proc = subprocess.run([*cmd, "--version"], capture_output=True, text=True, timeout=60, shell=False, check=False)
        except (OSError, subprocess.SubprocessError) as exc:
            return ToolMetadata(name=cls.name, capabilities=list(cls.capabilities), available=False, reason=f"lean probe failed: {exc}")
        if proc.returncode != 0:
            return ToolMetadata(name=cls.name, capabilities=list(cls.capabilities), available=False,
                                reason=f"toolchain {cls.TOOLCHAIN} unavailable: {proc.stderr.strip()[:200]}")
        return ToolMetadata(name=cls.name, capabilities=list(cls.capabilities), version=proc.stdout.strip() or "unknown", available=True)

    @classmethod
    def _probe_version(cls) -> str:
        meta = cls.availability()
        if not meta.available:
            raise RuntimeError(meta.reason or "lean unavailable")
        return meta.version

    def validate_input(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            raise ValueError("lean: payload must be a dict")
        theorem = payload.get("theorem")
        if not isinstance(theorem, str) or not theorem.strip():
            raise ValueError("lean: payload needs a non-empty 'theorem' string")
        if len(theorem.encode("utf-8")) > _MAX_THEOREM_BYTES:
            raise ValueError(f"lean theorem exceeds hard limit of {_MAX_THEOREM_BYTES} bytes")
        timeout = float(payload.get("timeout_s", self.TIMEOUT_S))
        if not math.isfinite(timeout) or timeout <= 0 or timeout > 600:
            raise ValueError("lean timeout_s must be finite and in (0, 600]")

    @staticmethod
    def _minimal_env(home: str) -> dict[str, str]:
        allowed = {"PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "LANG", "LC_ALL", "LC_CTYPE", "TZ"}
        env = {key: value for key, value in os.environ.items() if key in allowed}
        env.update({"HOME": home, "USERPROFILE": home, "TMPDIR": home, "TEMP": home, "TMP": home})
        return env

    def execute(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Elaborate trusted theorem text with the real local Lean toolchain."""
        self.validate_input(payload)
        theorem = str(payload["theorem"])
        if not bool(payload.get("allow_unsafe_execution", False)):
            result = {
                "status": ValidationStatus.INCONCLUSIVE.value,
                "theorem": theorem,
                "proved": False,
                "proof": None,
                "reason": "Lean elaboration executes trusted local code and is disabled by default; retry with allow_unsafe_execution=true only for trusted theorem text",
            }
            self.validate_output(result)
            return result

        meta = self.availability()
        if not meta.available:
            result = {"status": ValidationStatus.TOOL_UNAVAILABLE.value, "theorem": theorem, "proved": False,
                      "proof": None, "reason": meta.reason or "lean toolchain unavailable"}
            self.validate_output(result)
            return result

        timeout = float(payload.get("timeout_s", self.TIMEOUT_S))
        cmd = self._lean_cmd(); assert cmd is not None
        start = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="axiomize-lean-") as tmp:
            lean_file = Path(tmp) / "check.lean"
            lean_file.write_text(theorem.strip() + "\n", encoding="utf-8")
            try:
                proc = subprocess.run([*cmd, str(lean_file)], capture_output=True, text=True, errors="replace",
                                      timeout=timeout, shell=False, cwd=tmp, env=self._minimal_env(tmp), check=False)
            except subprocess.TimeoutExpired:
                result = {"status": ValidationStatus.INCONCLUSIVE.value, "theorem": theorem, "proved": False,
                          "proof": None, "reason": f"lean did not finish within {timeout:g}s",
                          "toolchain": self.TOOLCHAIN, "elapsed_s": round(time.monotonic() - start, 3)}
                self.validate_output(result)
                return result
        elapsed = round(time.monotonic() - start, 3)
        lean_output = (proc.stdout + proc.stderr).strip()[:_MAX_LEAN_OUTPUT_BYTES]
        if proc.returncode == 0:
            result = {"status": ValidationStatus.PASS.value, "theorem": theorem, "proved": True, "proof": theorem,
                      "reason": "lean elaborated the file with no errors", "toolchain": self.TOOLCHAIN, "elapsed_s": elapsed}
        else:
            result = {"status": ValidationStatus.FAIL.value, "theorem": theorem, "proved": False, "proof": None,
                      "reason": "lean rejected the statement", "lean_output": lean_output,
                      "toolchain": self.TOOLCHAIN, "elapsed_s": elapsed}
        self.validate_output(result)
        return result
