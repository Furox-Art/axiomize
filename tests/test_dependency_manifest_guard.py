"""Guard the dependency manifests against a requirement declared twice.

A package declared twice under two different environment markers (``"x>=1;
sys_platform == 'darwin'"`` and ``"x>=1; sys_platform != 'darwin'"``) is legal
PEP 508 and installs fine. It is not, however, something Dependabot can
rewrite: its Python file updater resolves the declaration it is replacing
against a single unambiguous requirement, fails with "Declaration not found
for <package>!", and drops the whole update job for the repository.

That is how the z3-solver Darwin pin broke the pip updater here. The pin was
also dead weight, because CI installs ``requirements-test.txt`` verbatim and
installs the package itself with ``--no-deps``; a constraint that only lived
in ``pyproject.toml`` never reached a CI runner.

The test therefore asserts two things:

* within each manifest, no distribution is declared more than once; and
* the two manifests agree on the distribution set, so a constraint can no
  longer drift into one file and leave the other describing a different
  dependency set.

Runnable both under pytest and as a script for stale-detection checks::

    python tests/test_dependency_manifest_guard.py
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
REQUIREMENTS = REPO_ROOT / "requirements-test.txt"

# ``name>=1.2`` / ``name[extra]>=1.2`` / ``name @ url`` at the start of a
# requirement, capturing the distribution name before any version or marker.
_REQUIREMENT_NAME = re.compile(r"^\s*(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)")

# Test tooling that CI installs but that is not a runtime dependency of the
# package, and therefore does not belong in pyproject's dependency list.
TEST_ONLY_DISTRIBUTIONS = frozenset({"pytest", "pytest-cov"})


def _normalize(name: str) -> str:
    """Normalize a distribution name the way PEP 503 does."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _requirement_name(requirement: str) -> str | None:
    """Return the normalized distribution name of a requirement string."""
    text = requirement.split("#", 1)[0].strip()
    if not text or text.startswith("-"):
        return None
    match = _REQUIREMENT_NAME.match(text)
    if not match:
        return None
    return _normalize(match.group("name"))


def pyproject_requirements(pyproject: Path = PYPROJECT) -> list[str]:
    """Return the raw requirement strings from ``[project] dependencies``."""
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    return list(data.get("project", {}).get("dependencies", []))


def requirements_file_requirements(requirements: Path = REQUIREMENTS) -> list[str]:
    """Return the raw requirement strings from a pip requirements file."""
    return [
        line.strip()
        for line in requirements.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def _duplicates(requirements: list[str]) -> dict[str, list[str]]:
    """Map each distribution declared more than once to its declarations."""
    seen: dict[str, list[str]] = {}
    for requirement in requirements:
        name = _requirement_name(requirement)
        if name is None:
            continue
        seen.setdefault(name, []).append(requirement)
    return {name: entries for name, entries in seen.items() if len(entries) > 1}


def find_all(
    pyproject: Path = PYPROJECT, requirements: Path = REQUIREMENTS
) -> list[str]:
    """Return every manifest finding, as human-readable lines."""
    findings: list[str] = []

    for label, entries in (
        ("pyproject.toml", pyproject_requirements(pyproject)),
        ("requirements-test.txt", requirements_file_requirements(requirements)),
    ):
        for name, declarations in _duplicates(entries).items():
            findings.append(
                f"{label}: {name} is declared more than once: "
                + "; ".join(repr(entry) for entry in declarations)
            )

    runtime = {
        name
        for name in (
            _requirement_name(entry) for entry in pyproject_requirements(pyproject)
        )
        if name is not None
    }
    installed = {
        name
        for name in (
            _requirement_name(entry) for entry in requirements_file_requirements(requirements)
        )
        if name is not None
    }

    for name in sorted(runtime - installed - TEST_ONLY_DISTRIBUTIONS):
        findings.append(
            f"pyproject.toml declares {name!r} but requirements-test.txt does not "
            "install it, so CI never exercises it"
        )
    for name in sorted(installed - runtime - TEST_ONLY_DISTRIBUTIONS):
        findings.append(
            f"requirements-test.txt installs {name!r} but pyproject.toml does not "
            "declare it, so the published metadata disagrees with CI"
        )
    return findings


def test_no_requirement_is_declared_twice_in_pyproject():
    duplicates = _duplicates(pyproject_requirements())
    assert not duplicates, "pyproject.toml declares a distribution twice:\n  " + "\n  ".join(
        f"{name}: {entries}" for name, entries in duplicates.items()
    )


def test_no_requirement_is_declared_twice_in_requirements_file():
    duplicates = _duplicates(requirements_file_requirements())
    assert not duplicates, "requirements-test.txt declares a distribution twice:\n  " + "\n  ".join(
        f"{name}: {entries}" for name, entries in duplicates.items()
    )


def test_manifests_agree_on_the_distribution_set():
    findings = find_all()
    assert not findings, "dependency manifest findings:\n  " + "\n  ".join(findings)


def test_z3_solver_is_declared_exactly_once():
    """The specific regression this guard exists for."""
    for label, entries in (
        ("pyproject.toml", pyproject_requirements()),
        ("requirements-test.txt", requirements_file_requirements()),
    ):
        names = [
            name
            for name in (_requirement_name(entry) for entry in entries)
            if name == "z3-solver"
        ]
        assert len(names) == 1, (
            f"{label} must declare z3-solver exactly once, found {len(names)}"
        )


def test_guard_detects_a_duplicate_declaration(tmp_path):
    """The guard must actually fail on the shape it is meant to catch."""
    requirements = tmp_path / "requirements-test.txt"
    requirements.write_text(
        "numpy>=1.24\nz3-solver>=4.12; sys_platform == 'darwin'\n"
        "z3-solver>=4.12; sys_platform != 'darwin'\n",
        encoding="utf-8",
    )
    duplicates = _duplicates(requirements_file_requirements(requirements))
    assert "z3-solver" in duplicates, duplicates

    # A single declaration must not be reported as a duplicate.
    requirements.write_text("numpy>=1.24\nz3-solver>=4.12\n", encoding="utf-8")
    duplicates = _duplicates(requirements_file_requirements(requirements))
    assert "z3-solver" not in duplicates, duplicates


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pyproject",
        default=str(PYPROJECT),
        help="path to pyproject.toml",
    )
    parser.add_argument(
        "--requirements",
        default=str(REQUIREMENTS),
        help="path to the requirements file CI installs",
    )
    args = parser.parse_args(argv)
    findings = find_all(Path(args.pyproject), Path(args.requirements))
    if findings:
        print(f"FAIL: {len(findings)} dependency manifest finding(s):")
        for finding in findings:
            print(f"  {finding}")
        return 1
    print("OK: dependency manifests declare each distribution once and agree")
    return 0


if __name__ == "__main__":
    sys.exit(main())
