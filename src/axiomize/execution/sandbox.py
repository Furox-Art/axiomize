"""Controlled local execution of explicitly trusted scientific Python code.

This module is **not** an OS security sandbox. Python code can perform any action
available to the current OS user unless the caller supplies a stronger external
sandbox/container.  Axiomize therefore refuses arbitrary code by default,
removes ambient secrets from the child environment, uses Python isolated mode,
and applies best-effort local resource ceilings.
"""

from __future__ import annotations

import math
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

_MAX_CODE_BYTES = 1 * 1024 * 1024
_MAX_CAPTURE_BYTES = 8 * 1024 * 1024
_MAX_TIMEOUT_S = 3600.0
_ENV_ALLOWLIST = {
    "PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT",
    "LANG", "LC_ALL", "LC_CTYPE", "TZ",
}


class UnsafeExecutionDenied(PermissionError):
    pass


@dataclass
class ExecutionRecord:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    timeout_s: float
    seed: int | None
    execution_time_s: float
    tool_versions: dict[str, str] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)
    output_truncated: bool = False
    environment_inherited: bool = False


def _tool_versions() -> dict[str, str]:
    versions: dict[str, str] = {"python": sys.version.split()[0]}
    for mod in ("numpy", "scipy", "sympy"):
        try:
            module = __import__(mod)
            versions[mod] = str(getattr(module, "__version__", "unknown"))
        except ImportError:
            versions[mod] = "not-installed"
    return versions


def _child_environment(workdir: str, *, seed: int | None, inherit: bool) -> dict[str, str]:
    if inherit:
        env = dict(os.environ)
    else:
        env = {key: value for key, value in os.environ.items() if key in _ENV_ALLOWLIST}
    # Do not let parent PYTHON* controls defeat ``-I`` or introduce a custom
    # startup path.  Seed is an explicit Axiomize input, not an ambient secret.
    for key in list(env):
        if key.startswith("PYTHON"):
            env.pop(key, None)
    env["HOME"] = workdir
    env["USERPROFILE"] = workdir
    env["TMPDIR"] = workdir
    env["TEMP"] = workdir
    env["TMP"] = workdir
    if seed is not None:
        env["AXIOMIZE_SEED"] = str(seed)
        env["PYTHONHASHSEED"] = str(seed % 4294967296)
    return env


def _resource_limiter(timeout_s: float):
    """Return a POSIX pre-exec limiter, or ``None`` on unsupported platforms."""
    if os.name != "posix":
        return None
    try:
        import resource
    except ImportError:  # pragma: no cover
        return None

    def limit() -> None:
        cpu = max(1, int(math.ceil(timeout_s)) + 1)
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
        except (ValueError, OSError):
            pass
        # 2 GiB is high enough for normal numerical smoke work but prevents an
        # accidental child from consuming the whole host.
        try:
            two_gib = 2 * 1024 * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (two_gib, two_gib))
        except (ValueError, OSError):
            pass
        try:
            resource.setrlimit(resource.RLIMIT_FSIZE, (_MAX_CAPTURE_BYTES, _MAX_CAPTURE_BYTES))
        except (ValueError, OSError):
            pass
        if hasattr(resource, "RLIMIT_NPROC"):
            try:
                resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
            except (ValueError, OSError):
                pass

    return limit


def _read_capture(path: Path) -> tuple[str, bool]:
    data = path.read_bytes() if path.exists() else b""
    truncated = len(data) > _MAX_CAPTURE_BYTES
    if truncated:
        data = data[:_MAX_CAPTURE_BYTES]
    return data.decode("utf-8", errors="replace"), truncated


def run_python(
    code: str,
    timeout_s: float = 60.0,
    seed: int | None = None,
    *,
    allow_unsafe_code: bool = False,
    inherit_environment: bool = False,
) -> ExecutionRecord:
    """Execute explicitly trusted Python in a constrained child process.

    ``allow_unsafe_code=True`` is mandatory because this helper does not provide
    kernel/container isolation. ``inherit_environment`` is a second, separate
    opt-in; by default API keys and other ambient secrets are not passed to the
    child process.
    """
    if not allow_unsafe_code:
        raise UnsafeExecutionDenied(
            "arbitrary Python execution is disabled by default; retry only for trusted code with allow_unsafe_code=True"
        )
    if not isinstance(code, str):
        raise ValueError("code must be a string")
    if len(code.encode("utf-8")) > _MAX_CODE_BYTES:
        raise ValueError(f"code exceeds hard limit of {_MAX_CODE_BYTES} bytes")
    timeout_s = float(timeout_s)
    if not math.isfinite(timeout_s) or timeout_s <= 0 or timeout_s > _MAX_TIMEOUT_S:
        raise ValueError(f"timeout_s must be finite and in (0, {_MAX_TIMEOUT_S:g}]")

    start = time.perf_counter()
    timed_out = False
    exit_code = 1
    stdout = ""
    stderr = ""
    output_truncated = False
    with tempfile.TemporaryDirectory(prefix="axiomize_exec_") as workdir:
        env = _child_environment(workdir, seed=seed, inherit=inherit_environment)
        stdout_path = Path(workdir) / "stdout.txt"
        stderr_path = Path(workdir) / "stderr.txt"
        try:
            with stdout_path.open("wb") as out_fh, stderr_path.open("wb") as err_fh:
                proc = subprocess.run(
                    [sys.executable, "-I", "-c", code],
                    stdout=out_fh,
                    stderr=err_fh,
                    timeout=timeout_s,
                    cwd=workdir,
                    env=env,
                    check=False,
                    preexec_fn=_resource_limiter(timeout_s),
                )
            exit_code = int(proc.returncode)
        except subprocess.TimeoutExpired:
            timed_out = True
            exit_code = 124
        stdout, out_truncated = _read_capture(stdout_path)
        stderr, err_truncated = _read_capture(stderr_path)
        output_truncated = out_truncated or err_truncated

    return ExecutionRecord(
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        timeout_s=timeout_s,
        seed=seed,
        execution_time_s=time.perf_counter() - start,
        tool_versions=_tool_versions(),
        output_truncated=output_truncated,
        environment_inherited=bool(inherit_environment),
    )
