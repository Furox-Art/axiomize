# Contributing to Axiomize

Thanks for helping make idea-to-model rigor a standard agent capability.

## Adding a perspective (the most valuable PRs)

Each file in `skills/axiomize/perspectives/` follows a fixed contract. A new lens PR must include **all** sections:

```
# Perspective: <Name> (<one-line essence>)

## When Applicable
- Explicit triggers tied to the Phase 2 classifications (flow / interaction / decision / uncertainty)
- What questions this lens answers that others cannot

## Model Forms
- The 2-4 canonical formalisms, with checklists for building them correctly
- Concrete functional forms (not "model it appropriately")

## Standard Analysis Output
- Numbered list of artifacts every analysis must produce

## Strengths / Blind Spots
- (+) what this view uniquely sees
- (-) what this view cannot see (honesty is the product)
```

Rules for perspective content:

1. Every equation symbol must be defined inline.
2. Units are mandatory where dimensional.
3. Include an "analysis ladder" (cheap → expensive methods) if more than one fidelity level exists.
4. No filler prose, a domain expert should be able to build a first model from your file alone.

Candidate lenses not yet covered: queueing networks beyond M/M/c, survival analysis with competing risks beyond reliability scope.

## Adding worked examples (`examples/`)

Follow the eight-section structure exactly as in `examples/epidemic-sir.md` (Parse,
Decompose, Parameters, Assumptions, Perspectives, Comparison & Recommendation,
Implementation, Falsifiability). This is the condensed report layout; the skill's own
workflow has nine phases, Phase 0 through Phase 8. Requirements:

- Real-ish parameter ranges with source classes (`lit.` / `data` / `est.`)
- At least two perspectives actually built, plus at least one **explicitly rejected with a one-line reason**
- A falsifiability section naming observations that would kill the model
- If you add runnable tooling, extend `skills/axiomize/tools/validate.py` (see below)

## Extending `skills/axiomize/tools/validate.py`

Every new model mode must print sanity checks and exit non-zero when they fail. Accepted checks: conservation laws, bounds/monotonicity, agreement with a closed-form theory result (within stated tolerance), or distributional consistency across Monte Carlo runs. CI runs all modes, keep default parameters under ~60s total runtime.

## Style

- Markdown for docs; Python 3.10+ (matching `requires-python`). Standalone skill tools stay
  on stdlib + numpy/scipy so they can run without the full scientific stack.
- No comments in code unless explaining a non-obvious formula's origin.
- English for repo content.

## Local checks

Run what CI runs before opening a PR. All of these are the same commands the workflows
execute, so a green local run predicts a green CI run.

```bash
pip install -r requirements-test.txt
pip install -e .

pytest tests/ -v                                    # full suite
python skills/axiomize/tools/check_skill.py         # skill frontmatter, links, compile
python .github/scripts/check_release_contract.py    # version lockstep
python .github/scripts/readme_example_check.py      # README/docs claims match real output
python .github/scripts/stage_docs.py                # stage skill pages into docs/
python -m mkdocs build --strict                     # docs build, warnings are failures
```

`readme_example_check.py` and `stage_docs.py` exist because CI enforces both. If you touch
`README.md`, `docs/quickstart.md`, `mkdocs.yml`, or `examples/quickstart_sir.py`, that gate
must stay green; it is the mechanism that keeps documentation from drifting from behavior.

## Adding documentation or changing public surfaces

- Docs live in `docs/` and build with `mkdocs build --strict`; a broken link fails the build.
- Pages named in `mkdocs.yml` nav must exist under `docs/`. Four of them (`rigor.md`,
  `archetypes.md`, `adaptive-workflow.md`, `skill.md`) are generated from `skills/axiomize/`
  by `stage_docs.py` and are git-ignored: edit the source under `skills/axiomize/`, never the
  generated page.
- A new console entry point belongs in `[project.scripts]` in `pyproject.toml` and needs a
  matching smoke assertion in `.github/scripts/cli_release_smoke.py`.

## Submitting

1. Fork & branch (`feat/<topic>`).
2. Run the local checks above.
3. Describe what lens/example adds to coverage that no existing file provides.
