"""Verify explicit opt-in, isolated environment and bounded execution semantics."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from axiomize.execution import sandbox


@pytest.mark.parametrize("source", ["print(1)", "import os; print(os.environ)"])
def test_arbitrary_python_is_denied_by_default(source):
    with pytest.raises(sandbox.UnsafeExecutionDenied, match="disabled by default"):
        sandbox.run_python(source)


@pytest.mark.parametrize("value", [None, 15, {"code": "print(1)"}])
def test_untrusted_nonstring_code_is_refused(value):
    with pytest.raises(ValueError, match="code must be a string"):
        sandbox.run_python(value, allow_unsafe_code=True)


@pytest.mark.parametrize("seconds", [0.0, -1.0, float("nan"), float("inf"), 3601.0])
def test_timeout_has_finite_explicit_hard_bounds(seconds):
    with pytest.raises(ValueError, match="timeout_s must be finite"):
        sandbox.run_python("print(1)", timeout_s=seconds, allow_unsafe_code=True)


def test_oversized_code_cannot_reach_interpreter(monkeypatch):
    monkeypatch.setattr(sandbox, "_MAX_CODE_BYTES", 8)
    with pytest.raises(ValueError, match="code exceeds hard limit"):
        sandbox.run_python("print(12345)", allow_unsafe_code=True)


def test_seeded_child_receives_only_deliberate_inputs(monkeypatch):
    monkeypatch.setenv("AXIOMIZE_PRIVATE_TEST_ONLY", "SYNTHETIC_PRIVATE_TOKEN")
    source = """import json, os
print(json.dumps({
    "private": os.getenv("AXIOMIZE_PRIVATE_TEST_ONLY"),
    "seed": os.getenv("AXIOMIZE_SEED"),
    "hash": os.getenv("PYTHONHASHSEED"),
    "home": os.getenv("HOME"),
    "tmp": os.getenv("TMPDIR"),
}))"""
    result = sandbox.run_python(source, seed=2**32 + 7, allow_unsafe_code=True)
    assert result.exit_code == 0
    assert result.timed_out is False
    assert result.environment_inherited is False
    captured = json.loads(result.stdout)
    assert captured["private"] is None
    assert captured["seed"] == str(2**32 + 7)
    assert captured["hash"] == "7"
    assert captured["home"] == captured["tmp"]
    assert not Path(captured["home"]).exists()


def test_explicit_env_inheritance_is_separately_authorized(monkeypatch):
    monkeypatch.setenv("AXIOMIZE_PRIVATE_TEST_ONLY", "SYNTHETIC_VISIBLE_IF_OPTED_IN")
    source = """import os
print(os.getenv("AXIOMIZE_PRIVATE_TEST_ONLY"))"""
    result = sandbox.run_python(
        source, allow_unsafe_code=True, inherit_environment=True,
    )
    assert result.exit_code == 0
    assert result.environment_inherited is True
    assert "SYNTHETIC_VISIBLE_IF_OPTED_IN" in result.stdout


def test_python_control_environment_is_removed_even_with_inheritance(monkeypatch):
    monkeypatch.setenv("PYTHONSTARTUP", "/tmp/unsafe-startup.py")
    monkeypatch.setenv("PYTHONPATH", "/tmp/unsafe-package")
    env = sandbox._child_environment("/tmp/axiomize-clean", seed=None, inherit=True)
    assert "PYTHONSTARTUP" not in env
    assert "PYTHONPATH" not in env
    assert env["HOME"] == "/tmp/axiomize-clean"


def test_real_subprocess_exit_code_and_stderr_remain_visible():
    source = """import sys
print("scientific report")
print("observed failure", file=sys.stderr)
raise SystemExit(7)"""
    result = sandbox.run_python(source, allow_unsafe_code=True)
    assert result.exit_code == 7
    assert "scientific report" in result.stdout
    assert "observed failure" in result.stderr
    assert not result.timed_out


def test_real_timeout_returns_124_not_fake_success():
    result = sandbox.run_python(
        "import time; time.sleep(1)",
        timeout_s=0.05, allow_unsafe_code=True,
    )
    assert result.timed_out
    assert result.exit_code == 124


def test_capture_byte_budget_is_explicit_and_auditable(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox, "_MAX_CAPTURE_BYTES", 6)
    captured = tmp_path / "capture.txt"
    captured.write_bytes(b"abcdefghij")
    text, truncated = sandbox._read_capture(captured)
    assert text == "abcdef"
    assert truncated
    assert sandbox._read_capture(tmp_path / "absent") == ("", False)


def test_no_seed_means_no_fabricated_seed():
    env = sandbox._child_environment("/tmp/axiomize-clean", seed=None, inherit=False)
    assert "AXIOMIZE_SEED" not in env
    assert "PYTHONHASHSEED" not in env
    assert env["HOME"] == env["TMP"] == env["TEMP"] == env["TMPDIR"]
    assert all(not name.startswith("PYTHON") for name in env)


def test_actual_tool_version_identification_never_invents_success():
    versions = sandbox._tool_versions()
    assert versions["python"].split(".")[0] == "3"
    assert all(isinstance(v, str) and v for v in versions.values())


def test_child_resource_limit_hook_is_platform_appropriate():
    limiter = sandbox._resource_limiter(1.0)
    if os.name == "posix":
        assert callable(limiter)
    else:
        assert limiter is None


def test_local_resource_limiter_uses_only_a_simulated_resource_module(monkeypatch):
    import sys
    from types import SimpleNamespace

    if os.name != "posix":
        assert sandbox._resource_limiter(1.5) is None
        return

    calls = []
    def record(resource_id, pair):
        calls.append((resource_id, pair))

    fake = SimpleNamespace(
        RLIMIT_CPU=1, RLIMIT_AS=2, RLIMIT_FSIZE=3,
        RLIMIT_NPROC=4, setrlimit=record,
    )
    monkeypatch.setitem(sys.modules, "resource", fake)
    limiter = sandbox._resource_limiter(1.5)
    assert callable(limiter)
    limiter()
    assert calls[0] == (fake.RLIMIT_CPU, (3, 3))
    assert any(resource_id == fake.RLIMIT_AS for resource_id, _ in calls)
    assert any(resource_id == fake.RLIMIT_FSIZE for resource_id, _ in calls)
    assert any(resource_id == fake.RLIMIT_NPROC for resource_id, _ in calls)


def test_resource_limits_remain_best_effort_on_platform_refusals(monkeypatch):
    import sys
    from types import SimpleNamespace

    if os.name != "posix":
        assert sandbox._resource_limiter(1.0) is None
        return

    attempts = []
    def refuses(resource_id, pair):
        attempts.append(resource_id)
        raise ValueError("resource limit unavailable")

    fake = SimpleNamespace(
        RLIMIT_CPU=1, RLIMIT_AS=2, RLIMIT_FSIZE=3,
        setrlimit=refuses,
    )
    monkeypatch.setitem(sys.modules, "resource", fake)
    limiter = sandbox._resource_limiter(1.0)
    assert callable(limiter)
    limiter()
    assert attempts == [1, 2, 3]


def test_resource_limiter_refuses_to_run_on_nonposix_platform(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(sandbox, "os", SimpleNamespace(name="nt"))
    assert sandbox._resource_limiter(10.0) is None


def test_resource_module_not_found_is_an_explicit_nonfatal_fallback(monkeypatch):
    import builtins

    if os.name != "posix":
        assert sandbox._resource_limiter(1.0) is None
        return

    actual_import = builtins.__import__
    def without_resource(name, *args, **kwargs):
        if name == "resource":
            raise ImportError("unavailable in fake runtime")
        return actual_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_resource)
    assert sandbox._resource_limiter(1.0) is None


def test_tool_versions_preserve_explicit_not_installed_evidence(monkeypatch):
    import builtins

    actual_import = builtins.__import__
    def without_numpy(name, *args, **kwargs):
        if name == "numpy":
            raise ImportError("test unavailable numpy")
        return actual_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_numpy)
    assert sandbox._tool_versions()["numpy"] == "not-installed"


def test_process_limit_refusal_is_conservative_and_nonfatal(monkeypatch):
    import sys
    from types import SimpleNamespace

    if os.name != "posix":
        return

    seen = []
    def reject_only_process_limit(resource_id, pair):
        seen.append(resource_id)
        if resource_id == 4:
            raise OSError("RLIMIT_NPROC not permitted")

    fake = SimpleNamespace(
        RLIMIT_CPU=1, RLIMIT_AS=2, RLIMIT_FSIZE=3,
        RLIMIT_NPROC=4, setrlimit=reject_only_process_limit,
    )
    monkeypatch.setitem(sys.modules, "resource", fake)
    limiter = sandbox._resource_limiter(1.0)
    assert callable(limiter)
    limiter()
    assert seen == [1, 2, 3, 4]
