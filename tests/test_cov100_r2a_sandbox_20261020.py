"""Round-2 coverage hardening for ``axiomize.execution.sandbox``.

The POSIX resource limiter is platform-conditional (``os.name != "posix"``).
These tests fake the platform name and the ``resource`` module at the import
boundary so the Linux-only branch executes on every CI platform, asserting the
exact rlimits requested and that a kernel refusal is tolerated.
"""
from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from axiomize.execution import sandbox

_GIB = 1024 * 1024 * 1024


def _fake_resource(calls: list[tuple[int, tuple[int, int]]], *, error: type[Exception] | None,
                   include_nproc: bool, record_before_raising: bool = True) -> SimpleNamespace:
    module = SimpleNamespace(RLIMIT_CPU=11, RLIMIT_AS=12, RLIMIT_FSIZE=13)
    if include_nproc:
        module.RLIMIT_NPROC = 14

    def setrlimit(which: int, limits: tuple[int, int]) -> None:
        if record_before_raising:
            calls.append((which, limits))
        if error is not None:
            raise error("kernel refused")

    module.setrlimit = setrlimit
    return module


def test_non_posix_platform_has_no_preexec_limiter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sandbox, "os", SimpleNamespace(name="nt"))
    assert sandbox._resource_limiter(5.0) is None


def test_posix_limiter_requests_bounded_cpu_memory_file_and_process_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[int, tuple[int, int]]] = []
    resource = _fake_resource(calls, error=None, include_nproc=True)
    monkeypatch.setattr(sandbox, "os", SimpleNamespace(name="posix"))
    monkeypatch.setitem(sys.modules, "resource", resource)

    limiter = sandbox._resource_limiter(1.2)
    assert callable(limiter)
    limiter()

    assert calls == [
        (11, (3, 3)),
        (12, (2 * _GIB, 2 * _GIB)),
        (13, (sandbox._MAX_CAPTURE_BYTES, sandbox._MAX_CAPTURE_BYTES)),
        (14, (64, 64)),
    ]


@pytest.mark.parametrize("error", [ValueError, OSError])
def test_posix_limiter_tolerates_kernel_refusals(
    monkeypatch: pytest.MonkeyPatch, error: type[Exception]
) -> None:
    calls: list[tuple[int, tuple[int, int]]] = []
    resource = _fake_resource(calls, error=error, include_nproc=True)
    monkeypatch.setattr(sandbox, "os", SimpleNamespace(name="posix"))
    monkeypatch.setitem(sys.modules, "resource", resource)

    limiter = sandbox._resource_limiter(0.0)
    assert limiter is not None
    limiter()  # must not propagate the kernel refusal

    assert [which for which, _ in calls] == [11, 12, 13, 14]


def test_posix_limiter_skips_missing_nproc_support(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[int, tuple[int, int]]] = []
    resource = _fake_resource(calls, error=None, include_nproc=False)
    monkeypatch.setattr(sandbox, "os", SimpleNamespace(name="posix"))
    monkeypatch.setitem(sys.modules, "resource", resource)

    limiter = sandbox._resource_limiter(2.0)
    assert limiter is not None
    limiter()
    assert [which for which, _ in calls] == [11, 12, 13]
