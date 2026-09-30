#!/usr/bin/env python3
"""Stage the GitHub Pages docs tree from ``skills/axiomize`` and ``examples``.

The Pages site serves one page per perspective lens plus a concatenated
workflow page, but the sources live in ``skills/axiomize/`` and ``examples/``
so that the skill pack stays browsable in place. This script performs the same
staging for both the Pages workflow and the local/CI docs check, so a clean
checkout can build the site without hand-copying files.

Generated pages are git-ignored; never edit their output by hand.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "axiomize"
DOCS = ROOT / "docs"
EXAMPLES = ROOT / "examples"
SKILL_URL = "https://github.com/Furox-Art/axiomize/tree/main/skills/axiomize"

# Perspective files that SKILL.md and the lens pages link to relatively. Their
# relative links cannot survive being concatenated into a single docs/ page,
# so every one of them is rewritten to an absolute GitHub URL instead.
LENS_NAMES = (
    "agent-based",
    "causal-inference",
    "control",
    "decision-theory",
    "demographic",
    "deterministic",
    "game-theory",
    "information-theory",
    "network",
    "optimization",
    "reliability",
    "spatial",
    "spc",
    "stochastic",
    "thermodynamic",
)
LENS_PATTERN = re.compile(rf"\]\(({LENS_NAMES[0]}|{'|'.join(LENS_NAMES[1:])})\.md")

# How many lines of each source document are surfaced on the aggregated page.
LENS_HEAD_LINES = 12
EXAMPLE_HEAD_LINES = 8


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _head(path: Path, lines: int) -> str:
    return "\n".join(_read(path).splitlines()[:lines])


def _stage_copies() -> list[str]:
    staged: list[str] = []
    for name in ("rigor.md", "archetypes.md", "adaptive-workflow.md"):
        target = DOCS / name
        target.write_text(_read(SKILL / name), encoding="utf-8")
        staged.append(name)
    return staged


def _stage_skill_page() -> str:
    parts = [
        "# The workflow\n",
        _read(SKILL / "SKILL.md"),
        "\n\n# The lenses\n\n",
    ]
    for lens in sorted(SKILL.glob("perspectives/*.md")):
        parts.append(f"## {lens.stem}\n\n{_head(lens, LENS_HEAD_LINES)}\n")

    page = "".join(parts)
    page = re.sub(r"\]\(perspectives/", f"]({SKILL_URL}/perspectives/", page)
    page = re.sub(r"\]\(templates/", f"]({SKILL_URL}/templates/", page)
    page = re.sub(r"\]\(first-principles\.md", f"]({SKILL_URL}/first-principles.md", page)
    page = LENS_PATTERN.sub(rf"]({SKILL_URL}/perspectives/\1.md", page)
    (DOCS / "skill.md").write_text(page, encoding="utf-8")
    return "skill.md"


def _stage_examples_page() -> str:
    parts = ["# Worked examples\n"]
    for example in sorted(EXAMPLES.glob("*.md")):
        parts.append(f"\n## {example.stem}\n\n{_head(example, EXAMPLE_HEAD_LINES)}\n")
    (DOCS / "examples.md").write_text("".join(parts), encoding="utf-8")
    return "examples.md"


def main() -> int:
    for required in (SKILL, DOCS, EXAMPLES):
        if not required.is_dir():
            print(f"FAIL: missing required directory: {required}", file=sys.stderr)
            return 1

    staged = [*_stage_copies(), _stage_skill_page(), _stage_examples_page()]
    print("STAGED_DOCS: PASS")
    for name in staged:
        lines = len((DOCS / name).read_text(encoding="utf-8").splitlines())
        print(f"- docs/{name} ({lines} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())