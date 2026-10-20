"""Round-2 coverage hardening for ``axiomize.formal.lean_adapter``.

Lean/elan are local optional toolchains. The tests replace ``shutil.which`` and
``subprocess.run`` at the adapter's import boundary so no compiler is executed,
then assert the real adapter contract: honest unavailability, the trust gate,
bounded timeouts, minimal child environment and PASS/FAIL/INCONCLUSIVE mapping.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from axiomize.formal import lean_adapter
from axiomize.formal.lean_adapter import LeanAdapter
from axiomize.validation.status import ValidationStatus

_THEOREM = "theorem cov100 : 2 + 2 = 4 := rfl"


def _fake_tools(monkeypatch: pytest.MonkeyPatch, run: object) -> None:
    monkeypatch.setattr(lean_adapter, "shutil", SimpleNamespace(which=lambda name: f"/fake/{name}"))
    monkeypatch.setattr(
        lean_adapter,
        "subprocess",
        SimpleNamespace(
            run=run,
            TimeoutExpired=subprocess.TimeoutExpired,
            SubprocessError=subprocess.SubprocessError,
        ),
    )


def _version_probe(command: list[str], **kwargs: object) -> SimpleNamespace:
    assert command[-1] == "--version"
    return SimpleNamespace(returncode=0, stdout="Lean (version 4.30.0, x86_64)\n", stderr="")


def test_missing_elan_reports_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lean_adapter, "shutil", SimpleNamespace(which=lambda name: None))
    assert LeanAdapter._lean_cmd() is None
    meta = LeanAdapter.availability()
    assert meta.available is False
    assert meta.reason == "elan not found on PATH"


def test_probe_spawn_failure_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_run(command: list[str], **kwargs: object) -> None:
        raise OSError("spawn failed")

    _fake_tools(monkeypatch, failing_run)
    meta = LeanAdapter.availability()
    assert meta.available is False
    assert "lean probe failed: spawn failed" in meta.reason


def test_probe_version_requires_and_returns_available_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_tools(monkeypatch, _version_probe)
    assert LeanAdapter._lean_cmd() == ["elan", "run", LeanAdapter.TOOLCHAIN, "lean"]
    assert LeanAdapter._probe_version() == "Lean (version 4.30.0, x86_64)"
    meta = LeanAdapter.availability()
    assert meta.available is True
    assert meta.version.startswith("Lean (version 4.30.0")

    monkeypatch.setattr(lean_adapter, "shutil", SimpleNamespace(which=lambda name: None))
    with pytest.raises(RuntimeError, match="elan not found on PATH"):
        LeanAdapter._probe_version()


def test_probe_nonzero_exit_reports_toolchain_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(returncode=1, stdout="", stderr="unknown toolchain\n" + "x" * 500)

    _fake_tools(monkeypatch, failing_run)
    meta = LeanAdapter.availability()
    assert meta.available is False
    assert meta.reason.startswith(f"toolchain {LeanAdapter.TOOLCHAIN} unavailable:")
    # The stderr excerpt is bounded so a noisy compiler cannot flood the reason.
    assert len(meta.reason) < 300


def test_unavailable_toolchain_yields_truthful_execution_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from axiomize.tools.base import ToolMetadata

    unavailable = ToolMetadata(name="lean", available=False, reason="elan not found on PATH")
    monkeypatch.setattr(LeanAdapter, "availability", classmethod(lambda cls: unavailable))
    result = LeanAdapter().execute({"theorem": _THEOREM, "allow_unsafe_execution": True})
    assert result["status"] == ValidationStatus.TOOL_UNAVAILABLE.value
    assert result["proved"] is False
    assert result["proof"] is None
    assert result["reason"] == "elan not found on PATH"


def test_validate_input_rejects_non_object_theorem_and_timeout() -> None:
    adapter = LeanAdapter()
    with pytest.raises(ValueError, match="payload must be a dict"):
        adapter.validate_input(["not", "a", "dict"])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="non-empty 'theorem'"):
        adapter.validate_input({"theorem": "   "})
    with pytest.raises(ValueError, match="exceeds hard limit"):
        adapter.validate_input({"theorem": "x" * (2 * 1024 * 1024 + 1)})
    with pytest.raises(ValueError, match="timeout_s must be finite"):
        adapter.validate_input({"theorem": "x", "timeout_s": float("nan")})
    with pytest.raises(ValueError, match="timeout_s must be finite"):
        adapter.validate_input({"theorem": "x", "timeout_s": 601})
    adapter.validate_input({"theorem": "x", "timeout_s": 5})


def test_minimal_env_allowlists_keys_and_overrides_home(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environ = {
        "PATH": "/usr/bin",
        "LANG": "C.UTF-8",
        "OPENAI_API_KEY": "secret",
        "PYTHONPATH": "/leak",
        "HOME": "/original",
    }
    monkeypatch.setattr(lean_adapter, "os", SimpleNamespace(environ=environ))
    env = LeanAdapter._minimal_env("/tmp/work")
    assert env["PATH"] == "/usr/bin"
    assert env["LANG"] == "C.UTF-8"
    assert "OPENAI_API_KEY" not in env
    assert "PYTHONPATH" not in env
    assert env["HOME"] == "/tmp/work"
    assert env["USERPROFILE"] == "/tmp/work"
    assert env["TMPDIR"] == "/tmp/work"
    assert env["TEMP"] == "/tmp/work"
    assert env["TMP"] == "/tmp/work"


def test_execute_proves_theorem_with_minimal_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def run(command: list[str], **kwargs: object) -> SimpleNamespace:
        if command[-1] == "--version":
            return _version_probe(command, **kwargs)
        lean_file = Path(command[-1])
        seen["command"] = list(command)
        seen["content"] = lean_file.read_text(encoding="utf-8")
        seen["cwd"] = kwargs.get("cwd")
        seen["env"] = kwargs.get("env")
        seen["timeout"] = kwargs.get("timeout")
        seen["shell"] = kwargs.get("shell")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    _fake_tools(monkeypatch, run)
    result = LeanAdapter().execute({"theorem": _THEOREM, "allow_unsafe_execution": True})
    assert result["status"] == ValidationStatus.PASS.value
    assert result["proved"] is True
    assert result["proof"] == _THEOREM
    assert result["toolchain"] == LeanAdapter.TOOLCHAIN
    assert isinstance(result["elapsed_s"], float)
    assert seen["command"][:4] == ["elan", "run", LeanAdapter.TOOLCHAIN, "lean"]
    assert seen["content"] == _THEOREM + "\n"
    cwd = str(seen["cwd"])
    assert str(seen["command"][-1]).startswith(cwd)
    env = seen["env"]
    assert isinstance(env, dict)
    assert env["HOME"] == cwd
    assert "PYTHONPATH" not in env
    assert seen["timeout"] == 120
    assert seen["shell"] is False


def test_execute_maps_rejection_to_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    def run(command: list[str], **kwargs: object) -> SimpleNamespace:
        if command[-1] == "--version":
            return _version_probe(command, **kwargs)
        return SimpleNamespace(returncode=1, stdout="", stderr="error: unknown identifier 'nope'")

    _fake_tools(monkeypatch, run)
    result = LeanAdapter().execute(
        {"theorem": _THEOREM, "allow_unsafe_execution": True, "timeout_s": 7}
    )
    assert result["status"] == ValidationStatus.FAIL.value
    assert result["proved"] is False
    assert result["proof"] is None
    assert "unknown identifier" in result["lean_output"]
    assert result["reason"] == "lean rejected the statement"


def test_execute_maps_timeout_to_inconclusive(monkeypatch: pytest.MonkeyPatch) -> None:
    def run(command: list[str], **kwargs: object) -> SimpleNamespace:
        if command[-1] == "--version":
            return _version_probe(command, **kwargs)
        raise subprocess.TimeoutExpired(command, float(kwargs["timeout"]))

    _fake_tools(monkeypatch, run)
    result = LeanAdapter().execute(
        {"theorem": _THEOREM, "allow_unsafe_execution": True, "timeout_s": 5}
    )
    assert result["status"] == ValidationStatus.INCONCLUSIVE.value
    assert result["proved"] is False
    assert result["proof"] is None
    assert result["reason"] == "lean did not finish within 5s"
    assert result["toolchain"] == LeanAdapter.TOOLCHAIN
    assert isinstance(result["elapsed_s"], float)


def test_execute_requires_explicit_trust_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def run(command: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append(list(command))
        return _version_probe(command, **kwargs)

    _fake_tools(monkeypatch, run)
    result = LeanAdapter().execute({"theorem": _THEOREM})
    assert result["status"] == ValidationStatus.INCONCLUSIVE.value
    assert result["proved"] is False
    assert "disabled by default" in result["reason"]
    # Only the availability probe ran; no theorem elaboration was attempted.
    assert len(calls) == 1
