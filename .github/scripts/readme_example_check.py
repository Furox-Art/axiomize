#!/usr/bin/env python3
"""Fail CI when the documented quickstart stops matching real behavior.

The README and ``docs/quickstart.md`` promise a specific five-minute path: an
install command, a runnable example, and the output that example prints. This
gate executes the real installed package and compares it against those claims,
so a refactor cannot quietly invalidate the first thing a reader tries.

Checks performed:
  1. ``pip install axiomize`` is documented in README and docs/quickstart.md.
  2. Every markdown link target in README.md and docs/quickstart.md resolves
     (relative paths, in-repo anchors, or an absolute http(s) URL).
  3. ``examples/quickstart_sir.py`` runs and prints exactly the output block
     quoted in the README and in the docs quickstart.
  4. The documented CLI entry points exist in the installed distribution and
     answer on real input.
  5. ``docs/`` navigation files referenced by ``mkdocs.yml`` exist.

Run from a checkout with the package installed (``pip install -e .`` is enough).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
QUICKSTART = ROOT / "docs" / "quickstart.md"
EXAMPLE = ROOT / "examples" / "quickstart_sir.py"
MKDOCS = ROOT / "mkdocs.yml"

INSTALL_COMMAND = "pip install axiomize"

# Console entry points the quickstart tells a reader to run.
CLI_COMMANDS = {
    "axiomize capabilities": ("interfaces",),
    "axiomize intake \"Reduce traffic congestion in a mid-size city\"": ("status", "questions"),
}

LINK_PATTERN = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
MARKDOWN_LINK_SKIP = ("#", "mailto:")


class CheckFailure(RuntimeError):
    pass


def _fail(message: str) -> None:
    raise CheckFailure(message)


def _read(path: Path) -> str:
    if not path.is_file():
        _fail(f"required file is missing: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def _check_install_documented() -> None:
    for document in (README, QUICKSTART):
        if INSTALL_COMMAND not in _read(document):
            _fail(f"{document.relative_to(ROOT)} does not document `{INSTALL_COMMAND}`")
    print("- install command documented in README.md and docs/quickstart.md")


def _anchor_slugs(markdown: str) -> set[str]:
    """Approximate GitHub's heading-anchor algorithm."""
    slugs: set[str] = set()
    in_fence = False
    for line in markdown.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = re.match(r"^#{1,6}\s+(.*?)\s*#*$", line)
        if not match:
            continue
        slug = match.group(1).strip().lower()
        slug = re.sub(r"[^\w\- ]+", "", slug, flags=re.UNICODE)
        slugs.add(re.sub(r"\s+", "-", slug))
    return slugs


def _check_links(document: Path) -> None:
    text = _read(document)
    slugs = _anchor_slugs(text)
    checked = 0
    for target in LINK_PATTERN.findall(text):
        if target.startswith(MARKDOWN_LINK_SKIP):
            continue
        if target.startswith(("http://", "https://")):
            continue
        path_part, _, anchor = target.partition("#")
        if path_part:
            resolved = (document.parent / path_part).resolve()
            if not resolved.exists():
                _fail(f"{document.relative_to(ROOT)} links to missing path: {target}")
        elif anchor and anchor not in slugs:
            _fail(f"{document.relative_to(ROOT)} links to unknown anchor: {target}")
        checked += 1
    print(f"- {document.relative_to(ROOT)}: {checked} local/anchor link(s) resolve")


def _expected_output_block(document: Path) -> list[str]:
    """Return the ``text`` fenced block that starts with ``status:``."""
    for block in re.findall(r"```text\n(.*?)```", _read(document), flags=re.DOTALL):
        if block.startswith("status:"):
            return [line for line in block.rstrip("\n").splitlines() if line.strip()]
    _fail(f"{document.relative_to(ROOT)} has no `text` block starting with 'status:'")
    return []


def _check_example_output() -> None:
    if not EXAMPLE.is_file():
        _fail("examples/quickstart_sir.py is missing; the quickstart cannot be verified")
    completed = subprocess.run(
        [sys.executable, str(EXAMPLE)],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        cwd=str(ROOT),
    )
    if completed.returncode != 0:
        _fail(f"examples/quickstart_sir.py failed ({completed.returncode}):\n{completed.stderr}")
    actual = [line for line in completed.stdout.rstrip("\n").splitlines() if line.strip()]
    for document in (README, QUICKSTART):
        expected = _expected_output_block(document)
        if actual != expected:
            _fail(
                f"{document.relative_to(ROOT)} quickstart output is stale.\n"
                "--- documented ---\n" + "\n".join(expected) + "\n--- actual ---\n" + "\n".join(actual)
            )
        print(f"- {document.relative_to(ROOT)} quickstart output matches the real run ({len(actual)} lines)")


def _run_cli(arguments: list[str]) -> str:
    import shutil

    executable = shutil.which("axiomize")
    if not executable:
        _fail("installed `axiomize` console entry point not found on PATH")
    completed = subprocess.run(
        [executable, *arguments],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if completed.returncode != 0:
        _fail(f"`axiomize {' '.join(arguments)}` failed ({completed.returncode}):\n{completed.stderr}")
    return completed.stdout


def _check_cli() -> None:
    import json

    for command, required_keys in CLI_COMMANDS.items():
        subcommand, _, remainder = command[len("axiomize "):].partition(" ")
        arguments = [subcommand, remainder.strip('"')] if remainder else [subcommand]
        payload = json.loads(_run_cli(arguments))
        for key in required_keys:
            if key not in payload:
                _fail(f"`axiomize {subcommand}` output is missing key {key!r}")
        print(f"- `axiomize {subcommand}` answered with the documented JSON keys")


def _check_nav_targets() -> None:
    """Verify every ``mkdocs.yml`` nav target exists, without requiring PyYAML.

    Only the nav block is inspected, and only for the ``something.md`` values that
    mkdocs resolves as page paths, so this stays stdlib-only and works in any job
    that has the package installed.
    """
    lines = _read(MKDOCS).splitlines()
    try:
        start = next(index for index, line in enumerate(lines) if line.rstrip() == "nav:")
    except StopIteration:
        _fail("mkdocs.yml has no 'nav:' section")
        return
    targets: list[str] = []
    for line in lines[start + 1:]:
        if line.strip() and not line.startswith((" ", "\t", "-")):
            break  # dedented back out of the nav block
        targets.extend(re.findall(r"([A-Za-z0-9_.-]+\.md)\s*$", line))
    if not targets:
        _fail("mkdocs.yml nav lists no documentation pages")
    missing = [target for target in targets if not (ROOT / "docs" / target).is_file()]
    if missing:
        _fail(f"mkdocs.yml nav references docs pages that do not exist: {missing}")
    print(f"- mkdocs.yml: all {len(targets)} nav target(s) exist under docs/")


def main() -> int:
    checks = (
        _check_install_documented,
        lambda: _check_links(README),
        lambda: _check_links(QUICKSTART),
        _check_example_output,
        _check_cli,
        _check_nav_targets,
    )
    failures: list[str] = []
    for check in checks:
        try:
            check()
        except CheckFailure as exc:
            failures.append(str(exc))
            print(f"- FAIL: {exc}")
    if failures:
        print("\nREADME/DOCS CONTRACT: FAIL")
        return 1
    print("\nREADME/DOCS CONTRACT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())