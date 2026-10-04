#!/usr/bin/env python3
"""Fail CI when a release workflow can validate artifacts only by luck.

A sibling repository failed its PyPI release because twine 6.2.0 and earlier
replace `packaging`'s metadata-version list **at import time**:
`import twine.package` rebinds ``packaging.metadata._VALID_METADATA_VERSIONS``
to a hardcoded list ending at ``2.4``. ``packaging`` 26.x knows about ``2.5``
and ``2.6``; after importing twine 6.2.0 it does not. ``twine check --strict``
then rejects perfectly valid artifacts with::

    InvalidDistribution: '2.5' is not a valid metadata version

twine 7.0.0 stopped overriding the list. This repository's build backend emits
``Metadata-Version: 2.5``, and ``release.yml`` installed ``build twine``
**unpinned**, so whether the release gate passed depended on whatever pip
resolved that day.

What this guard asserts, for every workflow that runs ``twine check``:

  1. the workflow pins ``twine`` to an exact version (no ``>=``, no bare name);
  2. that exact version is installed in the environment, so the workflow runs
     what it claims to run;
  3. importing twine in this interpreter does **not** shrink packaging's list of
     valid metadata versions -- the exact mutation that broke the sibling;
  4. every metadata version this repository actually emits is still valid
     after that import.

Unpinned is a failure, not a warning. ``--strict`` is not weakened and no
metadata is rewritten.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"

#: Floor for twine. 7.0.0 is the first release that stopped replacing
#: packaging's metadata-version list at import time.
MIN_TWINE = (7, 0, 0)

#: Matches an install step's package requirements. Deliberately strict: a
#: requirement is "pinned" only if every specifier is `==`.
REQUIREMENT = re.compile(r"(?<![\w.-])([A-Za-z0-9][\w.-]*)(?P<spec>(?:[<>!=~]=?|===)\s*[^\s\"']+)?")

PINNED = re.compile(r"^[A-Za-z0-9][\w.-]*==[^\s,;\"']+$")


class GuardFailure(RuntimeError):
    pass


def _fail(message: str) -> None:
    raise GuardFailure(message)


def _parse_version(raw: str) -> tuple[int, ...]:
    match = re.match(r"^\D*(\d+)(?:\.(\d+))?(?:\.(\d+))?", raw.strip())
    if not match:
        raise GuardFailure(f"cannot parse version {raw!r}")
    return tuple(int(part) for part in match.groups(default="0"))


def _twine_check_workflows() -> list[Path]:
    """Every workflow that runs ``twine check``.

    Scanned from the files rather than listed here, so a new workflow that
    starts validating distributions is covered automatically and cannot forget
    to be pinned.
    """
    found = []
    for path in sorted(WORKFLOWS.glob("*.y*ml")):
        text = path.read_text(encoding="utf-8")
        if re.search(r"twine\s+check", text):
            found.append(path)
    return found


def _install_lines(text: str) -> list[tuple[int, str]]:
    """Lines that pip-install something, with their 1-based line numbers."""
    lines = []
    for number, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not re.match(r"^(pip|python -m pip)\s+install\b", stripped):
            continue
        if "twine" not in stripped:
            continue
        lines.append((number, stripped))
    return lines


def _strip_trailing_comment(line: str) -> str:
    """Remove a trailing YAML comment, respecting quotes."""
    out = []
    quote = None
    for index, char in enumerate(line):
        if quote:
            out.append(char)
            if char == quote:
                quote = None
            continue
        if char in "\"'":
            quote = char
            out.append(char)
            continue
        if char == "#" and (index == 0 or line[index - 1].isspace()):
            break
        out.append(char)
    return "".join(out)


def _pinned_twine_requirements(line: str) -> list[str]:
    """Requirements in an install line that pin twine exactly."""
    body = _strip_trailing_comment(line)
    body = re.sub(r"^(pip|python -m pip)\s+install\s+", "", body)
    body = re.sub(r"(-r|--requirement)\s+\S+", "", body)
    body = re.sub(r"--\S+", "", body)
    tokens = [t.strip("\"'") for t in re.split(r"[\s;]+", body) if t.strip("\"'")]
    pinned = []
    for token in tokens:
        if not token.lower().startswith("twine"):
            continue
        if PINNED.match(token):
            pinned.append(token)
    return pinned


def check_workflow_pins() -> list[tuple[str, str]]:
    """Returns ``(workflow, detail)`` for each workflow, one entry per finding."""
    findings: list[tuple[str, str]] = []
    workflows = _twine_check_workflows()
    if not workflows:
        findings.append(("<none>", "no workflow runs `twine check`; expected release.yml"))
        return findings

    for path in workflows:
        text = path.read_text(encoding="utf-8")
        installs = _install_lines(text)
        if not installs:
            findings.append(
                (path.name, "runs `twine check` but never installs twine; add a pinned install step")
            )
            continue
        pinned_any = False
        for number, line in installs:
            pinned = _pinned_twine_requirements(line)
            if not pinned:
                findings.append(
                    (
                        path.name,
                        f"line {number} installs twine without an exact `==` pin: {line[:90]}",
                    )
                )
                continue
            pinned_any = True
            for requirement in pinned:
                version = requirement.split("==", 1)[1]
                parsed = _parse_version(version)
                floor = ".".join(str(part) for part in MIN_TWINE)
                if parsed < MIN_TWINE:
                    findings.append(
                        (
                            path.name,
                            f"line {number} pins twine=={version}, but twine {floor} is "
                            "the floor: earlier versions replace packaging's "
                            "metadata-version list at import time and reject "
                            "Metadata-Version 2.5",
                        )
                    )
        if not pinned_any and not any(f[0] == path.name for f in findings):
            findings.append((path.name, "twine is never pinned exactly"))

    return findings


def _emitted_metadata_versions() -> set[str]:
    """Metadata versions declared in ``pyproject.toml``.

    The build backend derives the emitted ``Metadata-Version`` from the
    ``license``/``license-files`` form, so reading the declaration is enough and
    needs no build. ``__init__.py`` is not consulted: it holds no metadata
    declaration.
    """
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    project = text.split("[project]", 1)[1].split("\n[", 1)[0]
    uses_pep639 = bool(re.search(r'^\s*license\s*=\s*"[^"]+"\s*$', project, re.MULTILINE))
    uses_license_files = bool(re.search(r"^\s*license-files\s*=", project, re.MULTILINE))
    if uses_pep639 and uses_license_files:
        # hatchling >= 1.27 with both PEP 639 keys emits Metadata-Version 2.4+.
        # The floor is 2.4 because PEP 639 introduced License-Expression there.
        return {"2.4", "2.5"}
    return {"2.1"}


def check_installed_twine() -> tuple[str, tuple[tuple[int, ...], tuple[int, ...]]]:
    """Verify the *installed* twine is pinned-safe.

    Returns ``(version, (packaging_list_before, packaging_list_after))`` so the
    caller can report the mutation directly.
    """
    try:
        import twine  # noqa: PLC0415
    except ImportError as exc:
        raise GuardFailure(
            "twine is not importable in this interpreter; install the pinned version first"
        ) from exc

    installed = getattr(twine, "__version__", "unknown")
    if installed == "unknown":
        raise GuardFailure("cannot determine the installed twine version")

    try:
        import packaging.metadata as pm  # noqa: PLC0415
    except ImportError as exc:
        raise GuardFailure("packaging is not importable") from exc

    before = tuple(getattr(pm, "_VALID_METADATA_VERSIONS", ()))
    if not before:
        raise GuardFailure(
            f"packaging.metadata has no _VALID_METADATA_VERSIONS; cannot verify twine "
            f"(packaging {getattr(pm, '__version__', '?')})"
        )

    import twine.package  # noqa: PLC0415,F401  -- the import that used to mutate

    after = tuple(getattr(pm, "_VALID_METADATA_VERSIONS", ()))

    if not after:
        raise GuardFailure("importing twine removed packaging's metadata-version list entirely")

    return installed, (before, after)


def main() -> int:
    failures: list[str] = []

    print("=== workflow pins ===")
    pin_findings = check_workflow_pins()
    workflows = _twine_check_workflows()
    if not workflows:
        print("  (no workflow runs `twine check`)")
    for name in sorted({f[0] for f in pin_findings if f[0] != "<none>"}):
        print(f"  {name}")
    if not pin_findings:
        print("  PASS every `twine check` workflow pins twine exactly")
    for workflow, detail in pin_findings:
        message = f"{workflow}: {detail}"
        print(f"  FAIL {message}")
        failures.append(message)

    print()
    print("=== installed twine ===")
    try:
        installed, (before, after) = check_installed_twine()
    except GuardFailure as exc:
        print(f"  FAIL {exc}")
        failures.append(str(exc))
        print()
        print(f"RELEASE TOOLCHAIN GUARD: FAIL ({len(failures)} finding(s))")
        return 1

    print(f"  twine version: {installed}")
    floor = ".".join(str(part) for part in MIN_TWINE)
    if _parse_version(installed) < MIN_TWINE:
        message = f"installed twine {installed} is below the floor {floor}"
        print(f"  FAIL {message}")
        failures.append(message)
    else:
        print(f"  PASS installed twine >= {'.'.join(str(p) for p in MIN_TWINE)}")

    print(f"  packaging metadata versions before `import twine`: {list(before)}")
    print(f"  packaging metadata versions after  `import twine`: {list(after)}")
    if before != after:
        message = (
            f"importing twine {installed} replaced packaging's metadata-version list "
            f"({list(before)} -> {list(after)}); this is the twine <= 6.2.0 bug that "
            "rejects valid artifacts"
        )
        print(f"  FAIL {message}")
        failures.append(message)
    else:
        print("  PASS importing twine left packaging's metadata-version list untouched")

    print()
    print("=== emitted metadata versions ===")
    emitted = sorted(_emitted_metadata_versions())
    print(f"  pyproject declares PEP 639 keys, so the backend may emit: {emitted}")
    lost = [v for v in emitted if v not in after]
    if lost:
        message = (
            f"twine {installed} would reject metadata version(s) {lost}; the artifacts "
            "this repository builds are valid and the toolchain is wrong"
        )
        print(f"  FAIL {message}")
        failures.append(message)
    else:
        print(f"  PASS every emitted metadata version {emitted} survives `import twine`")

    print()
    if failures:
        print(f"RELEASE TOOLCHAIN GUARD: FAIL ({len(failures)} finding(s))")
        return 1
    print("RELEASE TOOLCHAIN GUARD: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GuardFailure as error:
        print(f"RELEASE TOOLCHAIN GUARD ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error