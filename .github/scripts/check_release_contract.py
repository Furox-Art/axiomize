#!/usr/bin/env python3
"""Fail CI when package/release metadata drift or release provenance is unsafe."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _project_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    try:
        project = text.split("[project]", 1)[1].split("\n[", 1)[0]
    except IndexError as exc:
        raise RuntimeError("pyproject.toml has no [project] section") from exc
    match = re.search(r'^version\s*=\s*"([^"]+)"\s*$', project, re.MULTILINE)
    if not match:
        raise RuntimeError("[project] has no literal version")
    return match.group(1)


def _runtime_version() -> str:
    text = (ROOT / "src" / "axiomize" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*"([^"]+)"\s*$', text, re.MULTILINE)
    if not match:
        raise RuntimeError("src/axiomize/__init__.py has no __version__")
    return match.group(1)


def _trigger_version() -> str:
    lines = (ROOT / ".github" / "pypi-release-trigger").read_text(encoding="utf-8").splitlines()
    if not lines:
        raise RuntimeError(".github/pypi-release-trigger is empty")
    match = re.fullmatch(r"axiomize\s+([^\s]+)", lines[0].strip())
    if not match:
        raise RuntimeError("first trigger line must be: axiomize <version>")
    return match.group(1)


def _readme_version() -> str:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    match = re.search(r"^Current package line:\s*\*\*([^*]+)\*\*", text, re.MULTILINE)
    if not match:
        raise RuntimeError("README.md has no 'Current package line' version")
    return match.group(1).strip()


def _changelog_version() -> str:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(r"^## \[([^\]]+)\]", text, re.MULTILINE)
    if not match:
        raise RuntimeError("CHANGELOG.md has no release heading")
    return match.group(1).strip()


def _release_ref_is_allowed() -> bool:
    """Block release-workflow execution from feature branches.

    ``workflow_dispatch`` is useful for retrying a failed release, but without
    this guard GitHub allows a user to dispatch the workflow against an
    arbitrary branch.  The release workflow must only ever publish content from
    the repository's main branch.
    """
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return True
    if os.environ.get("GITHUB_WORKFLOW") != "Release":
        return True
    ref = os.environ.get("GITHUB_REF", "")
    if ref != "refs/heads/main":
        print(
            f"FAIL: Release workflow may run only from refs/heads/main; got {ref or '<missing>'}",
            file=sys.stderr,
        )
        return False
    return True


def main() -> int:
    versions = {
        "pyproject": _project_version(),
        "runtime": _runtime_version(),
        "pypi_trigger": _trigger_version(),
        "readme": _readme_version(),
        "changelog": _changelog_version(),
    }
    for name, value in versions.items():
        print(f"{name:12s} {value}")
    if len(set(versions.values())) != 1:
        print("FAIL: release versions differ; update package, trigger and public docs together", file=sys.stderr)
        return 1
    if not _release_ref_is_allowed():
        return 1
    print("PASS: release version contract is synchronized and release ref is authorized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
