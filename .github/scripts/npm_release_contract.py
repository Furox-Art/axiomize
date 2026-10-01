#!/usr/bin/env python3
"""Fail CI when the npm distribution and the Python distribution disagree.

The npm package is a launcher shim for the Python CLI, so a version skew between
``package.json`` and ``pyproject.toml`` publishes a shim that advertises a
version the Python package does not have. Before this gate the two files drifted
silently: ``package.json`` stayed at ``1.12.2`` while the Python distribution
was at ``1.12.3``.

The npm package's *major* version tracks the Python *minor* version. Both
distributions are released from the same ``.github/pypi-release-trigger``
commit, and this repository is pre-2.0, so ``1.x`` on npm corresponds to the
Python ``1.x`` line and a ``~> 1.0.0`` range. This script asserts:

  1. ``package.json`` version == ``pyproject.toml`` version (exact lockstep),
  2. both share the same major version,
  3. the declared npm install range is ``~> <major>.0.0``,
  4. ``package.json`` names a real ``main`` and every real ``bin`` entry,
  5. every file listed in the ``files`` allowlist exists,
  6. the npm package version does not already exist on the public registry
     when ``--check-registry`` is passed.

Run from a checkout with no arguments. The Python-side version contract is
enforced separately by ``check_release_contract.py``.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_JSON = ROOT / "package.json"
PYPROJECT = ROOT / "pyproject.toml"

REGISTRY_URL = "https://registry.npmjs.org/{name}"
# This gate runs on every PR. A registry lookup is network-dependent, so it is
# opt-in and only meaningful in the release workflow.
REGISTRY_TIMEOUT_S = 20


class ContractFailure(RuntimeError):
    pass


def _fail(message: str) -> None:
    raise ContractFailure(message)


def _read_manifest() -> dict:
    if not PACKAGE_JSON.is_file():
        _fail(f"required file is missing: {PACKAGE_JSON.relative_to(ROOT)}")
    try:
        manifest = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _fail(f"package.json is not valid JSON: {exc}")
    if not isinstance(manifest, dict):
        _fail("package.json must contain a JSON object")
    return manifest


def _python_version() -> str:
    text = PYPROJECT.read_text(encoding="utf-8")
    try:
        project = text.split("[project]", 1)[1].split("\n[", 1)[0]
    except IndexError as exc:
        raise ContractFailure("pyproject.toml has no [project] section") from exc
    marker = "version"
    for line in project.splitlines():
        stripped = line.strip()
        if not stripped.startswith(marker):
            continue
        _, _, value = stripped.partition("=")
        value = value.strip()
        if value.startswith('"') and value.endswith('"') and len(value) >= 2:
            return value[1:-1]
    _fail("pyproject.toml has no literal [project] version")


def _major(version: str) -> str:
    return version.split(".", 1)[0]


def _check_version_lockstep(manifest: dict) -> None:
    npm_version = manifest.get("version")
    if not isinstance(npm_version, str) or not npm_version:
        _fail("package.json has no version string")
    python_version = _python_version()

    print(f"npm version     {npm_version}")
    print(f"python version  {python_version}")

    if npm_version != python_version:
        _fail(
            f"npm version {npm_version} != python version {python_version}; "
            "both distributions are published from the same release commit, so "
            "update package.json and pyproject.toml together"
        )
    print("PASS npm and python versions are in exact lockstep")

    npm_major = _major(npm_version)
    python_major = _major(python_version)
    if npm_major != python_major:
        _fail(
            f"npm major {npm_major} does not track python major {python_major}; "
            "the npm shim only works against the Python package it was built with"
        )
    print(f"PASS npm major {npm_major} tracks the Python release line")

    compat = manifest.get("axiomizeCompat")
    if not isinstance(compat, dict):
        _fail(
            "package.json has no 'axiomizeCompat' object; declare the supported "
            "npm range there so consumers can see it"
        )
    expected_range = f"~> {npm_major}.0.0"
    npm_range = compat.get("npm")
    if npm_range != expected_range:
        _fail(f"axiomizeCompat.npm is {npm_range!r}, expected {expected_range!r}")
    python_range = compat.get("python")
    if not isinstance(python_range, str) or not python_range:
        _fail("axiomizeCompat.python must be a non-empty string")
    print(f"PASS declared compat range {npm_range} (python {python_range})")


def _check_package_surfaces(manifest: dict) -> None:
    name = manifest.get("name")
    if not isinstance(name, str) or not name:
        _fail("package.json has no name")

    main = manifest.get("main")
    if not isinstance(main, str) or not main:
        _fail("package.json has no main entry")
    if not (ROOT / main).is_file():
        _fail(f"package.json main does not exist: {main}")
    print(f"PASS main {main} exists")

    bins = manifest.get("bin")
    if not isinstance(bins, dict) or not bins:
        _fail("package.json declares no bin entries")
    for bin_name, target in bins.items():
        if not isinstance(target, str) or not (ROOT / target).is_file():
            _fail(f"bin {bin_name} points at a missing file: {target}")
    print(f"PASS all {len(bins)} bin entries exist ({', '.join(sorted(bins))})")

    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        _fail("package.json declares no files allowlist; npm would ship the whole checkout")
    for entry in files:
        if not isinstance(entry, str) or not entry:
            _fail(f"files allowlist contains a non-string entry: {entry!r}")
        if not (ROOT / entry.rstrip("/")).exists():
            _fail(f"files allowlist entry does not exist: {entry}")
    print(f"PASS files allowlist resolves ({len(files)} entries)")


def _check_registry(manifest: dict) -> None:
    name = manifest["name"]
    version = manifest["version"]
    url = REGISTRY_URL.format(name=name)
    try:
        with urllib.request.urlopen(url, timeout=REGISTRY_TIMEOUT_S) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            _fail(f"{name} is not published on npm at all; the shim cannot be verified")
        _fail(f"npm registry lookup for {name} failed with HTTP {exc.code}")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        _fail(f"npm registry lookup for {name} failed: {exc}")

    versions = payload.get("versions")
    if not isinstance(versions, dict):
        _fail(f"npm registry response for {name} has no versions map")
    if version in versions:
        _fail(
            f"npm already has {name}@{version}; bump the version before "
            "releasing, the registry will not accept a duplicate"
        )
    print(f"PASS npm {version} is not yet published for {name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-registry",
        action="store_true",
        help="also assert the version is not already present on the public npm registry",
    )
    args = parser.parse_args()

    manifest = _read_manifest()
    failures: list[str] = []
    checks = [
        lambda: _check_version_lockstep(manifest),
        lambda: _check_package_surfaces(manifest),
    ]
    if args.check_registry:
        checks.append(lambda: _check_registry(manifest))

    for check in checks:
        try:
            check()
        except ContractFailure as exc:
            failures.append(str(exc))
            print(f"- FAIL: {exc}")

    if failures:
        print(f"\nNPM CONTRACT: FAIL ({len(failures)} failing check(s))")
        return 1
    print("\nNPM CONTRACT: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractFailure as exc:
        print(f"NPM CONTRACT ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
