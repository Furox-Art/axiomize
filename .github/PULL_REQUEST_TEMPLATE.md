# What does this PR change?

<!-- One paragraph. Link the issue it closes, if there is one. -->

# What a reviewer should check first

<!-- Name the one thing that would make this wrong. -->

# Checklist

Docs and content:

- [ ] Markdown links resolve (`python skills/axiomize/tools/check_skill.py` checks the skill pack;
      `python -m mkdocs build --strict` checks `docs/`)
- [ ] Any new or changed number in `docs/` carries its reproduction command and states what it
      does not prove, per [docs/documentation.md](docs/documentation.md)
- [ ] Any new or changed example opens with the parameter-provenance note, because example
      parameter ranges are illustrative and uncited
- [ ] README and `docs/quickstart.md` output blocks still match a real run
      (`python .github/scripts/readme_example_check.py`)
- [ ] New pages are added to the `mkdocs.yml` nav, or deliberately excluded there

Skill pack (`skills/axiomize/`):

- [ ] New/changed markdown passes `python skills/axiomize/tools/check_skill.py`
- [ ] Perspective files follow the four-section contract in `CONTRIBUTING.md`
- [ ] Examples follow the 8-phase structure and include at least one rejected-lens rationale
- [ ] Frontmatter of `SKILL.md` still has a `name` and a trigger phrase in its `description`

Code:

- [ ] `pytest tests/ -v` passes
- [ ] New console entry points are declared in `[project.scripts]` and asserted in
      `.github/scripts/cli_release_smoke.py`
- [ ] Tool changes still exit non-zero on failure; default runtime under 60s
- [ ] Version bump plus `CHANGELOG.md`, `CITATION.cff` and `.github/pypi-release-trigger` are in
      lockstep (`python .github/scripts/check_release_contract.py`)

House style:

- [ ] No emojis in content; units stated wherever quantities appear
- [ ] No comment explaining something the code already says
- [ ] No undocumented scientific claim; if a number cannot be reproduced, it is labelled
