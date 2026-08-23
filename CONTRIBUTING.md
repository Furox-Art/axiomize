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
- ✅ what this view uniquely sees
- ❌ what this view cannot see (honesty is the product)
```

Rules for perspective content:

1. Every equation symbol must be defined inline.
2. Units are mandatory where dimensional.
3. Include an "analysis ladder" (cheap → expensive methods) if more than one fidelity level exists.
4. No filler prose — a domain expert should be able to build a first model from your file alone.

Candidate lenses not yet covered: information theory, game theory as its own file, thermodynamic/statistical-mechanics analogies, causal inference, reliability engineering.

## Adding worked examples (`examples/`)

Follow the 8-phase structure exactly as in `examples/epidemic-sir.md`. Requirements:

- Real-ish parameter ranges with source classes (`lit.` / `data` / `est.`)
- At least two perspectives actually built, plus at least one **explicitly rejected with a one-line reason**
- A falsifiability section naming observations that would kill the model
- If you add runnable tooling, extend `tools/validate.py` (see below)

## Extending `tools/validate.py`

Every new model mode must print sanity checks and exit non-zero when they fail. Accepted checks: conservation laws, bounds/monotonicity, agreement with a closed-form theory result (within stated tolerance), or distributional consistency across Monte Carlo runs. CI runs all modes — keep default parameters under ~60s total runtime.

## Style

- Markdown for docs; Python 3.9+ stdlib + numpy/scipy only.
- No comments in code unless explaining a non-obvious formula's origin.
- English for repo content.

## Submitting

1. Fork & branch (`feat/<topic>`).
2. Run all validate modes locally before the PR.
3. Describe what lens/example adds to coverage that no existing file provides.
