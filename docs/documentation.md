# Maintaining this documentation

This page is for people changing the docs, the README, or the benchmark numbers. It is not
needed to use Axiomize.

## What builds what

| Source of truth | Built into |
|---|---|
| `README.md` | GitHub repository page, and the PyPI project description |
| `docs/*.md` | <https://furox-art.github.io/axiomize/> via `mkdocs build --strict` |
| `skills/axiomize/*.md` | the agent skill pack; `skills/axiomize/tools/*.py` are also packaged inside the wheel |
| `.github/scripts/stage_docs.py` | copies a few `skills/axiomize/` pages into `docs/` before the site builds |

`docs/rigor.md`, `docs/archetypes.md`, `docs/adaptive-workflow.md`, `docs/skill.md` and
`docs/examples.md` are **generated** by `.github/scripts/stage_docs.py` and are git-ignored. Edit
the source under `skills/axiomize/`, never the generated page.

## Pages that are not in the site nav

These exist under `docs/`, are excluded from the nav by `exclude_docs` in `mkdocs.yml`, and are
reachable only through direct repository links:

- `publishing-checklist.md` — prepared text for third-party skill registries. Internal process,
  not user documentation.
- `security-ci-contract.md` — how CI enforces the security rules. Maintainer-facing.
- `security-maintenance.md` — dependency and advisory upkeep.
- `security-release-checklist.md` — release-time security steps.
- `security-audit-1.11.2.md` — engineering scope of the 1.11.2 hardening pass.

User-facing security documentation is `docs/security.md`, `docs/security-non-goals.md` and
`docs/security-versioning.md`, all of which stay in the nav.

## Rules that CI enforces

`python .github/scripts/readme_example_check.py` fails the build when:

1. `pip install axiomize` is missing from `README.md` or `docs/quickstart.md`.
2. A relative link or in-document anchor in `README.md` or `docs/quickstart.md` does not resolve.
   Absolute `http(s)` URLs are not fetched, so a broken external link is your responsibility.
3. The output block quoted in `README.md` or `docs/quickstart.md` differs from a real
   `examples/quickstart_sir.py` run.
4. A documented CLI entry point is missing from the installed distribution or does not answer.
5. A page named in the `mkdocs.yml` nav does not exist under `docs/`.

`python -m mkdocs build --strict` fails the build on any broken internal link or missing page.

## Adding a benchmark number

Anything numeric you publish has to be reproducible by someone else. Before adding a score:

1. Record the commit, the sha256 of `skills/axiomize/tools/benchmark_runner.py`,
   `benchmarks/ideas.json` and `benchmarks/rubric.md`, the interpreter version and the run
   timestamp. `docs/benchmark-results.md` carries a table in exactly this shape; follow it.
2. Give the command that regenerates the number verbatim.
3. State what the number does not prove. The automated layer checks report structure, not
   mathematics, and the rubric's real gate is a combined automatic plus human score that is not
   recorded in this repository.
4. If a run cannot be reproduced, put it under a clearly labelled history heading and say why.

Do not present an illustrative or placeholder figure as a measurement.

## Adding a worked example

Full examples follow the eight-phase structure in `examples/epidemic-sir.md`. Every example must
open with the parameter-provenance note, because the ranges in these files are illustrative and
carry no citation:

```markdown
> **Parameter provenance:** the values below are illustrative. `lit.` / `data.` / `est.`
> mark the intended weight of a range; this file cites no external source. Reading material
> for the workflow, not a literature-backed model.
```

Then add the file to `docs/example-gallery.md`, otherwise nothing links to it.

## PyPI description sync (manual step)

`README.md` is the `readme` in `pyproject.toml`, so the PyPI long description is whatever
`README.md` said **at the moment the release wheel was built**. Nothing republishes it
automatically, which means README edits merged after a release do not reach the PyPI page until
the next release. That is the whole reason the published description can lag the repository.

After each release, confirm the two agree:

```bash
# what PyPI currently renders as the description
curl -s https://pypi.org/pypi/axiomize/json | python -c "import json,sys; print(json.load(sys.stdin)['info']['description'])"

# what this checkout would render
python -c "print(open('README.md', encoding='utf-8').read())"
```

If they differ, the published description is stale. The only correct fix is a new release built
from a commit whose `README.md` is current; do not edit the PyPI page by hand, and do not upload
a file to a released version. Until that release exists, the repository README is the accurate
document.

Checklist before tagging:

- [ ] `README.md` states the version being released.
- [ ] `docs/quickstart.md` and `README.md` output blocks match a real run.
- [ ] `CHANGELOG.md` has an entry for the new version.
- [ ] `CITATION.cff` `version` and `date-released` match the release.
- [ ] PyPI metadata refreshed and re-checked with the commands above.

## Local commands

```bash
pip install -r requirements-test.txt
pip install -e .
pip install mkdocs-material

pytest tests/ -v                                    # test suite
python skills/axiomize/tools/check_skill.py         # skill frontmatter, links, compile
python .github/scripts/check_release_contract.py    # version lockstep
python .github/scripts/stage_docs.py                # stage generated docs pages
python .github/scripts/readme_example_check.py      # README/docs claims vs real behavior
python -m mkdocs build --strict                     # site build, warnings are failures
```
