#!/usr/bin/env python3
"""Fail CI when package/release metadata drift or release provenance is unsafe."""

from __future__ import annotations

import json
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
    arbitrary branch.  Both publishing workflows must only ever publish content
    from the repository's main branch. Other workflows (CI) also run this
    script on pull-request refs and must stay unaffected.
    """
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return True
    workflow = os.environ.get("GITHUB_WORKFLOW", "")
    if workflow not in {"Release", "npm Publish"}:
        return True
    ref = os.environ.get("GITHUB_REF", "")
    if ref != "refs/heads/main":
        print(
            f"FAIL: {workflow} workflow may run only from refs/heads/main; "
            f"got {ref or '<missing>'}",
            file=sys.stderr,
        )
        return False
    return True


def _json_version(path: Path, *, packages: bool = False) -> str:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{path.name} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"{path.name} must contain a JSON object")
    version = data.get("version")
    if not isinstance(version, str):
        raise RuntimeError(f"{path.name} has no string version")
    if packages:
        entries = data.get("packages")
        if not isinstance(entries, list) or not entries:
            raise RuntimeError(f"{path.name} has no packages array")
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("version") != version:
                found = entry.get("version") if isinstance(entry, dict) else entry
                raise RuntimeError(
                    f"{path.name} package entry version {found!r} disagrees with {version!r}"
                )
    return version


def _citation_version() -> str:
    text = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    match = re.search(r'^version:\s*"?([^"\s]+)"?\s*$', text, re.MULTILINE)
    if not match:
        raise RuntimeError("CITATION.cff has no literal version")
    return match.group(1)


def _npm_version() -> str:
    """The npm shim version.

    The npm package is published from the same release commit as the Python
    distribution, so it is part of the lockstep set. It drifted independently
    before this gate existed (package.json sat at 1.12.2 while Python was at
    1.12.3), which published a shim advertising a version the Python package
    did not have.
    """
    text = (ROOT / "package.json").read_text(encoding="utf-8")
    match = re.search(r'^\s*"version"\s*:\s*"([^"]+)"\s*,?\s*$', text, re.MULTILINE)
    if not match:
        raise RuntimeError("package.json has no literal version")
    return match.group(1)


def main() -> int:
    versions = {
        "pyproject": _project_version(),
        "runtime": _runtime_version(),
        "pypi_trigger": _trigger_version(),
        "readme": _readme_version(),
        "changelog": _changelog_version(),
        "npm": _npm_version(),
        "codemeta": _json_version(ROOT / "codemeta.json"),
        "citation": _citation_version(),
        "server": _json_version(ROOT / "server.json", packages=True),
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
