"""Controlled execution is opt-in, isolated, bounded, and auditable."""

from __future__ import annotations

import os

import pytest

from axiomize.execution.sandbox import (
    UnsafeExecutionDenied,
    _child_environment,
    _read_capture,
    _resource_limiter,
    run_python,
)


def test_arbitrary_code_execution_is_denied_by_default():
    with pytest.raises(UnsafeExecutionDenied, match="disabled by default"):
        run_python("print('do not run')")


@pytest.mark.parametrize(
    ("source", "timeout", "error"),
    [
        (None, 1.0, "code must be a string"),
        ("print(1)", 0.0, "timeout_s"),
        ("print(1)", float("nan"), "timeout_s"),
        ("print(1)", float("inf"), "timeout_s"),
        ("print(1)", 3601.0, "timeout_s"),
    ],
)
def test_untrusted_execution_inputs_are_rejected_even_with_explicit_permission(source, timeout, error):
    with pytest.raises(ValueError, match=error):
        run_python(source, timeout_s=timeout, allow_unsafe_code=True)


def test_isolated_python_child_runs_only_trusted_declared_program():
    result = run_python("print('scientific child')", timeout_s=3.0, seed=3, allow_unsafe_code=True)
    assert result.exit_code == 0
    assert result.stdout.strip() == "scientific child"
    assert result.stderr == ""
    assert result.timed_out is False
    assert result.environment_inherited is False
    assert result.tool_versions["python"]
    assert result.execution_time_s >= 0


def test_python_process_failure_is_not_reported_as_success():
    result = run_python("raise RuntimeError('observed failure')", timeout_s=3.0, allow_unsafe_code=True)
    assert result.exit_code != 0
    assert "RuntimeError" in result.stderr
    assert result.timed_out is False


def test_environment_isolation_does_not_inherit_secret_or_python_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("SECRET_CLOUD_TOKEN", "not-exported")
    monkeypatch.setenv("PYTHONPATH", "/fake/unsafe/path")
    env = _child_environment(str(tmp_path), seed=7, inherit=False)
    assert "SECRET_CLOUD_TOKEN" not in env
    assert "PYTHONPATH" not in env
    assert env["HOME"] == str(tmp_path)
    assert env["PYTHONHASHSEED"] == "7"
    assert env["AXIOMIZE_SEED"] == "7"


def test_parent_environment_inheritance_requires_separate_explicit_permission(monkeypatch, tmp_path):
    monkeypatch.setenv("SCIENTIFIC_TEST_ONLY_MARKER", "known-value")
    env = _child_environment(str(tmp_path), seed=None, inherit=True)
    assert env["SCIENTIFIC_TEST_ONLY_MARKER"] == "known-value"
    assert "PYTHONPATH" not in env
    assert "PYTHONHASHSEED" not in env


def test_isolated_process_does_not_observe_ambient_secret(monkeypatch):
    monkeypatch.setenv("SCIENTIFIC_TEST_SECRET", "PRIVATE_MARKER")
    result = run_python(
        "import os; print(os.environ.get('SCIENTIFIC_TEST_SECRET','none'))", timeout_s=3.0, allow_unsafe_code=True
    )
    assert result.stdout.strip() == "none"


def test_capture_truncation_is_explicit_and_does_not_lose_decode_contract(monkeypatch, tmp_path):
    import axiomize.execution.sandbox as sandbox

    monkeypatch.setattr(sandbox, "_MAX_CAPTURE_BYTES", 3)
    file = tmp_path / "output.txt"
    file.write_bytes(b"abcdef")
    text, truncated = _read_capture(file)
    assert text == "abc"
    assert truncated is True
    missing, was_truncated = _read_capture(tmp_path / "missing.txt")
    assert missing == ""
    assert was_truncated is False


def test_resource_limiter_is_present_on_posix_and_preserves_nonposix_fallback(monkeypatch):
    import axiomize.execution.sandbox as sandbox

    if os.name == "posix":
        assert callable(_resource_limiter(2.0))
    monkeypatch.setattr(sandbox.os, "name", "nt")
    assert sandbox._resource_limiter(2.0) is None
